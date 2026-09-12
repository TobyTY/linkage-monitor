"""Estimating conversion constants instead of asserting them.

An ADR ratio, an ETF's units-per-gram, an index divisor -- these are all
constants a config file is tempted to state. Stating them is how this project
would quietly fail: a ratio that is 3% stale produces a permanent 3% "spread"
that never mean-reverts, sits far from its own rolling mean, and looks exactly
like a standing arbitrage. The z-score would be well behaved. The number would
be wrong.

Worse, the failure is silent and durable. A stale constant does not throw; it
just moves the whole distribution, and every alert it generates is confidently
about nothing.

So: fit the constant against history and report how well it fits. The residual
standard deviation is the interesting output, not the ratio -- a linkage whose
residuals are tight is a real relationship, and one whose residuals are wide is
two prices that happen to be in the same file.

    python -m linkage.calibrate --linkage infy_adr
    python -m linkage.calibrate --all
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass
from datetime import timezone
from decimal import Decimal
from pathlib import Path

from linkage.config import LinkageConfig, Universe, load_universe
from linkage.formula import evaluate
from linkage.providers.base import MarketDataProvider
from linkage.providers.yfinance_provider import YFinanceProvider

DEFAULT_UNIVERSE = Path(__file__).resolve().parent.parent / "config" / "universe.yaml"


@dataclass
class Fit:
    """The result of fitting one scaling constant."""

    linkage_id: str
    param: str
    asserted: float
    estimated: float
    samples: int
    residual_sd_bps: float
    mean_abs_residual_bps: float

    @property
    def drift_pct(self) -> float:
        if self.asserted == 0:
            return float("inf")
        return (self.estimated / self.asserted - 1) * 100

    @property
    def verdict(self) -> str:
        """Is the asserted constant good enough to keep?

        The threshold is deliberately tight. A 1% error in a conversion constant
        is a 100bps permanent offset, and the whole system is trying to resolve
        gaps of tens of basis points.
        """
        if abs(self.drift_pct) < 0.5:
            return "asserted value holds"
        if abs(self.drift_pct) < 3:
            return "DRIFTED — replace it"
        return "WRONG — the asserted value is manufacturing a fake gap"


def _aligned_closes(
    provider: MarketDataProvider, symbols: list[str], days: int
) -> dict[str, dict]:
    """Daily closes keyed by date, per symbol, intersected across symbols.

    Daily rather than intraday on purpose: NSE and NYSE do not overlap, so
    intraday bars compare prices struck hours apart and the "gap" is mostly the
    overnight move. Daily closes are still struck at different times, which is
    why the residual spread is reported rather than swept under a number.
    """
    series: dict[str, dict] = {}
    for symbol in symbols:
        bars = provider.bars(symbol, "1d", days)
        series[symbol] = {
            bar.ts.astimezone(timezone.utc).date(): bar.close for bar in bars
        }

    common = set.intersection(*(set(s) for s in series.values())) if series else set()
    return {sym: {d: v for d, v in s.items() if d in common} for sym, s in series.items()}


def fit_param(
    linkage: LinkageConfig,
    param: str,
    provider: MarketDataProvider,
    *,
    days: int = 180,
) -> Fit:
    """Fit one multiplicative constant by the ratio of medians.

    Median rather than mean: an ADR pair over six months will contain at least
    one day where a corporate action, a data glitch or a holiday mismatch throws
    a 40% outlier, and a mean would absorb it into the estimate. The median
    ignores it.
    """
    if param not in linkage.params:
        raise KeyError(f"{linkage.id} has no param {param!r}")

    symbols = [leg.symbol for leg in linkage.legs.values()]
    closes = _aligned_closes(provider, symbols, days)
    dates = sorted(next(iter(closes.values())).keys()) if closes else []
    if len(dates) < 30:
        raise ValueError(
            f"{linkage.id}: only {len(dates)} aligned days; need 30+ to fit"
        )

    asserted = float(linkage.params[param])
    ratios: list[float] = []
    for date in dates:
        names: dict[str, object] = {
            leg_name: closes[leg.symbol][date] for leg_name, leg in linkage.legs.items()
        }
        # Evaluate with the constant neutralised, then read off what value of it
        # would have made fair value equal the reference on that day.
        names.update(linkage.params)
        names[param] = 1.0
        unscaled = evaluate(linkage.fair_value, names)
        reference = closes[linkage.legs[linkage.reference].symbol][date]
        if unscaled == 0:
            continue
        # fair = unscaled * k  (param multiplies) or unscaled / k (param divides).
        # Detect orientation by which direction moves fair toward reference.
        implied_mul = float(reference / unscaled)
        implied_div = float(unscaled / reference)
        ratios.append(implied_mul if abs(implied_mul - asserted) < abs(implied_div - asserted) else implied_div)

    estimated = statistics.median(ratios)

    residuals_bps: list[float] = []
    for date in dates:
        names = {
            leg_name: closes[leg.symbol][date] for leg_name, leg in linkage.legs.items()
        }
        names.update(linkage.params)
        names[param] = estimated
        fair = evaluate(linkage.fair_value, names)
        reference = closes[linkage.legs[linkage.reference].symbol][date]
        if reference:
            residuals_bps.append(float((reference - fair) / reference) * 10_000)

    return Fit(
        linkage_id=linkage.id,
        param=param,
        asserted=asserted,
        estimated=estimated,
        samples=len(dates),
        residual_sd_bps=statistics.stdev(residuals_bps) if len(residuals_bps) > 1 else 0.0,
        mean_abs_residual_bps=statistics.fmean(abs(r) for r in residuals_bps),
    )


def report(fit: Fit) -> str:
    return (
        f"  {fit.linkage_id:<14} {fit.param:<16}\n"
        f"      asserted {fit.asserted:>12.6f}   estimated {fit.estimated:>12.6f}"
        f"   drift {fit.drift_pct:+7.2f}%\n"
        f"      {fit.samples} days   residual sd {fit.residual_sd_bps:8.1f} bps"
        f"   mean |resid| {fit.mean_abs_residual_bps:7.1f} bps\n"
        f"      -> {fit.verdict}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fit conversion constants against history."
    )
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--linkage", help="fit one linkage; omit with --all")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args()

    universe: Universe = load_universe(args.universe)
    provider = YFinanceProvider()

    targets = (
        universe.linkages
        if args.all
        else [universe.by_id(args.linkage)]
        if args.linkage
        else []
    )
    if not targets:
        raise SystemExit("pass --linkage <id> or --all")

    print(f"\nFitting against {args.days} days of daily closes\n")
    for linkage in targets:
        if not linkage.params:
            print(f"  {linkage.id:<14} no constants to fit\n")
            continue
        for param in linkage.params:
            try:
                print(report(fit_param(linkage, param, provider, days=args.days)))
            except (ValueError, KeyError) as exc:
                print(f"  {linkage.id:<14} {param:<16} could not fit: {exc}\n")


if __name__ == "__main__":
    main()
