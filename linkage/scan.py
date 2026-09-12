"""One scan cycle, or many.

    python -m linkage.scan --once
    python -m linkage.scan --interval 60
    python -m linkage.scan --warmup 400        # replay history before watching live

Prefetches every symbol in one request per provider, evaluates each linkage,
and puts the observation through the composed detector: Kalman for the signal,
an empirical percentile for the threshold, an OU gate for whether the deviation
is reachable inside the holding period.

History is in memory, so a fresh process knows nothing until it has watched
enough cycles -- or until `--warmup` replays daily history through the detectors
first, which is the difference between being useful at startup and being useful
next week.
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from linkage.config import LinkageConfig, Universe, load_universe
from linkage.detector import LinkageDetector, Verdict
from linkage.engine import SpreadHistory, evaluate_linkage
from linkage.providers.base import MarketDataProvider, ProviderError, Quote
from linkage.providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger("linkage.scan")

PROVIDERS: dict[str, type] = {"yfinance": YFinanceProvider}
DEFAULT_UNIVERSE = Path(__file__).resolve().parent.parent / "config" / "universe.yaml"


def build_providers(universe: Universe) -> dict[str, MarketDataProvider]:
    providers: dict[str, MarketDataProvider] = {}
    for name in universe.providers_used():
        try:
            providers[name] = PROVIDERS[name]()
        except KeyError:
            raise SystemExit(
                f"universe references unknown provider {name!r}; "
                f"known: {', '.join(sorted(PROVIDERS))}"
            ) from None
    return providers


def warm_detectors(
    universe: Universe,
    providers: dict[str, MarketDataProvider],
    detectors: dict[str, LinkageDetector],
    histories: dict[str, SpreadHistory],
    *,
    days: int,
) -> None:
    """Replay daily history through each detector before going live.

    Without this the first few hundred live cycles are spent learning, and the
    detector is silent through exactly the period someone is watching it to see
    whether it works.
    """
    print(f"warming detectors on {days} days of history...")
    for linkage in universe.linkages:
        try:
            bars = {
                name: providers[leg.provider].bars(leg.symbol, "1d", days)
                for name, leg in linkage.legs.items()
            }
        except ProviderError as exc:
            print(f"  {linkage.id:<20} skipped — {exc}")
            continue

        by_date: dict[object, dict[str, Decimal]] = {}
        for name, series in bars.items():
            for bar in series:
                by_date.setdefault(bar.ts.date(), {})[name] = bar.close

        complete = [d for d, legs in sorted(by_date.items()) if len(legs) == len(linkage.legs)]
        detector = detectors.setdefault(linkage.id, LinkageDetector(linkage.id))
        history = histories.setdefault(linkage.id, SpreadHistory())

        for day in complete:
            ts = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            quotes = {n: Quote(n, p, ts) for n, p in by_date[day].items()}
            try:
                observation = evaluate_linkage(
                    linkage, quotes, history, now=ts, max_age_seconds=float("inf")
                )
            except (KeyError, ValueError):
                continue
            history.append(observation.spread_bps)
            detector.observe(observation, linkage)

        print(f"  {linkage.id:<20} {len(complete):>4} days replayed")
    print()


def _render(linkage: LinkageConfig, observation, verdict: Verdict) -> str:
    z = verdict.z
    z_text = f"{z:+6.2f}" if z is not None else "   n/a"
    pct = verdict.threshold.percentile if verdict.threshold else None
    pct_text = f"{pct:>5.1f}" if pct is not None else "  n/a"
    beta = verdict.kalman.beta if verdict.kalman else None
    beta_text = f"{beta:.4f}" if beta is not None else "   n/a"
    return (
        f"  {linkage.id:<20} "
        f"spread {observation.spread_bps:+9.1f}bps  "
        f"kz {z_text}  "
        f"pct {pct_text}  "
        f"beta {beta_text}  "
        f"{'ALERT' if verdict.should_alert else verdict.reason[:52]}"
    )


def scan_once(
    universe: Universe,
    providers: dict[str, MarketDataProvider],
    histories: dict[str, SpreadHistory],
    detectors: dict[str, LinkageDetector],
    last_alert: dict[str, datetime],
    *,
    max_age_seconds: float,
    horizon_days: float,
) -> list[tuple[LinkageConfig, Verdict]]:
    for name, provider in providers.items():
        try:
            provider.prefetch(universe.symbols_for(name))
        except ProviderError as exc:
            logger.error("%s prefetch failed: %s", name, exc)

    now = datetime.now(timezone.utc)
    fired: list[tuple[LinkageConfig, Verdict]] = []

    for linkage in universe.linkages:
        quotes = {}
        try:
            for leg_name, leg in linkage.legs.items():
                quotes[leg_name] = providers[leg.provider].quote(leg.symbol)
        except ProviderError as exc:
            print(f"  {linkage.id:<20} unavailable — {exc}")
            continue

        history = histories.setdefault(linkage.id, SpreadHistory())
        detector = detectors.setdefault(linkage.id, LinkageDetector(linkage.id))

        observation = evaluate_linkage(
            linkage, quotes, history, now=now, max_age_seconds=max_age_seconds
        )
        verdict = detector.observe(observation, linkage, horizon_periods=horizon_days)

        # Stale points never join the distribution they would be judged against.
        if not observation.stale:
            history.append(observation.spread_bps)

        print(_render(linkage, observation, verdict))

        if verdict.should_alert:
            previous = last_alert.get(linkage.id)
            cooldown = timedelta(minutes=linkage.alert.cooldown_minutes)
            if previous is None or now - previous >= cooldown:
                last_alert[linkage.id] = now
                fired.append((linkage, verdict))

    return fired


def render_alert(linkage: LinkageConfig, verdict: Verdict) -> str:
    gate = verdict.gate
    ou = verdict.ou
    return (
        f"\n  ALERT  {linkage.id}  [{linkage.category.value}]\n"
        f"         kalman z      {verdict.z:+.2f}   beta {verdict.kalman.beta:.4f}\n"
        f"         percentile    {verdict.threshold.percentile:.2f}\n"
        f"         half-life     {ou.half_life:.2f}d (t={ou.theta_tstat:.1f})\n"
        f"         reverts in {gate.expected_reversion_bps:+.1f}bps, "
        f"friction {linkage.total_friction_bps:.1f}bps, "
        f"net {gate.net_after_friction_bps:+.1f}bps\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan the linkage universe.")
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=None)
    parser.add_argument("--max-age", type=float, default=900.0)
    parser.add_argument("--horizon", type=float, default=3.0, help="holding period, days")
    parser.add_argument(
        "--warmup", type=int, default=0, help="days of history to replay first"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    universe = load_universe(args.universe)
    providers = build_providers(universe)
    histories: dict[str, SpreadHistory] = {}
    detectors: dict[str, LinkageDetector] = {}
    last_alert: dict[str, datetime] = {}

    floor = max(p.cadence_floor_seconds for p in providers.values())
    interval = max(args.interval or floor, floor)
    if args.interval and args.interval < floor:
        print(
            f"note: requested {args.interval}s but the slowest provider's honest "
            f"floor is {floor}s — using {floor}s"
        )

    print(
        f"{len(universe.linkages)} linkage(s), "
        f"{sum(len(universe.symbols_for(p)) for p in providers)} distinct symbol(s), "
        f"interval {interval}s, horizon {args.horizon:g}d\n"
    )

    if args.warmup:
        warm_detectors(universe, providers, detectors, histories, days=args.warmup)

    while True:
        print(f"[{datetime.now(timezone.utc):%H:%M:%S}]")
        for linkage, verdict in scan_once(
            universe,
            providers,
            histories,
            detectors,
            last_alert,
            max_age_seconds=args.max_age,
            horizon_days=args.horizon,
        ):
            print(render_alert(linkage, verdict))
        if args.once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
