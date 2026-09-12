"""The three detectors, tested against data whose answer is known in advance.

Synthetic rather than market data throughout: the point is to prove the maths
recovers a parameter it was given, which is impossible to check against a series
whose true parameters nobody knows.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from linkage.kalman import KalmanHedge
from linkage.ou import fit_ou, horizon_gate
from linkage.thresholds import EmpiricalThreshold


# ── Kalman ──────────────────────────────────────────────────────────────────

def test_kalman_recovers_a_static_hedge_ratio():
    rng = np.random.default_rng(7)
    x = np.cumsum(rng.normal(0, 1, 600)) + 100
    y = 2.5 * x + rng.normal(0, 0.05, 600)

    kf = KalmanHedge(delta=1e-5, observation_var=0.0025)
    for yi, xi in zip(y, x):
        step = kf.update(yi, xi)

    assert step.beta == pytest.approx(2.5, abs=0.05)


def test_kalman_tracks_a_hedge_ratio_that_moves():
    """The whole reason not to use OLS.

    Beta shifts from 2.0 to 3.0 halfway through. A static fit would split the
    difference and report a permanent residual on both halves; the filter
    follows it.
    """
    rng = np.random.default_rng(11)
    x = np.cumsum(rng.normal(0, 1, 1200)) + 200
    beta = np.where(np.arange(1200) < 600, 2.0, 3.0)
    y = beta * x + rng.normal(0, 0.05, 1200)

    kf = KalmanHedge(delta=1e-4, observation_var=0.0025)
    for yi, xi in zip(y[:600], x[:600]):
        kf.update(yi, xi)
    before = kf.state[0]

    for yi, xi in zip(y[600:], x[600:]):
        kf.update(yi, xi)
    after = kf.state[0]

    assert before == pytest.approx(2.0, abs=0.1)
    assert after == pytest.approx(3.0, abs=0.1)


def test_kalman_innovation_is_standardised():
    """z should behave like a standard normal on well-specified data.

    This is the property that makes the innovation usable as a threshold
    without a rolling window underneath it.
    """
    rng = np.random.default_rng(3)
    x = np.cumsum(rng.normal(0, 1, 3000)) + 100
    y = 1.5 * x + rng.normal(0, 0.1, 3000)

    kf = KalmanHedge(delta=1e-6, observation_var=0.01)
    zs = [kf.update(yi, xi).z for yi, xi in zip(y, x)][500:]  # discard burn-in

    assert abs(float(np.mean(zs))) < 0.2
    assert 0.6 < float(np.std(zs)) < 1.6


def test_kalman_uncertainty_shrinks_as_it_learns():
    """A fresh filter is ignorant and should say so."""
    rng = np.random.default_rng(5)
    x = np.cumsum(rng.normal(0, 1, 400)) + 100
    y = 2.0 * x + rng.normal(0, 0.05, 400)

    kf = KalmanHedge(delta=1e-5, observation_var=0.0025)
    first = kf.update(y[0], x[0])
    for yi, xi in zip(y[1:], x[1:]):
        last = kf.update(yi, xi)

    assert last.beta_var < first.beta_var


# ── Ornstein-Uhlenbeck ──────────────────────────────────────────────────────

def _ou_series(theta: float, mu: float, sigma: float, n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = np.empty(n)
    x[0] = mu
    for i in range(1, n):
        x[i] = x[i - 1] + theta * (mu - x[i - 1]) + rng.normal(0, sigma)
    return x


def test_ou_recovers_a_known_half_life():
    theta = 0.1  # half-life = ln2/0.1 ~ 6.93 periods
    fit = fit_ou(_ou_series(theta, 0.0, 0.05, 4000, seed=13))

    assert fit.reverts
    assert fit.half_life == pytest.approx(math.log(2) / theta, rel=0.2)
    assert fit.mu == pytest.approx(0.0, abs=0.02)


def test_random_walk_is_not_reported_as_slow_reversion():
    """The failure mode this guard exists for.

    Fit an AR(1) to a pure random walk and finite-sample noise hands back a
    small positive theta almost every time -- here a 687-day half-life with an
    R-squared of 0.0005. Reported naively that reads as a slow but genuine
    relationship. Requiring theta to be separable from zero makes "cannot tell"
    distinct from "yes, slowly".
    """
    rng = np.random.default_rng(17)
    fit = fit_ou(np.cumsum(rng.normal(0, 1, 2000)))

    assert not fit.reverts
    assert abs(fit.theta_tstat) < 2.0
    assert fit.r_squared < 0.01


def test_ou_decay_fraction_matches_the_half_life():
    fit = fit_ou(_ou_series(0.1, 0.0, 0.05, 4000, seed=19))
    # By definition, half the deviation is gone after one half-life.
    assert fit.decay_fraction(fit.half_life) == pytest.approx(0.5, abs=0.02)


# ── Horizon gate ────────────────────────────────────────────────────────────

def test_gate_rejects_a_wide_spread_that_reverts_too_slowly():
    """The case the z-score alone gets wrong.

    A 200bps deviation on a 60-day half-life looks spectacular and returns
    about 3% of itself inside three days -- less than the cost of trading it.
    """
    slow = fit_ou(_ou_series(0.0116, 0.0, 0.05, 4000, seed=23))  # ~60d half-life
    result = horizon_gate(
        200.0, slow, horizon_periods=3, friction_bps=27, min_edge_bps=10
    )
    assert not result.passed
    assert "reverts within" in result.reason


def test_gate_accepts_a_fast_reverting_spread():
    fast = fit_ou(_ou_series(0.35, 0.0, 0.05, 4000, seed=29))  # ~2d half-life
    result = horizon_gate(
        200.0, fast, horizon_periods=3, friction_bps=27, min_edge_bps=10
    )
    assert result.passed
    assert result.net_after_friction_bps > 10


def test_gate_rejects_a_non_reverting_spread_outright():
    rng = np.random.default_rng(31)
    walk = fit_ou(np.cumsum(rng.normal(0, 1, 2000)))
    result = horizon_gate(500.0, walk, horizon_periods=3, friction_bps=27)
    assert not result.passed
    assert "does not mean-revert" in result.reason
    assert result.expected_reversion_bps == 0.0


# ── Empirical thresholds ────────────────────────────────────────────────────

def test_threshold_needs_history_before_it_scores():
    t = EmpiricalThreshold()
    t.append(1.0)
    assert t.score(5.0) is None


def test_threshold_flags_both_tails():
    t = EmpiricalThreshold(warn_percentile=90, alert_percentile=99)
    rng = np.random.default_rng(37)
    for v in rng.normal(0, 1, 500):
        t.append(float(v))

    assert t.score(4.0).exceeds_alert
    assert t.score(-4.0).exceeds_alert
    assert not t.score(0.0).exceeds_warn


def test_fat_tails_break_the_sigma_promise():
    """The reason this module exists.

    Student-t with 3 degrees of freedom is a realistic stand-in for a spread
    series. A normal distribution promises |z| > 3 on 0.27% of observations;
    the observed rate here is several times that. A detector set at 3 sigma
    expecting one alert a year gets many.
    """
    t = EmpiricalThreshold(window=20_000)
    rng = np.random.default_rng(41)
    for v in rng.standard_t(df=3, size=20_000):
        t.append(float(v))

    observed, normal_implied = t.sigma_lie()
    assert observed > normal_implied * 2
    assert normal_implied == pytest.approx(0.0027, abs=0.0001)


def test_percentile_is_measured_against_history_not_assumption():
    t = EmpiricalThreshold()
    for v in range(100):
        t.append(float(v))

    reading = t.score(95.0)
    assert reading.percentile == pytest.approx(95.0, abs=1.0)
    assert reading.tail_probability == pytest.approx(0.10, abs=0.03)
