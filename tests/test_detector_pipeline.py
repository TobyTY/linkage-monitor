"""The composed detector: Kalman, then quantile, then horizon gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from linkage.detector import OU_WINDOW, WARMUP_OBSERVATIONS, LinkageDetector
from linkage.engine import Observation
from tests.test_engine import linkage

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def obs(spread_bps: float, *, day: int = 0, stale: bool = False, fair: float = 1000.0):
    """One observation with a chosen spread, expressed through real prices."""
    reference = fair * (1 + spread_bps / 10_000)
    return Observation(
        linkage_id="adr",
        ts=START + timedelta(days=day),
        leg_prices={"local": Decimal(str(round(reference, 4)))},
        fair_value=Decimal(str(round(fair, 4))),
        reference_price=Decimal(str(round(reference, 4))),
        spread=Decimal(str(round(reference - fair, 4))),
        spread_bps=spread_bps,
        z_score=None if stale else 0.0,
        net_edge_bps=None if stale else 0.0,
        stale=stale,
        stale_reason="feed hiccup" if stale else None,
    )


def _feed(det: LinkageDetector, cfg, values, *, start_day=0):
    last = None
    for i, v in enumerate(values):
        last = det.observe(obs(v, day=start_day + i), cfg)
    return last


def test_detector_refuses_to_speak_during_warmup():
    det = LinkageDetector("adr")
    verdict = _feed(det, linkage(), [0.0, 5.0, -5.0])
    assert not verdict.should_alert
    assert "warming up" in verdict.reason


def test_quiet_series_produces_no_alert():
    """A pair behaving normally must stay silent however long it runs."""
    det, cfg = LinkageDetector("adr"), linkage()
    values = [(-1) ** i * 3.0 for i in range(WARMUP_OBSERVATIONS + 200)]
    verdict = _feed(det, cfg, values)
    assert not verdict.should_alert


def test_stale_observation_advances_nothing():
    """A price that was never real must not enter long-lived state.

    Both the filter and the threshold distribution persist for the life of the
    process, so a single bad observation admitted here contaminates every
    verdict that follows.
    """
    det, cfg = LinkageDetector("adr"), linkage()
    _feed(det, cfg, [(-1) ** i * 3.0 for i in range(50)])

    before_seen, before_len = det.seen, len(det.threshold)
    verdict = det.observe(obs(9_999.0, day=99, stale=True), cfg)

    assert not verdict.should_alert
    assert "stale" in verdict.reason
    assert det.seen == before_seen
    assert len(det.threshold) == before_len


def test_ordinary_deviation_is_rejected_by_the_percentile_gate():
    """Scored against what this linkage actually does, not an assumed shape."""
    import numpy as np

    rng = np.random.default_rng(11)
    det, cfg = LinkageDetector("adr"), linkage()
    _feed(det, cfg, [float(v) for v in rng.normal(0, 10, WARMUP_OBSERVATIONS + 300)])

    # Half a standard deviation: unremarkable for this series.
    verdict = det.observe(obs(5.0, day=900), cfg)
    assert not verdict.should_alert
    assert "percentile" in verdict.reason


def test_extreme_but_slow_deviation_is_rejected_by_the_horizon_gate():
    """The case a percentile threshold alone gets wrong.

    A near-random-walk spread wanders far from its mean, so an extreme reading
    is genuinely rare -- and still worthless, because nothing pulls it back
    inside three days.
    """
    import numpy as np

    rng = np.random.default_rng(3)
    walk = np.cumsum(rng.normal(0, 4, OU_WINDOW + WARMUP_OBSERVATIONS))

    det, cfg = LinkageDetector("adr"), linkage()
    _feed(det, cfg, [float(v) for v in walk])

    verdict = det.observe(obs(float(walk[-1]) + 400.0, day=900), cfg)
    assert not verdict.should_alert
    assert verdict.gate is not None
    assert "revert" in verdict.reason


def test_beta_drift_exposes_a_stale_conversion_constant():
    """The reason the filter runs on reference ~ beta * fair_value.

    Here the true relationship shifts 3% -- an ADR ratio changing, or an ETF's
    units-per-gram drifting. Naively that is a permanent 300bps 'divergence'
    that never reverts and alerts forever. The filter instead moves beta, so the
    staleness becomes visible as drift rather than as a standing fake arbitrage.
    """
    import pytest

    det, cfg = LinkageDetector("adr"), linkage()

    # Phase one: config is correct, so reference tracks fair value exactly.
    for i in range(200):
        det.observe(obs(0.0, day=i), cfg)
    assert det.kalman.state[0] == pytest.approx(1.0, abs=0.02)
    settled = det.kalman.state[0]

    # Phase two: the constant goes 3% stale, so reference now sits 300bps above
    # fair value permanently.
    for i in range(200, 600):
        verdict = det.observe(obs(300.0, day=i), cfg)

    assert det.kalman.state[0] > settled
    assert verdict.beta_drift > 0.005
