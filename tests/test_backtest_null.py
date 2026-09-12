"""Point the backtest at series whose answer is known before it runs.

Every number this repo has produced came from real prices, which means none of
them could be checked -- there was nothing to compare against. A backtest that
has never been run on a null is a backtest whose output has no scale: +13 bps of
"edge" means nothing until you know what the same pipeline returns on a series
with no edge in it at all.

Three nulls and one positive control:

    random walk           no reversion exists; edge must not appear
    drifting random walk  no reversion exists, plus a trend to be fooled by
    OU process            reversion exists by construction; must be found

THE ONE THAT MATTERS IS `test_detrending_a_random_walk_does_not_manufacture_edge`.
Subtracting a locally fitted trend from a random walk induces negative
autocorrelation in what is left -- the residual is pulled toward a line that was
itself fitted to the recent past, so it appears to revert to something. This is
the same mechanism that makes the Hodrick-Prescott filter invent business cycles
in data that has none. If `--detrend` produces an edge here, then the de-trended
result on the gold pair is an artefact of the filter and not a property of the
pair, and the flag should be deleted rather than believed.
"""

from __future__ import annotations

import numpy as np
import pytest

from linkage.backtest import FIT_WINDOW, run_on_series

#: Long enough that the rule gets a real sample after its warmup.
LENGTH = 2000

#: Independent draws per null. One draw of a random walk can look like anything;
#: the question is what happens on average.
DRAWS = 12

SPREAD_SD = 20.0  # bps per day, roughly the gold pair's scale


def dates(n: int) -> list:
    import datetime as dt

    start = dt.date(2019, 1, 1)
    return [start + dt.timedelta(days=i) for i in range(n)]


def random_walk(rng, n: int, drift: float = 0.0) -> np.ndarray:
    return np.cumsum(rng.normal(drift, SPREAD_SD, n))


def ou(rng, n: int, *, theta: float = 0.35, sigma: float = SPREAD_SD) -> np.ndarray:
    """A series that genuinely reverts, with a half-life of about two days."""
    out = np.zeros(n)
    for i in range(1, n):
        out[i] = out[i - 1] - theta * out[i - 1] + rng.normal(0, sigma)
    return out


def edges(series_fn, *, detrended: bool, draws: int = DRAWS) -> list[float]:
    """Edge over baseline from `draws` independent series."""
    found = []
    for seed in range(draws):
        rng = np.random.default_rng(seed)
        values = series_fn(rng, LENGTH)
        result = run_on_series(
            "null",
            values,
            dates(LENGTH),
            horizon=3,
            friction_bps=0.0,
            alert_percentile=99.0,
            detrended=detrended,
            quiet=True,
        )
        if result.alerts:
            found.append(result.edge_over_baseline_bps)
    return found


# ---------------------------------------------------------------------------
# Nulls
# ---------------------------------------------------------------------------


def test_a_random_walk_shows_no_edge():
    """The plain rule, on a series with nothing to find."""
    found = edges(random_walk, detrended=False)
    assert found, "the rule never fired on any draw; the null proves nothing"
    mean = float(np.mean(found))
    assert mean < 5.0, (
        f"the rule found {mean:+.1f} bps of edge in a random walk over "
        f"{len(found)} draws; on this series the true edge is zero"
    )


def test_detrending_a_random_walk_does_not_manufacture_edge():
    """The test that decides whether `--detrend` may be believed.

    A residual taken against a trend fitted to its own recent past is pulled
    back toward that trend by construction. If that alone produces an edge, then
    every de-trended result in this repo is measuring the filter rather than the
    market.
    """
    plain = float(np.mean(edges(random_walk, detrended=False)))
    detrended = edges(random_walk, detrended=True)
    assert detrended, "de-trended rule never fired; the null proves nothing"
    mean = float(np.mean(detrended))

    assert mean < 5.0, (
        f"de-trending a random walk produced {mean:+.1f} bps of edge "
        f"(plain: {plain:+.1f}). The filter is inventing reversion, so the "
        f"de-trended gold-pair result is an artefact."
    )


def test_detrending_a_drifting_random_walk_does_not_manufacture_edge():
    """The case the gold pair actually is: a trend over a walk, no reversion."""
    found = edges(lambda rng, n: random_walk(rng, n, drift=0.4), detrended=True)
    assert found, "de-trended rule never fired; the null proves nothing"
    mean = float(np.mean(found))
    assert mean < 5.0, (
        f"de-trending a drifting random walk produced {mean:+.1f} bps of edge; "
        "a trend removed from a walk must not leave something tradeable behind"
    )


# ---------------------------------------------------------------------------
# Positive control
# ---------------------------------------------------------------------------


def test_a_genuinely_reverting_series_is_found():
    """The other half. A null test passed by a rule that never fires is worth
    nothing -- this shows the pipeline can still find reversion that is there."""
    found = edges(ou, detrended=False)
    assert found, "the rule failed to fire on a series that reverts by design"
    mean = float(np.mean(found))
    assert mean > 10.0, (
        f"only {mean:+.1f} bps found in a series built to revert with a "
        "two-day half-life"
    )


def test_the_horizon_gate_refuses_a_random_walk_outright():
    """Upstream of any edge measurement: theta must not be separable from zero."""
    from linkage.ou import fit_ou

    refused = 0
    for seed in range(DRAWS):
        rng = np.random.default_rng(100 + seed)
        fit = fit_ou(random_walk(rng, FIT_WINDOW))
        if not fit.reverts:
            refused += 1
    assert refused >= DRAWS - 2, (
        f"only {refused}/{DRAWS} random walks were refused as non-reverting"
    )
