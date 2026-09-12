"""Observation building: fair value, spread, staleness, and when not to score."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from linkage.config import LinkageConfig
from linkage.engine import MIN_SAMPLES_FOR_Z, SpreadHistory, evaluate_linkage
from linkage.providers.base import Quote

NOW = datetime(2026, 9, 12, 9, 30, tzinfo=timezone.utc)


def linkage(**overrides) -> LinkageConfig:
    base = {
        "id": "adr",
        "description": "ADR against local via USDINR",
        "legs": {
            "local": {"symbol": "INFY.NS", "provider": "fake"},
            "adr": {"symbol": "INFY", "provider": "fake"},
            "fx": {"symbol": "USDINR=X", "provider": "fake"},
        },
        "fair_value": "adr * fx",
        "reference": "local",
        "friction_bps": {"fx_spread": 25, "brokerage": 5},
        "alert": {
            "warn_z": 1.8,
            "alert_z": 2.5,
            "min_net_edge_bps": 15,
            "cooldown_minutes": 60,
        },
    }
    base.update(overrides)
    return LinkageConfig.model_validate(base)


def quotes(local="1550", adr="18.50", fx="83.70", *, age=0.0, stale=False):
    ts = NOW - timedelta(seconds=age)
    return {
        "local": Quote("INFY.NS", Decimal(local), ts, stale),
        "adr": Quote("INFY", Decimal(adr), ts, False),
        "fx": Quote("USDINR=X", Decimal(fx), ts, False),
    }


def full_history(mean: float = 0.0, spread: float = 1.0) -> SpreadHistory:
    """Enough samples to score, with real variance.

    A constant history has zero standard deviation and is deliberately refused
    by the engine, so a usable fixture has to actually vary.
    """
    history = SpreadHistory()
    for i in range(MIN_SAMPLES_FOR_Z):
        history.append(mean + (spread if i % 2 else -spread))
    return history


def test_fair_value_and_spread():
    obs = evaluate_linkage(linkage(), quotes(), SpreadHistory(), now=NOW)

    assert obs.fair_value == Decimal("18.50") * Decimal("83.70")  # 1548.45
    assert obs.reference_price == Decimal("1550")
    assert obs.spread == Decimal("1.55")
    assert obs.spread_bps == pytest.approx(10.0, abs=0.1)


def test_no_z_score_until_enough_history():
    """Eight samples is not a distribution.

    Returning None is the honest answer; returning a number computed from a
    handful of points is a confident-looking lie, and it would alert on the
    very first wobble after startup.
    """
    history = SpreadHistory()
    for _ in range(MIN_SAMPLES_FOR_Z - 1):
        history.append(0.0)

    obs = evaluate_linkage(linkage(), quotes(), history, now=NOW)
    assert obs.z_score is None
    assert obs.net_edge_bps is None
    assert obs.alertable is False


def test_z_score_excludes_the_current_point():
    """Including it drags the mean toward the reading being scored.

    That systematically shrinks extremes -- precisely the readings this system
    exists to find.
    """
    history = SpreadHistory()
    for value in [0.0, 2.0] * (MIN_SAMPLES_FOR_Z // 2):
        history.append(value)

    obs = evaluate_linkage(linkage(), quotes(), history, now=NOW)
    assert obs.z_score is not None
    assert obs.z_score > 3  # ~10bps against a mean of 1.0, sd 1.0


def test_net_edge_is_spread_minus_friction():
    obs = evaluate_linkage(linkage(), quotes(), full_history(), now=NOW)

    # ~10bps gap against 30bps of friction: the gap costs more to capture than
    # it is worth. This is the expected answer most of the time.
    assert obs.net_edge_bps == pytest.approx(abs(obs.spread_bps) - 30, abs=0.1)
    assert obs.net_edge_bps < 0


def test_provider_reported_stale_leg_blocks_alerting():
    obs = evaluate_linkage(
        linkage(), quotes(stale=True), full_history(), now=NOW
    )
    assert obs.stale is True
    assert "stale" in obs.stale_reason
    assert obs.alertable is False


def test_old_leg_blocks_alerting():
    """A frozen leg beside a moving one is what a broken feed looks like.

    The gap widens beautifully and means nothing.
    """
    obs = evaluate_linkage(
        linkage(), quotes(age=600), full_history(), now=NOW, max_age_seconds=180
    )
    assert obs.stale is True
    assert "600s old" in obs.stale_reason
    assert obs.alertable is False


def test_fresh_complete_observation_is_alertable():
    obs = evaluate_linkage(linkage(), quotes(), full_history(), now=NOW)
    assert obs.stale is False
    assert obs.alertable is True


def test_missing_leg_is_an_error_not_a_guess():
    partial = quotes()
    del partial["fx"]
    with pytest.raises(KeyError, match="fx"):
        evaluate_linkage(linkage(), partial, SpreadHistory(), now=NOW)


def test_history_window_is_bounded():
    history = SpreadHistory(window=10)
    for i in range(50):
        history.append(float(i))
    assert len(history) == 10


def test_zero_variance_history_yields_no_score():
    """A spread that has never moved gives a divide-by-zero, not infinity."""
    history = SpreadHistory()
    for _ in range(MIN_SAMPLES_FOR_Z):
        history.append(5.0)
    assert history.z_score(9.0) is None
