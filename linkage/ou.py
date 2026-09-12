"""Ornstein-Uhlenbeck fitting, and the horizon gate.

A spread being three standard deviations wide is not a reason to act. It is a
reason to act only if it will come back *within the time you intend to hold it*.
Those are different claims, and conflating them is how a pairs strategy ends up
holding a position for two months that it sized for three days.

Model the spread as mean-reverting:

    dX = theta * (mu - X) dt + sigma dW

theta is the pull toward the mean. Half-life = ln(2)/theta is the time for a
deviation to decay by half. Fitted by regressing the change in spread on its own
lagged level -- an AR(1) in disguise.

The gate then asks a question the z-score alone cannot:

    of the current deviation, how much reverts inside my horizon,
    and does that exceed what it costs to trade?

On the 50 pairs profiled, half-lives ran 5 to 320 days against a 48-72 hour
horizon. Almost everything fails this gate, and that is the gate working.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


#: |t| on the AR(1) coefficient below which theta is indistinguishable from zero.
#:
#: This is 2.86, not the 2.0 a t-table suggests, and the difference is the whole
#: point. The regression below -- the change in the spread on its own lagged
#: level, with a constant -- IS the Dickey-Fuller regression, and under the null
#: of a random walk its t-statistic does not follow Student's t. It follows the
#: Dickey-Fuller tau_mu distribution, which sits well to the left, so a t-table
#: cut-off is far more permissive than it appears to be.
#:
#: Measured directly, on 3000 pure random walks per length (see
#: `tests/test_backtest_null.py`):
#:
#:     cut-off    admitted as "reverting"
#:      2.00              29%
#:      2.57              10%
#:      2.86               5%
#:      3.43               1%
#:
#: The value was 2.0 here, which meant that nearly a third of series with no
#: mean reversion whatsoever passed the check that exists to exclude them --
#: while the docstring below claimed the check was there to stop exactly that.
#: 2.86 is the conventional 5% critical value and the simulation agrees with it
#: to within 0.05.
MIN_THETA_TSTAT = 2.86


@dataclass(frozen=True)
class OUFit:
    theta: float          # mean-reversion speed, per period
    mu: float             # long-run mean of the spread
    sigma: float          # instantaneous volatility
    half_life: float | None  # in periods; None when the spread does not revert
    observations: int
    r_squared: float
    theta_tstat: float    # significance of theta; see `reverts`

    @property
    def reverts(self) -> bool:
        """Does this spread mean-revert, at all, distinguishably?

        A positive theta is not enough. Fit an AR(1) to a pure random walk and
        finite-sample noise hands back a small positive theta essentially every
        time -- which is then reported as a 600-day half-life and reads as a
        slow but real relationship. It is neither.

        So theta must also be statistically separable from zero. This is the
        same discipline as refusing to compute a z-score from eight samples:
        the honest answer to "does this revert?" is often "cannot tell", and
        that must be distinct from "yes, slowly".
        """
        return self.half_life is not None and abs(self.theta_tstat) >= MIN_THETA_TSTAT

    def decay_fraction(self, periods: float) -> float:
        """Fraction of a deviation expected to decay over `periods`.

        exp(-theta*t) is what remains, so 1 - that is what comes back.
        """
        if self.theta <= 0:
            return 0.0
        return 1.0 - math.exp(-self.theta * periods)

    def expected_reversion(self, deviation: float, periods: float) -> float:
        """How far the spread is expected to travel back, in the same units."""
        return deviation * self.decay_fraction(periods)


def fit_ou(spread: Sequence[float]) -> OUFit:
    """Fit theta, mu and sigma by AR(1) regression on the spread."""
    x = np.asarray(spread, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 30:
        raise ValueError(f"need 30+ observations to fit, got {len(x)}")

    lagged = x[:-1]
    delta = np.diff(x)

    # delta_t = a + b * x_{t-1} + e   ->   theta = -b,  mu = -a/b
    design = np.column_stack([np.ones_like(lagged), lagged])
    coeffs, residuals, *_ = np.linalg.lstsq(design, delta, rcond=None)
    a, b = float(coeffs[0]), float(coeffs[1])

    fitted = design @ coeffs
    ss_res = float(np.sum((delta - fitted) ** 2))
    ss_tot = float(np.sum((delta - delta.mean()) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    theta = -b
    mu = -a / b if b != 0 else float(x.mean())
    sigma = float(np.std(delta - fitted, ddof=2))

    # Standard error of the slope, so theta can be tested against zero rather
    # than merely observed to be positive.
    dof = len(delta) - 2
    centred = lagged - lagged.mean()
    denom = float(np.sum(centred**2))
    if dof > 0 and denom > 0:
        se_b = math.sqrt(ss_res / dof / denom)
        tstat = b / se_b if se_b > 0 else 0.0
    else:
        tstat = 0.0

    # b >= 0 means deviations grow rather than decay. There is no half-life to
    # report, and saying so is more useful than returning a large number.
    half_life = math.log(2) / theta if theta > 0 else None

    return OUFit(
        theta=theta,
        mu=mu,
        sigma=sigma,
        half_life=half_life,
        observations=len(x),
        r_squared=r_squared,
        theta_tstat=tstat,
    )


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reason: str
    expected_reversion_bps: float
    net_after_friction_bps: float


def horizon_gate(
    deviation_bps: float,
    fit: OUFit,
    *,
    horizon_periods: float,
    friction_bps: float,
    min_edge_bps: float = 0.0,
) -> GateResult:
    """Does enough of this deviation come back, soon enough, to beat the cost?

    `horizon_periods` is in the same units the fit was made in -- fit on daily
    spreads and a 72-hour horizon is 3.
    """
    if not fit.reverts:
        return GateResult(
            False, "spread does not mean-revert (theta <= 0)", 0.0, -friction_bps
        )

    expected = fit.expected_reversion(abs(deviation_bps), horizon_periods)
    net = expected - friction_bps

    if net < min_edge_bps:
        return GateResult(
            False,
            f"only {expected:.1f}bps reverts within {horizon_periods:g} periods "
            f"(half-life {fit.half_life:.1f}); {friction_bps:.1f}bps friction leaves "
            f"{net:+.1f}bps",
            expected,
            net,
        )

    return GateResult(
        True,
        f"{expected:.1f}bps expected back within {horizon_periods:g} periods, "
        f"{net:+.1f}bps after friction",
        expected,
        net,
    )
