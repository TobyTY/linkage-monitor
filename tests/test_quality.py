"""Data screening, tested against the two failures that caused it to exist.

Both screens in this module were written in response to a specific bad print
that reached a headline number, so both tests below reconstruct that print
rather than inventing a tidy synthetic one. A screen tested only on data
somebody made up to be caught is a screen that catches made-up data.

The other half of each test matters as much: the screen must NOT remove the
legitimate case it most resembles. A spike screen that eats real crashes and a
stale screen that eats quiet days are both worse than no screen, because they
delete evidence while reporting that the data is clean.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from linkage.quality import (
    DEFAULT_MIN_PARTNER_MOVE,
    find_mad_outliers,
    find_spikes,
    find_stale_prints,
    screen,
)


def frame(**columns) -> pd.DataFrame:
    n = len(next(iter(columns.values())))
    index = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame(columns, index=index)


# ----------------------------------------------------------------- stale prints


def test_the_real_2025_03_18_carry_forward_is_caught():
    """The failure this screen was written for.

    Yahoo returned NIFTYBEES.NS at exactly its previous close while the Nifty
    moved +1.45%. Nothing spiked, nothing was an outlier in level, and the
    detector read the resulting gap as a -6 sigma divergence.
    """
    f = frame(
        etf=[251.740005, 252.179993, 252.179993, 256.700012],
        index=[22470.50, 22508.75, 22834.300781, 22907.599609],
    )
    stale = find_stale_prints(f)
    assert list(stale) == ["etf"]
    assert stale["etf"] == [f.index[2]]


def test_a_genuinely_flat_day_is_not_stale():
    """An unchanged close on a day the partner also barely moved is a quiet
    day. Removing those would delete most of a calm month."""
    f = frame(etf=[100.0, 100.0, 100.0], index=[500.0, 500.4, 500.8])
    assert find_stale_prints(f) == {}


def test_a_repeat_is_only_stale_when_the_partner_actually_moved():
    f = frame(etf=[100.0, 100.0], index=[500.0, 500.0])
    assert find_stale_prints(f) == {}


def test_either_leg_can_be_the_stale_one():
    """The bad print is not always in the column that happens to be first."""
    f = frame(etf=[100.0, 103.0], index=[500.0, 500.0])
    assert list(find_stale_prints(f)) == ["index"]


def test_exact_equality_is_the_test_not_approximate():
    """A near-unchanged close is a market outcome. Only a value repeated to the
    last representable decimal is a value that was carried forward."""
    f = frame(etf=[252.179993, 252.179994], index=[22508.75, 22834.30])
    assert find_stale_prints(f) == {}


def test_the_partner_move_threshold_is_respected():
    f = frame(etf=[100.0, 100.0], index=[500.0, 501.0])  # +0.2%, under 0.5%
    assert find_stale_prints(f) == {}
    assert find_stale_prints(f, min_partner_move=0.001) != {}


def test_three_legs_flag_against_the_largest_partner_move():
    f = frame(a=[100.0, 100.0], b=[500.0, 500.1], c=[10.0, 10.5])
    assert list(find_stale_prints(f)) == ["a"]


def test_a_single_row_cannot_be_stale():
    assert find_stale_prints(frame(a=[1.0], b=[2.0])) == {}


# ------------------------------------------------------------------- spikes


def test_a_one_day_bad_print_is_caught_as_a_spike():
    prices = pd.Series(
        [43.1, 43.2, 0.42, 43.0, 43.4],
        index=pd.bdate_range("2022-01-03", periods=5),
    )
    assert find_spikes(prices)


def test_the_setfgold_error_lasted_two_days_and_the_spike_screen_misses_it():
    """Worth pinning down, because the module docstring reads as though the
    spike screen caught the failure it was written for. It did not.

    `find_spikes` requires the big move to reverse on the NEXT bar. The real
    SETFGOLD error was 0.42 on two consecutive days, so the move out is
    followed by no move at all, and the reversal test never fires. MAD is what
    actually caught it -- which is the stronger argument for having two screens
    rather than a better one.
    """
    prices = pd.Series(
        [43.1, 43.2, 0.42, 0.42, 43.0, 43.4],
        index=pd.bdate_range("2022-01-03", periods=6),
    )
    assert find_spikes(prices) == []


def test_mad_is_what_actually_catches_the_setfgold_error():
    clean = [43.0 + 0.1 * (i % 5) for i in range(60)]
    contaminated = clean[:30] + [0.42, 0.42] + clean[32:]
    spread = pd.Series(
        np.log(contaminated), index=pd.bdate_range("2022-01-03", periods=60)
    )
    assert len(find_mad_outliers(spread)) == 2


def test_a_real_crash_is_not_a_spike():
    """A genuine 50% move persists into the next session. A data error is
    corrected by it, and that reversal is the only thing separating them."""
    prices = pd.Series(
        [100.0, 100.0, 50.0, 49.0, 48.0, 51.0],
        index=pd.bdate_range("2025-01-01", periods=6),
    )
    assert find_spikes(prices) == []


def test_a_series_too_short_to_judge_returns_nothing():
    prices = pd.Series([1.0, 100.0], index=pd.bdate_range("2025-01-01", periods=2))
    assert find_spikes(prices) == []


# --------------------------------------------------------------- MAD outliers


def test_mad_finds_what_a_sigma_screen_would_hide():
    """The reason MAD is used at all. A 3-sigma screen computed on contaminated
    data inflates its own threshold to cover the contamination and then reports
    that everything is fine."""
    values = list(np.random.default_rng(0).normal(0, 0.001, 200))
    values[100] = 5.0
    spread = pd.Series(values, index=pd.bdate_range("2024-01-01", periods=200))

    assert find_mad_outliers(spread)

    mean, sigma = spread.mean(), spread.std()
    assert abs(spread.iloc[100] - mean) < 15 * sigma  # a sigma screen misses it


def test_mad_needs_enough_data_to_have_an_opinion():
    spread = pd.Series([0.0, 5.0], index=pd.bdate_range("2025-01-01", periods=2))
    assert find_mad_outliers(spread) == []


def test_a_constant_series_has_no_outliers():
    """MAD is zero, and dividing by it would make every point infinitely far
    from the median."""
    spread = pd.Series([1.0] * 50, index=pd.bdate_range("2025-01-01", periods=50))
    assert find_mad_outliers(spread) == []


# -------------------------------------------------------------------- screen


def test_screen_reports_what_it_removed_rather_than_cleaning_silently():
    """The report is the point. A screen that silently drops rows is a screen
    that can quietly delete a real crash and never say so."""
    f = frame(
        etf=[251.74, 252.179993, 252.179993, 256.70],
        index=[22470.50, 22508.75, 22834.30, 22907.60],
    )
    cleaned, report = screen(f)
    assert len(cleaned) == 3
    assert report.removed == 1
    assert not report.clean
    assert "stale print" in report.summary()


def test_clean_data_passes_through_untouched():
    f = frame(etf=[100.0, 101.0, 102.0], index=[500.0, 505.0, 510.0])
    cleaned, report = screen(f)
    assert len(cleaned) == 3
    assert report.clean
    assert "nothing removed" in report.summary()


def test_an_empty_frame_does_not_explode():
    cleaned, report = screen(pd.DataFrame({"a": [], "b": []}))
    assert cleaned.empty and report.clean


@pytest.mark.parametrize("move", [DEFAULT_MIN_PARTNER_MOVE * 1.01, 0.02, 0.10])
def test_partner_moves_at_or_above_the_threshold_flag(move):
    f = frame(etf=[100.0, 100.0], index=[500.0, 500.0 * (1 + move)])
    assert find_stale_prints(f) != {}
