"""Statistical pairs: relationships you cannot write down as a formula.

The linkages in `config.py` have a COMPUTABLE fair value -- a triangular FX
identity, an ADR ratio, a duty-adjusted conversion. You can state what one leg
should cost given the other.

These cannot. Nobody can say what Pepsi *should* cost given Coca-Cola. The
relationship, if there is one, has to be estimated from the data and then
tested, because the null hypothesis is that there is no relationship at all and
two trending series will look correlated regardless.

Three methodological commitments, each of which is the difference between a
result and a mirage:

CORRELATE RETURNS, NOT LEVELS. Any two series that both trend upward show a
high level-correlation. It measures that both went up over the period and
nothing else. Return correlation is the one that means something.

TEST COINTEGRATION ON LEVELS. That is the opposite convention and it is correct:
cointegration is precisely the claim that two non-stationary level series have a
stationary linear combination. Testing it on returns would test nothing.

REPORT HALF-LIFE. A pair can be beautifully cointegrated over a forty-day
reversion cycle and be useless on a 48-72 hour horizon. Half-life is what turns
"this relationship is real" into "this relationship is real AND reachable within
the holding period I actually have".
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint

from linkage.quality import ScreenReport, screen

# statsmodels is chatty about small samples and interpolated p-values; the
# sample sizes are reported per pair so the reader can judge for themselves.
warnings.filterwarnings("ignore", category=RuntimeWarning, module="statsmodels")
warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")

MIN_OBSERVATIONS = 250  # roughly one trading year


@dataclass
class PairProfile:
    """Everything measured about one pair."""

    pair_id: str
    symbol_a: str
    symbol_b: str
    start: date
    end: date
    observations: int

    return_corr: float
    rolling_corr_now: float
    rolling_corr_min: float
    rolling_corr_max: float

    coint_pvalue: float
    adf_pvalue: float
    hedge_ratio: float
    r_squared: float

    spread_sd_bps: float
    half_life_days: float | None
    current_z: float
    max_abs_z: float
    screen_report: ScreenReport | None = None

    @property
    def is_cointegrated(self) -> bool:
        """Engle-Granger at 5%. A p-value is not proof, it is a filter."""
        return self.coint_pvalue < 0.05

    @property
    def reachable_in_72h(self) -> bool:
        """Can the spread plausibly revert inside a three-day hold?

        Half-life is the time for a deviation to decay by half. Anything beyond
        about five days makes a 48-72h horizon a bet on luck rather than on
        reversion.
        """
        return self.half_life_days is not None and self.half_life_days <= 5

    @property
    def stability(self) -> str:
        """How much the relationship itself moves around."""
        swing = self.rolling_corr_max - self.rolling_corr_min
        if swing < 0.4:
            return "stable"
        if swing < 0.8:
            return "variable"
        return "unstable"

    @property
    def verdict(self) -> str:
        if self.observations < MIN_OBSERVATIONS:
            return "INSUFFICIENT HISTORY"
        if not self.is_cointegrated:
            return "NOT COINTEGRATED — correlation only, no tradeable spread"
        if not self.reachable_in_72h:
            return f"COINTEGRATED but slow — {self.half_life_days:.0f}d half-life"
        if self.stability == "unstable":
            return "COINTEGRATED but the relationship itself is unstable"
        return "COINTEGRATED and reverts within horizon"


def _half_life(spread: pd.Series) -> float | None:
    """Ornstein-Uhlenbeck half-life via an AR(1) fit on the spread.

    Regress the change in spread on its own lagged level. A negative coefficient
    means deviations pull back toward the mean, and the half-life follows from
    its magnitude. A non-negative coefficient means the spread diverges, and
    there is no half-life to report -- which is itself the answer.
    """
    lagged = spread.shift(1).dropna()
    delta = (spread - spread.shift(1)).dropna()
    lagged, delta = lagged.align(delta, join="inner")
    if len(lagged) < 30:
        return None

    model = sm.OLS(delta.values, sm.add_constant(lagged.values)).fit()
    lam = model.params[1]
    if lam >= 0:
        return None
    return float(-math.log(2) / lam)


def profile_pair(
    pair_id: str,
    symbol_a: str,
    symbol_b: str,
    prices: pd.DataFrame,
    *,
    rolling_window: int = 60,
) -> PairProfile:
    """Measure one pair from an aligned two-column price frame."""
    frame = prices[[symbol_a, symbol_b]].dropna()

    # Screen BEFORE anything is measured. Two bad prints out of 1239 once took
    # this pair's spread SD from 15 bps to 1851 bps -- see linkage/quality.py.
    frame, report = screen(frame)

    if len(frame) < 60:
        raise ValueError(f"{pair_id}: only {len(frame)} usable observations")

    a, b = frame[symbol_a], frame[symbol_b]

    # Returns for correlation. Levels for cointegration. See module docstring.
    returns = frame.pct_change(fill_method=None).dropna()
    return_corr = float(returns[symbol_a].corr(returns[symbol_b]))
    rolling = (
        returns[symbol_a].rolling(rolling_window).corr(returns[symbol_b]).dropna()
    )

    coint_p = float(coint(a, b)[1])

    # Hedge ratio on logs, so beta is an elasticity and is scale-free -- a
    # ratio fitted on raw prices silently encodes the price levels of the day
    # it was fitted.
    log_a, log_b = np.log(a), np.log(b)
    model = sm.OLS(log_a.values, sm.add_constant(log_b.values)).fit()
    beta = float(model.params[1])

    spread = log_a - (model.params[0] + beta * log_b)
    spread_sd = float(spread.std())
    z = (spread - spread.mean()) / spread.std()

    return PairProfile(
        pair_id=pair_id,
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        start=frame.index[0].date(),
        end=frame.index[-1].date(),
        observations=len(frame),
        return_corr=return_corr,
        rolling_corr_now=float(rolling.iloc[-1]) if len(rolling) else float("nan"),
        rolling_corr_min=float(rolling.min()) if len(rolling) else float("nan"),
        rolling_corr_max=float(rolling.max()) if len(rolling) else float("nan"),
        coint_pvalue=coint_p,
        adf_pvalue=float(adfuller(spread.values, autolag="AIC")[1]),
        hedge_ratio=beta,
        r_squared=float(model.rsquared),
        spread_sd_bps=spread_sd * 10_000,
        half_life_days=_half_life(spread),
        current_z=float(z.iloc[-1]),
        max_abs_z=float(z.abs().max()),
        screen_report=report,
    )
