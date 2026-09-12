"""Fitting a pair, and refusing to run one.

Built on synthetic pairs whose true relationship is set before the fit sees
them, so "the fit is right" is a checkable claim rather than a plausible-looking
number. The admission gate is then shown refusing each of the four ways a pair
can be unfit, one test per way.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from linkage.config import Access, Category, PairSpec, load_catalogue
from linkage.engine import SpreadHistory, evaluate_linkage
from linkage.providers.base import Quote
from linkage.stat_pairs import (
    ADMISSION_SIGMAS,
    MAX_TRADES_TO_DETECT,
    admit,
    compile_pair,
    fit,
)

CATALOGUE = "config/pairs.yaml"


def spec(**overrides) -> PairSpec:
    base = {
        "id": "synthetic",
        "group": "india_sector",
        "a": "AAA.NS",
        "b": "BBB.NS",
        "access": "long_only",
        "mechanism": "constructed",
        "breaks_when": "never, it is synthetic",
    }
    base.update(overrides)
    return PairSpec.model_validate(base)


def frame(a: np.ndarray, b: np.ndarray) -> pd.DataFrame:
    index = pd.date_range("2021-01-01", periods=len(a), freq="B")
    return pd.DataFrame({"AAA.NS": a, "BBB.NS": b}, index=index)


def cointegrated(n=1200, *, k=2.5, beta=0.85, resid_sd=0.02, theta=0.25, seed=3):
    """a = k * b^beta * exp(e), where e is a genuine OU process.

    The spread reverts by construction, so anything that fails to find it is
    broken rather than merely unlucky.
    """
    rng = np.random.default_rng(seed)
    b = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = e[i - 1] - theta * e[i - 1] + rng.normal(0, resid_sd)
    return k * b**beta * np.exp(e), b


def independent(n=1200, seed=9):
    """Two unrelated random walks. There is nothing here to find."""
    rng = np.random.default_rng(seed)
    a = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    b = 250 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    return a, b


# ---------------------------------------------------------------------------
# The fit
# ---------------------------------------------------------------------------


def test_the_fit_recovers_a_relationship_that_was_put_there():
    a, b = cointegrated(k=2.5, beta=0.85)
    rel = fit("synthetic", "AAA.NS", "BBB.NS", frame(a, b))

    assert rel.beta == pytest.approx(0.85, abs=0.03)
    assert rel.coint_pvalue < 0.05
    assert rel.ou.reverts
    assert rel.half_life_days == pytest.approx(np.log(2) / 0.25, rel=0.35)

    # k is checked THROUGH the fair value, not on its own. k and beta are
    # strongly correlated in the fit -- b sits near 100, so beta being off by
    # 0.02 moves k by about 10% while the fitted fair value barely changes.
    # Asserting on k alone would be testing the parameterisation rather than
    # the relationship, and would fail on a fit that is entirely correct.
    b_mid = float(np.median(b))
    assert rel.k * b_mid**rel.beta == pytest.approx(2.5 * b_mid**0.85, rel=0.01)


def test_a_fitted_pair_becomes_an_ordinary_linkage():
    """The claim the whole module rests on: after compiling, nothing downstream
    needs to know this was ever a statistical pair."""
    a, b = cointegrated()
    rel = fit("synthetic", "AAA.NS", "BBB.NS", frame(a, b))
    linkage = compile_pair(spec(), rel, friction_bps=26.95)

    assert linkage.fair_value == "k * b ** beta"
    assert set(linkage.params) == {"k", "beta"}
    assert linkage.reference == "a"

    # And it evaluates: at prices drawn from the fitted relationship, the
    # measured spread is small.
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    b_price = Decimal("120.00")
    a_price = Decimal(str(rel.k * 120.0**rel.beta))
    observation = evaluate_linkage(
        linkage,
        {
            "a": Quote("AAA.NS", a_price, now),
            "b": Quote("BBB.NS", b_price, now),
        },
        SpreadHistory(),
        now=now,
    )
    assert abs(observation.spread_bps) < 1.0


def test_refitting_discards_stored_state():
    """Why the fit is compiled into params rather than kept beside them.

    A new hedge ratio means the accumulated percentile window and Kalman state
    describe a different quantity. Because the ratio lives in `params`, which
    the fingerprint covers, the store discards that state without anything
    having to remember to.
    """
    a, b = cointegrated(seed=3)
    first = compile_pair(spec(), fit("s", "AAA.NS", "BBB.NS", frame(a, b)), friction_bps=27)

    a2, b2 = cointegrated(beta=0.70, seed=4)
    second = compile_pair(
        spec(), fit("s", "AAA.NS", "BBB.NS", frame(a2, b2)), friction_bps=27
    )

    assert first.state_fingerprint != second.state_fingerprint


def test_friction_is_outside_the_fingerprint_even_for_pairs():
    a, b = cointegrated()
    rel = fit("s", "AAA.NS", "BBB.NS", frame(a, b))
    cheap = compile_pair(spec(), rel, friction_bps=4.0)
    dear = compile_pair(spec(), rel, friction_bps=26.95)
    assert cheap.state_fingerprint == dear.state_fingerprint


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_unrelated_pairs_are_refused_at_about_the_nominal_rate():
    """One draw proves nothing here, and that is the whole lesson.

    Engle-Granger at 5% calls roughly one unrelated pair in twenty
    cointegrated. Asserting on a single pair of random walks would pass or fail
    on the seed. What matters is the RATE -- because a catalogue of fifty pairs
    screened at 5% each is expected to hand back two or three relationships
    that do not exist.
    """
    admitted = 0
    for seed in range(40):
        a, b = independent(seed=seed)
        rel = fit("s", "AAA.NS", "BBB.NS", frame(a, b))
        if admit(spec(), rel, horizon=3.0, friction_bps=26.95).admitted:
            admitted += 1

    assert admitted <= 5, (
        f"{admitted}/40 unrelated random-walk pairs were admitted; the "
        f"uncorrected test should sit near 5%"
    )


def test_screening_the_family_removes_what_chance_put_there():
    """The correction, shown working on pairs that are all known to be noise."""
    from linkage.stat_pairs import bh_threshold

    pvalues = []
    for seed in range(40):
        a, b = independent(seed=seed)
        pvalues.append(fit("s", "AAA.NS", "BBB.NS", frame(a, b)).coint_pvalue)

    raw = sum(p < 0.05 for p in pvalues)
    threshold = bh_threshold(pvalues)
    corrected = sum(p <= threshold for p in pvalues) if threshold > 0 else 0

    assert corrected == 0, (
        f"{raw} of 40 unrelated pairs passed an uncorrected 5% screen and "
        f"{corrected} still passed after Benjamini-Hochberg"
    )


def test_a_real_relationship_too_small_to_pay_is_refused():
    """The pair that passes every statistical test and still cannot be traded.

    A 5 bps spread reverting perfectly is a genuine relationship and a
    guaranteed loss against 27 bps of friction.
    """
    a, b = cointegrated(resid_sd=0.0005, theta=0.4)
    rel = fit("s", "AAA.NS", "BBB.NS", frame(a, b))

    assert rel.ou.reverts          # the relationship is real
    assert rel.spread_sd_bps < 30  # and far too small to cover a round trip

    result = admit(spec(), rel, horizon=3.0, friction_bps=26.95)
    assert not result.admitted
    assert "friction" in result.reason


def test_an_edge_nobody_could_ever_verify_is_refused():
    """Positive expectancy is not the same as a checkable claim.

    Built directly rather than sampled, because the case is narrow: a spread
    that reverts strongly and is JUST wide enough to clear friction. What is
    left over after the round trip is real and positive and buried under a
    per-trade noise many times its size.
    """
    from dataclasses import replace

    a, b = cointegrated(resid_sd=0.02, theta=0.25)
    base = fit("s", "AAA.NS", "BBB.NS", frame(a, b))

    # Shrink the spread until 2 sigma barely covers a 26.95 bps round trip.
    marginal = replace(base, spread_sd_bps=29.0)
    edge = marginal.net_edge_at(ADMISSION_SIGMAS, 3.0, 26.95)
    assert 0 < edge < 5, f"fixture did not land on the margin: {edge:+.2f} bps"

    detect = marginal.trades_to_detect(ADMISSION_SIGMAS, 3.0, 26.95)
    assert detect > MAX_TRADES_TO_DETECT

    result = admit(spec(), marginal, horizon=3.0, friction_bps=26.95)
    assert not result.admitted
    assert "unfalsifiable" in result.reason


def test_a_good_pair_is_admitted():
    a, b = cointegrated(resid_sd=0.02, theta=0.25)
    rel = fit("s", "AAA.NS", "BBB.NS", frame(a, b))
    result = admit(spec(), rel, horizon=3.0, friction_bps=26.95)

    assert result.admitted, result.reason
    assert result.net_edge_bps > 0


def test_trades_to_detect_is_infinite_when_there_is_no_edge():
    a, b = cointegrated(resid_sd=0.0005, theta=0.4)
    rel = fit("s", "AAA.NS", "BBB.NS", frame(a, b))
    assert rel.trades_to_detect(2.0, 3.0, 26.95) == float("inf")


# ---------------------------------------------------------------------------
# Access, and the catalogue as written
# ---------------------------------------------------------------------------


def test_access_decides_what_an_edge_number_means():
    assert Access.FULL.category is Category.TRADEABLE
    assert Access.LONG_ONLY.category is Category.OBSERVATIONAL
    assert Access.NONE.category is Category.OBSERVATIONAL


def test_no_catalogue_pair_is_fully_tradeable():
    """Worth asserting rather than assuming.

    Not one of the 50 pairs has both legs shortable from a Groww account, so
    every statistical pair in this repo is observational by construction. If
    that ever changes, this test should fail and make someone look at it.
    """
    catalogue = load_catalogue(CATALOGUE)
    assert not [p for p in catalogue.pairs if p.access is Access.FULL]


def test_a_pair_against_itself_is_refused_at_load():
    with pytest.raises(ValueError, match="both legs"):
        spec(a="AAA.NS", b="AAA.NS")


def test_the_catalogue_validates():
    catalogue = load_catalogue(CATALOGUE)
    assert len(catalogue.pairs) == 50
    assert len(catalogue.symbols()) == 80
