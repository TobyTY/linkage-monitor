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

#: Shape of the persisted snapshot. Bumped whenever a field is added, removed
#: or reinterpreted, so that a restore across an upgrade refuses rather than
#: quietly loading a state that means something else now.
#:
#: 2: the Kalman filter now runs on a normalised scale, and its priors changed
#:    with it (delta 1e-4 -> 1e-7, observation_var 1e-3 -> 1e-5 in units of the
#:    first observation). Every version-1 snapshot holds a state fitted in raw
#:    price units by a filter that was not scale-invariant, so its beta is wrong
#:    and its intercept is not even in the same units the filter now uses.
#:    Resuming one would carry the bug forward silently, which is the exact
#:    failure this constant exists to prevent.
STATE_VERSION = 2

#: Trailing window the OU process is refitted on. Never the full history: a
#: half-life fitted on data that includes the future is not a half-life.
OU_WINDOW = 250


class StateVersionMismatch(Exception):
    """A stored snapshot was written by a build that meant something else."""


@dataclass(frozen=True)
class Verdict:
    """What the composed detector concluded about one observation."""

    linkage_id: str
    ts: datetime
    should_alert: bool
    reason: str

    #: The deviation this verdict is about, in basis points. Carried on the
    #: verdict rather than left on the observation because everything that
    #: consumes a verdict -- the renderer, the notifier, the alerts table --
    #: needs the number the decision was made on, and reaching back for it is
    #: how the logged number drifts from the decided number.
    spread_bps: float | None = None

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
    # No delta override here. It used to say delta=1e-5, which meant the prior
    # was defined in two places: once as the default in kalman.py and once
    # here, silently winning. Correcting the default alone then changed
    # nothing on the live path -- the bug survived its own fix, which is the
    # argument for there being exactly one definition.
    kalman: KalmanHedge = field(default_factory=KalmanHedge)
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
                spread_bps=spread_bps,
                kalman=step,
            )

        if reading is None:
            return Verdict(
                self.linkage_id,
                observation.ts,
                False,
                "no distribution yet",
                spread_bps=spread_bps,
                kalman=step,
            )

        # Gate 1 -- is this deviation unusual against what this linkage actually
        # does, rather than against an assumed normal distribution?
        if not reading.exceeds_alert:
            return Verdict(
                self.linkage_id,
                observation.ts,
                False,
                f"{reading.percentile:.1f}th percentile, below alert threshold",
                spread_bps=spread_bps,
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
                spread_bps=spread_bps,
                kalman=step,
                threshold=reading,
            )

        try:
            fit = fit_ou(window)
        except ValueError as exc:
            return Verdict(
                self.linkage_id,
                observation.ts,
                False,
                str(exc),
                spread_bps=spread_bps,
                kalman=step,
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
            spread_bps=spread_bps,
            kalman=step,
            threshold=reading,
            gate=gate,
            ou=fit,
        )

    def warmup(self, observations: list[Observation], linkage: LinkageConfig) -> None:
        """Replay history so the detector is ready at startup, not in a week."""
        for observation in observations:
            self.observe(observation, linkage)

    # ---- persistence -------------------------------------------------------
    #
    # Everything mutated by `observe` appears here, and nothing else. The test
    # that keeps it honest does not compare dictionaries: it splits a series in
    # two, runs one detector straight through and another through a save and a
    # reload, and asserts the two verdicts are identical. A field forgotten here
    # shows up there as a divergence, which is what the omission would actually
    # cost in production.

    def snapshot(self) -> dict:
        return {
            "version": STATE_VERSION,
            "linkage_id": self.linkage_id,
            "seen": self.seen,
            "kalman": self.kalman.snapshot(),
            "threshold": self.threshold.snapshot(),
            "spread_history": list(self.spread_history),
        }

    @classmethod
    def for_linkage(cls, linkage: LinkageConfig) -> LinkageDetector:
        """A fresh detector carrying this linkage's own prior.

        Constructing detectors through here rather than calling the dataclass
        directly is what keeps `kalman_delta` from being silently ignored at
        one of the two call sites.
        """
        kalman = (
            KalmanHedge(delta=linkage.kalman_delta)
            if linkage.kalman_delta is not None
            else KalmanHedge()
        )
        return cls(linkage_id=linkage.id, kalman=kalman)

    @classmethod
    def restore(cls, snapshot: dict) -> LinkageDetector:
        version = snapshot.get("version")
        if version != STATE_VERSION:
            raise StateVersionMismatch(
                f"snapshot is version {version}, this build reads {STATE_VERSION}"
            )
        return cls(
            linkage_id=snapshot["linkage_id"],
            kalman=KalmanHedge.restore(snapshot["kalman"]),
            threshold=EmpiricalThreshold.restore(snapshot["threshold"]),
            spread_history=[float(v) for v in snapshot["spread_history"]],
            seen=int(snapshot["seen"]),
        )
