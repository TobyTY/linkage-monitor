"""The three detectors, composed into one verdict per observation.

    Kalman  ->  produces the signal, adaptively
    OU gate ->  decides whether it is reachable inside the holding period
    Quantile -> decides where the line actually sits

Each one alone is wrong in a specific way. A Kalman z with no gate alerts on
deviations that will take six weeks to revert. A gate with no empirical
threshold uses a sigma cut-off that fires several times more often than the
arithmetic promises. A threshold with no filter scores against a hedge ratio
that stopped being true a year ago.

ON THE KALMAN'S OBSERVATION EQUATION. For a computable linkage the filter runs
`reference ~ beta * fair_value`, not on the raw spread. That choice does real
work: if the conversion constants in config are right, beta sits at 1. If one
goes stale -- an ADR ratio changes, an ETF's units-per-gram drifts -- beta moves
away from 1 and the filter ABSORBS it, instead of reporting a permanent
divergence that never reverts. The staleness shows up as a drifting beta, where
it can be seen, rather than as a standing fake arbitrage.

For a statistical pair there is no fair value, so the filter runs
`log(a) ~ beta * log(b)` in the usual way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from linkage.config import LinkageConfig
from linkage.engine import Observation
from linkage.kalman import KalmanHedge, KalmanStep
from linkage.ou import GateResult, OUFit, fit_ou, horizon_gate
from linkage.thresholds import EmpiricalThreshold, ThresholdReading

#: Observations before the detector will say anything. The Kalman needs to stop
#: being ignorant, the threshold needs a distribution, the OU fit needs a window.
WARMUP_OBSERVATIONS = 120

#: Trailing window the OU process is refitted on. Never the full history: a
#: half-life fitted on data that includes the future is not a half-life.
OU_WINDOW = 250


@dataclass(frozen=True)
class Verdict:
    """What the composed detector concluded about one observation."""

    linkage_id: str
    ts: datetime
    should_alert: bool
    reason: str

    kalman: KalmanStep | None = None
    threshold: ThresholdReading | None = None
    gate: GateResult | None = None
    ou: OUFit | None = None

    @property
    def z(self) -> float | None:
        return self.kalman.z if self.kalman else None

    @property
    def beta_drift(self) -> float | None:
        """How far the fitted ratio has moved from 1.

        Only meaningful for computable linkages, where 1 is the value the
        config's constants imply. A persistent drift here is a stale constant
        asking to be recalibrated, not a trading signal.
        """
        return abs(self.kalman.beta - 1.0) if self.kalman else None


@dataclass
class LinkageDetector:
    """Per-linkage detector state. One of these lives per linkage, forever."""

    linkage_id: str
    kalman: KalmanHedge = field(default_factory=lambda: KalmanHedge(delta=1e-5))
    threshold: EmpiricalThreshold = field(default_factory=EmpiricalThreshold)
    spread_history: list[float] = field(default_factory=list)
    seen: int = 0

    def observe(
        self,
        observation: Observation,
        linkage: LinkageConfig,
        *,
        horizon_periods: float = 3.0,
    ) -> Verdict:
        """Advance all three detectors and combine them into one verdict."""
        # A stale observation advances nothing. Feeding it in would corrupt the
        # filter's state and the threshold's distribution with a price that was
        # never real, and both are long-lived.
        if observation.stale:
            return Verdict(
                self.linkage_id,
                observation.ts,
                False,
                f"stale: {observation.stale_reason}",
            )

        self.seen += 1
        step = self.kalman.update(
            float(observation.reference_price), float(observation.fair_value)
        )

        spread_bps = observation.spread_bps
        self.spread_history.append(spread_bps)
        if len(self.spread_history) > OU_WINDOW * 2:
            del self.spread_history[:-OU_WINDOW]

        reading = self.threshold.score(spread_bps)
        self.threshold.append(spread_bps)

        if self.seen < WARMUP_OBSERVATIONS:
            return Verdict(
                self.linkage_id,
                observation.ts,
                False,
                f"warming up ({self.seen}/{WARMUP_OBSERVATIONS})",
                kalman=step,
            )

        if reading is None:
            return Verdict(
                self.linkage_id, observation.ts, False, "no distribution yet", kalman=step
            )

        # Gate 1 -- is this deviation unusual against what this linkage actually
        # does, rather than against an assumed normal distribution?
        if not reading.exceeds_alert:
            return Verdict(
                self.linkage_id,
                observation.ts,
                False,
                f"{reading.percentile:.1f}th percentile, below alert threshold",
                kalman=step,
                threshold=reading,
            )

        # Gate 2 -- does enough of it come back inside the holding period to
        # beat what it costs to trade?
        window = self.spread_history[-OU_WINDOW:]
        if len(window) < 30:
            return Verdict(
                self.linkage_id,
                observation.ts,
                False,
                "insufficient history to fit reversion",
                kalman=step,
                threshold=reading,
            )

        try:
            fit = fit_ou(window)
        except ValueError as exc:
            return Verdict(
                self.linkage_id, observation.ts, False, str(exc), kalman=step,
                threshold=reading,
            )

        deviation = spread_bps - fit.mu
        gate = horizon_gate(
            deviation,
            fit,
            horizon_periods=horizon_periods,
            friction_bps=linkage.total_friction_bps,
            min_edge_bps=linkage.alert.min_net_edge_bps,
        )

        return Verdict(
            self.linkage_id,
            observation.ts,
            gate.passed,
            gate.reason,
            kalman=step,
            threshold=reading,
            gate=gate,
            ou=fit,
        )

    def warmup(self, observations: list[Observation], linkage: LinkageConfig) -> None:
        """Replay history so the detector is ready at startup, not in a week."""
        for observation in observations:
            self.observe(observation, linkage)
