"""Scheduled events: what they did last time, and what that is worth knowing.

    python -m linkage.events --symbol INFY.NS
    python -m linkage.events --universe            # every leg, upcoming only
    python -m linkage.events --calibrate INFY.NS

This is the event half of the system. The other half asks whether a spread is
unusually wide; this one asks whether something is about to happen that would
make it wider for a reason.

WHY EARNINGS RATHER THAN HEADLINES. The obvious build is a news feed and a
sentiment model. The reason this is not that: a projection with a confidence
number attached is only honest if the confidence was measured against outcomes,
and measuring it needs events that are DATED, LABELLED, and numerous enough to
count. Free news feeds give recent headlines with no history, so anything
trained on them would have a confidence figure that was asserted rather than
observed -- which is the exact failure this repo keeps refusing elsewhere.

Earnings are dated to the minute, carry a consensus estimate and a reported
figure, and come with fifty of them per instrument going back years. So the
surprise is measurable, the outcome is measurable, and the claim "a 10% beat
moves this stock 1.4% over three days, and here is how often that was within the
interval" is checkable. Headline sentiment can be added later; it cannot be
calibrated first.

WHAT THE CALIBRATION ACTUALLY SAYS, MEASURED. Two results come out of this, and
both argue against the feature as originally imagined.

The consensus surprise explains essentially nothing about the subsequent move:
R^2 of 0.03 and 0.001 on INFY and RELIANCE, p = 0.41 and 0.88. That is not a
broken fit, it is the expected one -- the estimate is public and the market has
already priced its own view of it. So "news gives a projected dip or rise" is,
for scheduled events at least, mostly not true, and the projection degenerates
to this symbol's typical event move.

And the interval under-covers. Walk-forward across four symbols it delivers
about 66% where it promises 80%, using the better of the two methods tried.
Small samples and fat tails, and no formula fixes it. So the nominal figure is
never reported alone: every projection carries its MEASURED coverage beside it,
and `well_calibrated` is False until the two agree. These intervals are for
suppression, not for sizing.

THE ABNORMAL RETURN, NOT THE RETURN. A stock that rose 3% on results the day the
index rose 2.8% did not move on results. Every move here is measured net of the
benchmark over the identical window, which is what makes it an event study
rather than a chart reading.

WHAT THIS IS FOR, PRACTICALLY. The most useful output is not the projection. It
is the SUPPRESSION: an earnings date inside the holding horizon is precisely the
`breaks_when` condition written against every pair in the catalogue. A spread
that diverges the day before results is not a spread reverting to a mean, and
alerting on it means entering a mean-reversion trade immediately before the
event most likely to end the relationship.
"""

from __future__ import annotations

import argparse
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

#: Trading days after the event the move is measured over. Matches the 48-72
#: hour horizon the rest of the system is built around.
DEFAULT_HORIZON_DAYS = 3

#: Events needed before a projection is offered at all. Below this the interval
#: is wider than anything it could usefully exclude, and a number would only
#: give the appearance of an answer.
MIN_EVENTS = 12

#: Nominal coverage of the reported interval. Reported alongside its MEASURED
#: coverage, because those two agreeing is the whole claim.
INTERVAL_CONFIDENCE = 0.80

#: Benchmark per market. An event study without one measures the index.
BENCHMARKS = {".NS": "^NSEI", ".BO": "^BSESN", ".L": "^FTSE", ".DE": "^GDAXI"}
DEFAULT_BENCHMARK = "^GSPC"


def could_report(symbol: str) -> bool:
    """Can this instrument have an earnings date at all?

    An FX cross, an index and a futures contract cannot, by construction.
    Asking yfinance anyway costs a network round trip each and returns
    "No earnings dates found, symbol may be delisted" -- which is both wrong
    and alarming, and on a 34-symbol universe produces sixteen lines of it at
    every startup. A company reports; a currency pair does not.

    ETFs cannot be excluded this way (GOLDBEES.NS looks exactly like an equity),
    so they are still queried and simply come back empty.
    """
    return not (symbol.endswith("=X") or symbol.endswith("=F") or symbol.startswith("^"))


def benchmark_for(symbol: str) -> str:
    for suffix, index in BENCHMARKS.items():
        if symbol.endswith(suffix):
            return index
    return DEFAULT_BENCHMARK


@dataclass(frozen=True)
class EarningsEvent:
    """One scheduled event, past or future."""

    symbol: str
    when: datetime
    eps_estimate: float | None
    reported_eps: float | None
    surprise_pct: float | None

    @property
    def is_past(self) -> bool:
        return self.reported_eps is not None and not math.isnan(self.reported_eps)

    @property
    def days_away(self) -> float:
        return (self.when - datetime.now(timezone.utc)).total_seconds() / 86400


@dataclass(frozen=True)
class Outcome:
    """A past event joined to what the stock did afterwards, net of the index."""

    event: EarningsEvent
    raw_move_pct: float
    benchmark_move_pct: float

    @property
    def abnormal_move_pct(self) -> float:
        return self.raw_move_pct - self.benchmark_move_pct


@dataclass(frozen=True)
class Projection:
    """A projected move, with the interval and the evidence for it."""

    symbol: str
    horizon_days: int
    n_events: int

    expected_move_pct: float       # signed, conditional on the surprise
    interval_low_pct: float
    interval_high_pct: float
    confidence: float

    typical_abs_move_pct: float    # median |abnormal move| across all events
    surprise_beta: float           # abnormal move per 1% of surprise
    surprise_r_squared: float
    surprise_pvalue: float

    measured_coverage: float | None  # what fraction of held-out events landed inside
    coverage_n: int

    @property
    def surprise_explains_anything(self) -> bool:
        """Does the consensus surprise carry information about the move?

        Usually it does not, and that is a real result rather than a broken
        fit: the estimate is public and the market has already priced its own
        expectation of it. Where this is False the projection degenerates to
        "this stock typically moves this much on results", which is still worth
        knowing and is a much weaker claim.
        """
        return self.surprise_pvalue < 0.05 and self.surprise_r_squared > 0.05

    @property
    def well_calibrated(self) -> bool:
        """Does the interval contain what it promises to contain?

        A projection whose 80% interval catches 45% of outcomes is not a
        projection, it is a decoration.
        """
        if self.measured_coverage is None:
            return False
        return abs(self.measured_coverage - self.confidence) <= 0.10

    def summary(self) -> str:
        lines = [
            f"  {self.symbol}   {self.n_events} past events, "
            f"{self.horizon_days}-day abnormal move",
            "",
            f"  typical move          {self.typical_abs_move_pct:>7.2f}%  "
            f"(median absolute, net of benchmark)",
            f"  projected             {self.expected_move_pct:>+7.2f}%",
            f"  {self.confidence:.0%} interval          "
            f"{self.interval_low_pct:>+7.2f}% .. {self.interval_high_pct:+.2f}%"
            + (
                f"   [really {self.measured_coverage:.0%}]"
                if self.measured_coverage is not None
                else ""
            ),
            "",
            f"  surprise beta         {self.surprise_beta:>+7.3f}% per 1% surprise",
            f"  R^2                   {self.surprise_r_squared:>7.3f}   "
            f"p={self.surprise_pvalue:.3f}",
        ]
        if self.measured_coverage is not None:
            lines.append(
                f"  measured coverage     {self.measured_coverage:>7.1%}  "
                f"of {self.coverage_n} held-out events "
                f"(promised {self.confidence:.0%})"
            )
        lines += [
            "",
            "  "
            + (
                "SURPRISE IS INFORMATIVE for this symbol."
                if self.surprise_explains_anything
                else "SURPRISE EXPLAINS NOTHING — the projection is just this "
                "symbol's typical event move."
            ),
        ]
        if self.measured_coverage is not None:
            lines.append(
                "  "
                + (
                    "INTERVAL IS CALIBRATED."
                    if self.well_calibrated
                    else f"INTERVAL IS NOT CALIBRATED — it promises "
                    f"{self.confidence:.0%} and delivers "
                    f"{self.measured_coverage:.0%}. Do not size on it."
                )
            )
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def _yf():
    import yfinance as yf

    cache = (
        Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
        / "linkage-monitor"
        / "yf-cache"
    )
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache))
    return yf


def fetch_events(symbol: str, *, limit: int = 60) -> list[EarningsEvent]:
    """Historical and scheduled earnings dates with their consensus surprise."""
    yf = _yf()
    try:
        frame = yf.Ticker(symbol).get_earnings_dates(limit=limit)
    except Exception:  # noqa: BLE001 -- absent data is the common case, not an error
        return []
    if frame is None or frame.empty:
        return []

    def _clean(value) -> float | None:
        if value is None:
            return None
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else f

    events = []
    for when, row in frame.iterrows():
        ts = when.to_pydatetime()
        events.append(
            EarningsEvent(
                symbol=symbol,
                when=ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc),
                eps_estimate=_clean(row.get("EPS Estimate")),
                reported_eps=_clean(row.get("Reported EPS")),
                surprise_pct=_clean(row.get("Surprise(%)")),
            )
        )
    return sorted(events, key=lambda e: e.when)


def fetch_prices(symbols: list[str], years: int = 6) -> pd.DataFrame:
    yf = _yf()
    frame = yf.download(
        symbols,
        period=f"{years}y",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    out = {}
    for symbol in symbols:
        try:
            out[symbol] = frame[symbol]["Close"]
        except KeyError:
            continue
    return pd.DataFrame(out).dropna(how="all")


# ---------------------------------------------------------------------------
# The study
# ---------------------------------------------------------------------------


def measure(
    events: list[EarningsEvent],
    prices: pd.Series,
    benchmark: pd.Series,
    *,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> list[Outcome]:
    """Join each past event to the abnormal move over the following horizon.

    The entry price is the last close STRICTLY BEFORE the event. Using the
    close of the event day would be using the reaction to predict the reaction
    on the roughly half of these that are announced before the close.
    """
    outcomes: list[Outcome] = []
    index = prices.index

    for event in events:
        if not event.is_past or event.surprise_pct is None:
            continue

        day = pd.Timestamp(event.when.date())
        before = index[index < day]
        after = index[index >= day]
        if len(before) == 0 or len(after) <= horizon_days:
            continue

        entry_ts, exit_ts = before[-1], after[horizon_days - 1]
        try:
            p0, p1 = float(prices.loc[entry_ts]), float(prices.loc[exit_ts])
            b0, b1 = float(benchmark.loc[entry_ts]), float(benchmark.loc[exit_ts])
        except KeyError:
            continue
        if not all(np.isfinite([p0, p1, b0, b1])) or p0 <= 0 or b0 <= 0:
            continue

        outcomes.append(
            Outcome(
                event=event,
                raw_move_pct=(p1 / p0 - 1) * 100,
                benchmark_move_pct=(b1 / b0 - 1) * 100,
            )
        )
    return outcomes


def _prediction_interval(
    x: np.ndarray, y: np.ndarray, x_new: float, confidence: float
) -> tuple[float, float]:
    """Half-widths of an OLS prediction interval around a new point.

        se = s * sqrt(1 + 1/n + (x_new - xbar)^2 / Sxx)

    The three terms are the residual scatter, the uncertainty in the fitted
    mean, and the extra uncertainty from projecting away from the centre of the
    data. Empirical residual quantiles capture only the first, and from twelve
    points an 80% quantile pair is biased inward besides -- extreme quantiles
    of small samples sit too close together. Measured walk-forward across four
    symbols, this method covers 66% against 57% for raw residual quantiles.

    Neither reaches its nominal 80%. Event returns are fat-tailed and the
    samples are small, and no choice of formula fixes that; the honest response
    is to MEASURE the coverage and report it instead of the promise. See the
    module docstring.
    """
    from scipy import stats

    n = len(x)
    if n < 3:
        return (float("nan"), float("nan"))
    residuals = y - np.polyval(np.polyfit(x, y, 1), x)
    s = math.sqrt(float(np.sum(residuals**2)) / (n - 2))
    xbar = float(np.mean(x))
    sxx = float(np.sum((x - xbar) ** 2))
    leverage = ((x_new - xbar) ** 2 / sxx) if sxx > 0 else 0.0
    se = s * math.sqrt(1 + 1 / n + leverage)
    t = float(stats.t.ppf(1 - (1 - confidence) / 2, n - 2))
    return (-t * se, t * se)


def _fit_surprise(outcomes: list[Outcome]) -> tuple[float, float, float, float]:
    """Regress abnormal move on surprise. Returns (alpha, beta, r2, p)."""
    import statsmodels.api as sm

    x = np.array([o.event.surprise_pct for o in outcomes], dtype=float)
    y = np.array([o.abnormal_move_pct for o in outcomes], dtype=float)
    model = sm.OLS(y, sm.add_constant(x)).fit()
    return (
        float(model.params[0]),
        float(model.params[1]),
        float(model.rsquared),
        float(model.pvalues[1]),
    )


def _coverage(
    outcomes: list[Outcome], *, confidence: float, min_train: int = MIN_EVENTS
) -> tuple[float | None, int]:
    """Walk-forward coverage: fit on the past, predict the next, count hits.

    This is the only honest way to ask whether the interval means anything. An
    interval fitted on all the data and then checked against the same data will
    report roughly its nominal coverage whatever the model does, because the
    residual quantiles ARE the interval by construction.
    """
    hits, checked = 0, 0
    for i in range(min_train, len(outcomes)):
        train, test = outcomes[:i], outcomes[i]
        alpha, beta, _, _ = _fit_surprise(train)
        x = np.array([o.event.surprise_pct for o in train], dtype=float)
        y = np.array([o.abnormal_move_pct for o in train], dtype=float)
        low, high = _prediction_interval(
            x, y, test.event.surprise_pct, confidence
        )
        centre = alpha + beta * test.event.surprise_pct
        if centre + low <= test.abnormal_move_pct <= centre + high:
            hits += 1
        checked += 1
    return (hits / checked if checked else None), checked


def project(
    symbol: str,
    outcomes: list[Outcome],
    *,
    surprise_pct: float = 0.0,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    confidence: float = INTERVAL_CONFIDENCE,
) -> Projection | None:
    """Project the move for a given surprise, with a measured interval."""
    if len(outcomes) < MIN_EVENTS:
        return None

    alpha, beta, r2, pvalue = _fit_surprise(outcomes)
    moves = np.array([o.abnormal_move_pct for o in outcomes])
    x = np.array([o.event.surprise_pct for o in outcomes], dtype=float)

    centre = alpha + beta * surprise_pct
    low, high = _prediction_interval(x, moves, surprise_pct, confidence)
    coverage, coverage_n = _coverage(outcomes, confidence=confidence)

    return Projection(
        symbol=symbol,
        horizon_days=horizon_days,
        n_events=len(outcomes),
        expected_move_pct=float(centre),
        interval_low_pct=float(centre + low),
        interval_high_pct=float(centre + high),
        confidence=confidence,
        typical_abs_move_pct=float(np.median(np.abs(moves))),
        surprise_beta=float(beta),
        surprise_r_squared=float(r2),
        surprise_pvalue=float(pvalue),
        measured_coverage=coverage,
        coverage_n=coverage_n,
    )


def study(
    symbol: str,
    *,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    years: int = 6,
    surprise_pct: float = 0.0,
) -> tuple[list[Outcome], Projection | None]:
    """Fetch, measure and project in one call."""
    events = fetch_events(symbol)
    if not events:
        return [], None

    index = benchmark_for(symbol)
    prices = fetch_prices([symbol, index], years=years)
    if symbol not in prices or index not in prices:
        return [], None

    outcomes = measure(
        events,
        prices[symbol].dropna(),
        prices[index].dropna(),
        horizon_days=horizon_days,
    )
    return outcomes, project(
        symbol,
        outcomes,
        surprise_pct=surprise_pct,
        horizon_days=horizon_days,
    )


# ---------------------------------------------------------------------------
# The part that changes what the scanner does
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventWindow:
    """A scheduled event close enough to matter to an open position."""

    symbol: str
    when: datetime
    days_away: float

    def describe(self) -> str:
        return f"{self.symbol} reports in {self.days_away:.1f}d ({self.when:%Y-%m-%d})"


class EventCalendar:
    """Upcoming scheduled events, and whether a linkage sits in front of one.

    Built once at startup and consulted per cycle. Refreshing it inside the
    scan loop would add a network call per linkage per cycle to answer a
    question whose answer changes once a quarter.
    """

    def __init__(self, events: dict[str, list[EarningsEvent]]):
        self._events = events

    @classmethod
    def build(cls, symbols: list[str]) -> EventCalendar:
        import logging

        # yfinance logs an error per symbol with no earnings, which for an ETF
        # is simply the answer rather than a fault.
        yf_log = logging.getLogger("yfinance")
        previous = yf_log.level
        yf_log.setLevel(logging.CRITICAL)
        try:
            return cls(
                {
                    symbol: fetch_events(symbol)
                    for symbol in symbols
                    if could_report(symbol)
                }
            )
        finally:
            yf_log.setLevel(previous)

    def upcoming(self, symbol: str, *, within_days: float) -> EventWindow | None:
        for event in self._events.get(symbol, []):
            days = event.days_away
            if 0 <= days <= within_days:
                return EventWindow(symbol, event.when, days)
        return None

    def blocking(self, symbols: list[str], *, within_days: float) -> list[EventWindow]:
        """Every leg with an event inside the horizon.

        This is the suppression rule, and it is the most valuable thing in this
        module. Every pair in the catalogue carries a `breaks_when` clause, and
        for an equity pair that clause is almost always a results announcement.
        A spread that widens the day before earnings is not a spread that is
        about to revert -- it is the relationship being tested. Entering a
        mean-reversion trade immediately in front of the event most likely to
        end the relationship is the single most expensive thing this system
        could do, and it would look like a perfectly ordinary alert.
        """
        found = [self.upcoming(s, within_days=within_days) for s in symbols]
        return [window for window in found if window is not None]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Event study on scheduled events.")
    parser.add_argument("--symbol", help="one symbol to study")
    parser.add_argument(
        "--universe", action="store_true", help="upcoming events across every leg"
    )
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_DAYS)
    parser.add_argument("--years", type=int, default=6)
    parser.add_argument(
        "--surprise",
        type=float,
        default=0.0,
        help="project for this consensus surprise, in percent",
    )
    args = parser.parse_args()

    if args.universe:
        from linkage.scan import default_universes, load_universes

        universe = load_universes(default_universes())
        symbols = sorted(universe.symbols_for("yfinance"))
        print(f"\nchecking {len(symbols)} symbols for scheduled events...\n")
        calendar = EventCalendar.build(symbols)
        found = 0
        for symbol in symbols:
            window = calendar.upcoming(symbol, within_days=14)
            if window:
                print(f"  {window.describe()}")
                found += 1
        print(f"\n  {found} of {len(symbols)} report within 14 days.\n")
        return

    if not args.symbol:
        raise SystemExit("pass --symbol or --universe")

    print(f"\nstudying {args.symbol} against {benchmark_for(args.symbol)}...")
    outcomes, projection = study(
        args.symbol,
        horizon_days=args.horizon,
        years=args.years,
        surprise_pct=args.surprise,
    )
    if projection is None:
        raise SystemExit(
            f"  {len(outcomes)} usable events — need {MIN_EVENTS} before a "
            f"projection means anything.\n"
        )
    print()
    print(projection.summary())


if __name__ == "__main__":
    main()
