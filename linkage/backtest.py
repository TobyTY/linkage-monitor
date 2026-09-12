"""Replay history through the detector and score the alerts it would have fired.

    python -m linkage.backtest --pair gold_etf_pair
    python -m linkage.backtest --pair gold_etf_pair --horizon 3 --years 5

This answers the only question that matters about an alerting system: were the
alerts any good? Watching it live for a month gives you three alerts and no
statistics. Replaying five years gives you a sample.

Two things make this a backtest rather than a demonstration:

NOTHING USES DATA IT WOULD NOT HAVE HAD. The Kalman filter is causal by
construction -- it only ever sees the past. The OU fit and the threshold are
recomputed on a TRAILING window at every step, never once on the full sample.
Fitting the half-life on all five years and then "testing" on those same five
years is the most common way a pairs backtest lies, and it lies in the
flattering direction.

EVERY ALERT IS SCORED AGAINST A BASELINE. The relevant number is not "did the
spread narrow after an alert" -- spreads narrow after most days, because they
are mean-reverting series. It is "did it narrow MORE than it does on an ordinary
day". An alerting rule that cannot beat entering at random adds nothing except
confidence.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from linkage.config import load_universe
from linkage.ou import fit_ou, horizon_gate
from linkage.quality import screen
from linkage.thresholds import EmpiricalThreshold

UNIVERSE = Path(__file__).resolve().parent.parent / "config" / "universe.yaml"

#: Trailing window used to refit the OU process and the threshold each step.
FIT_WINDOW = 250

#: Observations before the detector is allowed to say anything at all.
WARMUP = 300


@dataclass
class Alert:
    when: date
    spread_bps: float
    z: float
    half_life: float
    predicted_reversion_bps: float
    predicted_net_bps: float
    actual_move_bps: float      # how much |spread| actually shrank over horizon
    actual_net_bps: float       # after friction

    @property
    def reverted(self) -> bool:
        return self.actual_move_bps > 0

    @property
    def profitable(self) -> bool:
        return self.actual_net_bps > 0


@dataclass
class BacktestResult:
    pair_id: str
    observations: int
    alerts: list[Alert]
    baseline_mean_move_bps: float
    baseline_n: int
    friction_bps: float
    horizon: int

    @property
    def hit_rate(self) -> float:
        if not self.alerts:
            return float("nan")
        return sum(a.reverted for a in self.alerts) / len(self.alerts)

    @property
    def profit_rate(self) -> float:
        if not self.alerts:
            return float("nan")
        return sum(a.profitable for a in self.alerts) / len(self.alerts)

    @property
    def mean_move_bps(self) -> float:
        if not self.alerts:
            return float("nan")
        return float(np.mean([a.actual_move_bps for a in self.alerts]))

    @property
    def mean_net_bps(self) -> float:
        if not self.alerts:
            return float("nan")
        return float(np.mean([a.actual_net_bps for a in self.alerts]))

    @property
    def edge_over_baseline_bps(self) -> float:
        """The number that decides whether the alerting rule is worth anything."""
        return self.mean_move_bps - self.baseline_mean_move_bps

    @property
    def verdict(self) -> str:
        if not self.alerts:
            return "NO ALERTS — the rule never fired; nothing to evaluate"
        if len(self.alerts) < 10:
            return f"ONLY {len(self.alerts)} ALERTS — too few to conclude anything"
        if self.edge_over_baseline_bps <= 0:
            return "NO EDGE — alerts did no better than entering on a random day"
        if self.mean_net_bps <= 0:
            return "BEATS BASELINE but loses to friction"
        return "BEATS BASELINE and survives friction"


def _prices(symbols: list[str], years: int) -> pd.DataFrame:
    import yfinance as yf

    cache = (
        Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
        / "linkage-monitor"
        / "yf-cache"
    )
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache))
    frame = yf.download(
        symbols,
        period=f"{years}y",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    return pd.DataFrame({s: frame[s]["Close"] for s in symbols}).dropna()


def run(
    pair_id: str,
    symbol_a: str,
    symbol_b: str,
    *,
    years: int,
    horizon: int,
    friction_bps: float,
    alert_percentile: float,
) -> BacktestResult:
    raw = _prices([symbol_a, symbol_b], years)
    frame, report = screen(raw)
    print(f"  data: {report.summary()}")

    spread = (np.log(frame[symbol_a]) - np.log(frame[symbol_b])) * 10_000
    values = spread.values
    dates = spread.index

    threshold = EmpiricalThreshold(window=FIT_WINDOW, alert_percentile=alert_percentile)
    for v in values[:WARMUP]:
        threshold.append(float(v))

    alerts: list[Alert] = []
    baseline_moves: list[float] = []
    cooldown_until = -1

    for i in range(WARMUP, len(values) - horizon):
        current = float(values[i])
        window = values[i - FIT_WINDOW : i]  # strictly the past

        # Baseline: the move from EVERY eligible day, alert or not. This is what
        # an alert has to beat.
        shrink = abs(current) - abs(float(values[i + horizon]))
        baseline_moves.append(shrink)

        reading = threshold.score(current)
        threshold.append(current)
        if reading is None or not reading.exceeds_alert or i < cooldown_until:
            continue

        try:
            fit = fit_ou(window)
        except ValueError:
            continue
        if not fit.reverts:
            continue

        gate = horizon_gate(
            current - float(np.median(window)),
            fit,
            horizon_periods=horizon,
            friction_bps=friction_bps,
        )
        if not gate.passed:
            continue

        sd = float(np.std(window, ddof=1))
        alerts.append(
            Alert(
                when=dates[i].date(),
                spread_bps=current,
                z=(current - float(np.mean(window))) / sd if sd else 0.0,
                half_life=fit.half_life,
                predicted_reversion_bps=gate.expected_reversion_bps,
                predicted_net_bps=gate.net_after_friction_bps,
                actual_move_bps=shrink,
                actual_net_bps=shrink - friction_bps,
            )
        )
        cooldown_until = i + horizon  # do not re-enter inside an open position

    return BacktestResult(
        pair_id=pair_id,
        observations=len(values),
        alerts=alerts,
        baseline_mean_move_bps=float(np.mean(baseline_moves)) if baseline_moves else 0.0,
        baseline_n=len(baseline_moves),
        friction_bps=friction_bps,
        horizon=horizon,
    )


def report(result: BacktestResult) -> str:
    lines = [
        "",
        f"  {result.pair_id}   {result.observations} observations, "
        f"{result.horizon}-day horizon, {result.friction_bps:.1f} bps friction",
        "",
    ]
    if result.alerts:
        lines += [
            "  date          spread      z   half-life   predicted    actual    net",
            "  " + "-" * 68,
        ]
        for a in result.alerts[:20]:
            lines.append(
                f"  {a.when}  {a.spread_bps:>8.1f}  {a.z:>+5.2f}   "
                f"{a.half_life:>6.1f}d   {a.predicted_reversion_bps:>+8.1f}  "
                f"{a.actual_move_bps:>+8.1f}  {a.actual_net_bps:>+6.1f}"
            )
        if len(result.alerts) > 20:
            lines.append(f"  ... {len(result.alerts) - 20} more")
        lines.append("")

    lines += [
        f"  alerts fired          {len(result.alerts)}",
        f"  reverted              {result.hit_rate:.1%}",
        f"  beat friction         {result.profit_rate:.1%}",
        f"  mean move on alert    {result.mean_move_bps:>+8.2f} bps",
        f"  mean move any day     {result.baseline_mean_move_bps:>+8.2f} bps  "
        f"(n={result.baseline_n})",
        f"  EDGE OVER BASELINE    {result.edge_over_baseline_bps:>+8.2f} bps",
        f"  mean net of friction  {result.mean_net_bps:>+8.2f} bps",
        "",
        f"  {result.verdict}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the alerting rule.")
    parser.add_argument("--pair", required=True, help="a linkage id from universe.yaml")
    parser.add_argument("--universe", type=Path, default=UNIVERSE)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--horizon", type=int, default=3, help="holding period in days")
    parser.add_argument("--alert-percentile", type=float, default=99.0)
    parser.add_argument("--friction", type=float, default=None)
    args = parser.parse_args()

    universe = load_universe(args.universe)
    linkage = universe.by_id(args.pair)
    legs = list(linkage.legs.values())
    if len(legs) != 2:
        raise SystemExit(
            f"{args.pair} has {len(legs)} legs; the backtest handles two-leg "
            "spreads only"
        )

    friction = args.friction if args.friction is not None else linkage.total_friction_bps
    print(f"\nBacktesting {args.pair}: {legs[0].symbol} vs {legs[1].symbol}")

    result = run(
        args.pair,
        legs[0].symbol,
        legs[1].symbol,
        years=args.years,
        horizon=args.horizon,
        friction_bps=friction,
        alert_percentile=args.alert_percentile,
    )
    print(report(result))


if __name__ == "__main__":
    main()
