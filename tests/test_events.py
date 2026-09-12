"""The event study, on constructed events whose answer is known.

Nothing here touches yfinance. Events and prices are built so that the correct
abnormal move is arithmetic rather than opinion -- which is the only way to
check that the benchmark is really being subtracted, that the entry price really
precedes the announcement, and that the calibration measurement is really out of
sample.

The two results this module actually produced on real data are asserted as
properties rather than as numbers: that a projection reports when the surprise
explains nothing, and that it refuses to call itself calibrated when its
measured coverage disagrees with its promise.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from linkage.events import (
    INTERVAL_CONFIDENCE,
    MIN_EVENTS,
    EarningsEvent,
    EventCalendar,
    benchmark_for,
    measure,
    project,
)

START = datetime(2024, 1, 3, tzinfo=timezone.utc)


def event(day: int, *, surprise: float | None = 0.0, reported: float | None = 1.0):
    return EarningsEvent(
        symbol="AAA.NS",
        when=START + timedelta(days=day),
        eps_estimate=1.0,
        reported_eps=reported,
        surprise_pct=surprise,
    )


def series(values: list[float], *, start=START, days: int | None = None) -> pd.Series:
    index = pd.date_range(start.date(), periods=len(values), freq="D")
    return pd.Series(values, index=index)


# ---------------------------------------------------------------------------
# Measuring the move
# ---------------------------------------------------------------------------


def test_the_benchmark_is_subtracted():
    """A stock up 3% on the day the index was up 3% did not move on results."""
    prices = series([100.0, 100.0, 103.0, 103.0, 103.0])
    bench = series([200.0, 200.0, 206.0, 206.0, 206.0])

    (outcome,) = measure([event(2)], prices, bench, horizon_days=1)

    assert outcome.raw_move_pct == pytest.approx(3.0)
    assert outcome.benchmark_move_pct == pytest.approx(3.0)
    assert outcome.abnormal_move_pct == pytest.approx(0.0)


def test_the_entry_price_is_the_close_before_the_announcement():
    """Using the event day's own close would mean measuring the reaction from
    inside it, on the roughly half of announcements made before the close --
    which is lookahead wearing ordinary clothes.
    """
    # Day 2 is the event. The stock jumps that day and stays put afterwards.
    prices = series([100.0, 100.0, 110.0, 110.0, 110.0])
    bench = series([200.0, 200.0, 200.0, 200.0, 200.0])

    (outcome,) = measure([event(2)], prices, bench, horizon_days=1)

    # Entry at 100 (day 1's close), exit at 110: the whole move is captured.
    assert outcome.abnormal_move_pct == pytest.approx(10.0)


def test_an_event_without_enough_history_after_it_is_dropped():
    prices = series([100.0, 101.0, 102.0])
    bench = series([200.0, 200.0, 200.0])
    assert measure([event(2)], prices, bench, horizon_days=3) == []


def test_a_scheduled_event_is_not_measured():
    """An announcement that has not happened has no outcome to record."""
    prices = series([100.0] * 10)
    bench = series([200.0] * 10)
    future = event(2, reported=None, surprise=None)
    assert measure([future], prices, bench, horizon_days=1) == []


def test_an_event_with_no_consensus_is_dropped():
    prices = series([100.0] * 10)
    bench = series([200.0] * 10)
    assert measure([event(2, surprise=None)], prices, bench, horizon_days=1) == []


# ---------------------------------------------------------------------------
# Projecting
# ---------------------------------------------------------------------------


def build_outcomes(n: int, *, beta: float, noise: float, seed: int = 5):
    """n events where the abnormal move really is beta * surprise + noise."""
    rng = np.random.default_rng(seed)
    prices, bench, events = [100.0], [200.0], []

    for i in range(n):
        surprise = float(rng.normal(0, 10))
        move = beta * surprise + float(rng.normal(0, noise))
        # Two flat days, then the event day carrying the whole move.
        prices += [prices[-1], prices[-1] * (1 + move / 100), prices[-1] * (1 + move / 100)]
        bench += [bench[-1], bench[-1], bench[-1]]
        events.append(event(len(prices) - 2, surprise=surprise))

    return measure(
        events, series(prices), series(bench), horizon_days=1
    )


def test_too_few_events_gets_no_projection():
    """Silence rather than a number nobody should use."""
    assert project("AAA.NS", build_outcomes(MIN_EVENTS - 3, beta=0.5, noise=1)) is None


def test_a_real_relationship_between_surprise_and_move_is_found():
    outcomes = build_outcomes(60, beta=0.5, noise=1.0)
    projection = project("AAA.NS", outcomes, surprise_pct=10.0)

    assert projection is not None
    assert projection.surprise_beta == pytest.approx(0.5, abs=0.1)
    assert projection.surprise_explains_anything
    assert projection.expected_move_pct == pytest.approx(5.0, abs=1.0)


def test_a_surprise_that_explains_nothing_is_reported_as_such():
    """What real symbols actually look like. Consensus is public, so the market
    has already priced its own view of it, and the projection collapses to the
    symbol's typical event move."""
    outcomes = build_outcomes(60, beta=0.0, noise=3.0)
    projection = project("AAA.NS", outcomes)

    assert projection is not None
    assert not projection.surprise_explains_anything
    assert projection.typical_abs_move_pct > 0


def test_the_interval_widens_with_the_noise():
    quiet = project("AAA.NS", build_outcomes(60, beta=0.5, noise=0.5))
    wild = project("AAA.NS", build_outcomes(60, beta=0.5, noise=5.0))

    quiet_width = quiet.interval_high_pct - quiet.interval_low_pct
    wild_width = wild.interval_high_pct - wild.interval_low_pct
    assert wild_width > quiet_width * 3


def test_coverage_is_measured_out_of_sample():
    """On well-behaved normal noise the interval should roughly deliver what it
    promises. Real event returns do not, which is why this number is measured
    per symbol and reported rather than assumed."""
    projection = project("AAA.NS", build_outcomes(90, beta=0.5, noise=2.0))

    assert projection.measured_coverage is not None
    assert projection.coverage_n > 20
    assert projection.measured_coverage == pytest.approx(INTERVAL_CONFIDENCE, abs=0.15)
    assert projection.well_calibrated


def test_a_miscalibrated_interval_refuses_to_call_itself_calibrated():
    from dataclasses import replace

    good = project("AAA.NS", build_outcomes(60, beta=0.5, noise=2.0))
    bad = replace(good, measured_coverage=0.45)

    assert not bad.well_calibrated
    assert "NOT CALIBRATED" in bad.summary()
    assert "Do not size on it" in bad.summary()


def test_the_summary_shows_the_real_coverage_beside_the_promised_one():
    projection = project("AAA.NS", build_outcomes(60, beta=0.5, noise=2.0))
    assert "really" in projection.summary()


# ---------------------------------------------------------------------------
# Suppression -- the part that changes what the scanner does
# ---------------------------------------------------------------------------


def calendar_with(days_away: float | None) -> EventCalendar:
    if days_away is None:
        return EventCalendar({"AAA.NS": []})
    when = datetime.now(timezone.utc) + timedelta(days=days_away)
    return EventCalendar(
        {"AAA.NS": [EarningsEvent("AAA.NS", when, 1.0, None, None)]}
    )


def test_an_event_inside_the_horizon_blocks():
    calendar = calendar_with(1.5)
    assert calendar.blocking(["AAA.NS"], within_days=3)


def test_an_event_beyond_the_horizon_does_not_block():
    calendar = calendar_with(9.0)
    assert not calendar.blocking(["AAA.NS"], within_days=3)


def test_a_past_event_does_not_block():
    """The risk is the announcement ahead, not the one behind."""
    calendar = calendar_with(-2.0)
    assert not calendar.blocking(["AAA.NS"], within_days=3)


def test_a_symbol_with_no_calendar_does_not_block():
    """Most legs are FX crosses and ETFs that never report. Absent data must
    mean 'nothing scheduled', not 'unknown, so refuse to alert'."""
    assert not EventCalendar({}).blocking(["USDINR=X"], within_days=3)


def test_any_leg_reporting_blocks_the_whole_linkage():
    calendar = calendar_with(1.0)
    blocked = calendar.blocking(["USDINR=X", "AAA.NS"], within_days=3)
    assert len(blocked) == 1
    assert blocked[0].symbol == "AAA.NS"


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("INFY.NS", "^NSEI"),
        ("RELIANCE.NS", "^NSEI"),
        ("INFY.BO", "^BSESN"),
        ("INFY", "^GSPC"),
        ("AAPL", "^GSPC"),
    ],
)
def test_the_benchmark_matches_the_listing(symbol, expected):
    assert benchmark_for(symbol) == expected


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("INFY.NS", True),
        ("GOLDBEES.NS", True),   # an ETF looks like an equity; queried and empty
        ("USDINR=X", False),
        ("GC=F", False),
        ("^NSEI", False),
    ],
)
def test_only_things_that_can_report_are_queried(symbol, expected):
    """Sixteen of this universe's thirty-four symbols are FX crosses, futures
    or indices. Asking each one for an earnings date costs a round trip and
    returns a 'may be delisted' error that is simply untrue."""
    from linkage.events import could_report

    assert could_report(symbol) is expected
