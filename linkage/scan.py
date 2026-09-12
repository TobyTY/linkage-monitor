"""One scan cycle, or many.

    python -m linkage.scan --once
    python -m linkage.scan --interval 60

Prefetches every symbol the universe needs in one request per provider,
evaluates each linkage, advances the state machine, and prints a line per
linkage. History lives in memory for now, so a fresh process has no z-scores
until it has watched MIN_SAMPLES_FOR_Z cycles -- which is correct behaviour, not
a gap: scoring against a handful of points is how you alert on the first wobble
after startup.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from linkage.config import Universe, load_universe
from linkage.engine import SpreadHistory, evaluate_linkage
from linkage.providers.base import MarketDataProvider, ProviderError
from linkage.providers.yfinance_provider import YFinanceProvider
from linkage.signals import AlertEvent, SignalTracker

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


def scan_once(
    universe: Universe,
    providers: dict[str, MarketDataProvider],
    histories: dict[str, SpreadHistory],
    tracker: SignalTracker,
    *,
    max_age_seconds: float,
) -> list[AlertEvent]:
    # One request per provider, not one per leg. USDINR alone appears in every
    # linkage here.
    for name, provider in providers.items():
        try:
            provider.prefetch(universe.symbols_for(name))
        except ProviderError as exc:
            logger.error("%s prefetch failed: %s", name, exc)

    now = datetime.now(timezone.utc)
    alerts: list[AlertEvent] = []

    for linkage in universe.linkages:
        quotes = {}
        try:
            for leg_name, leg in linkage.legs.items():
                quotes[leg_name] = providers[leg.provider].quote(leg.symbol)
        except ProviderError as exc:
            print(f"  {linkage.id:<12} unavailable — {exc}")
            continue

        history = histories.setdefault(linkage.id, SpreadHistory())
        observation = evaluate_linkage(
            linkage, quotes, history, now=now, max_age_seconds=max_age_seconds
        )

        z = observation.z_score
        z_text = f"{z:+6.2f}" if z is not None else f"  n/a ({len(history)})"
        edge = observation.net_edge_bps
        edge_text = f"{edge:+8.1f}" if edge is not None else "     n/a"
        flag = f"  STALE: {observation.stale_reason}" if observation.stale else ""

        print(
            f"  {linkage.id:<12} "
            f"ref {observation.reference_price:>12}  "
            f"fair {observation.fair_value:>12.4f}  "
            f"spread {observation.spread_bps:+8.1f}bps  "
            f"z {z_text}  "
            f"net {edge_text}bps"
            f"{flag}"
        )

        # Only a scoreable observation joins the history. Feeding stale points
        # in would pollute the very distribution used to judge them.
        if not observation.stale:
            history.append(observation.spread_bps)

        alert = tracker.observe(observation, linkage)
        if alert is not None:
            alerts.append(alert)

    return alerts


def render_alert(alert: AlertEvent) -> str:
    return (
        f"\n  ALERT  {alert.linkage_id}\n"
        f"         z={alert.z_score:+.2f}  spread={alert.spread_bps:+.1f}bps\n"
        f"         friction={alert.friction_bps:.1f}bps  "
        f"net={alert.net_edge_bps:+.1f}bps\n"
        f"         legs={ {k: str(v) for k, v in alert.leg_prices.items()} }\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan the linkage universe.")
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--once", action="store_true", help="one cycle, then exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="seconds between cycles; floored at the slowest provider's floor",
    )
    parser.add_argument("--max-age", type=float, default=900.0)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    universe = load_universe(args.universe)
    providers = build_providers(universe)
    histories: dict[str, SpreadHistory] = defaultdict(SpreadHistory)
    tracker = SignalTracker()

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
        f"interval {interval}s\n"
    )

    while True:
        print(f"[{datetime.now(timezone.utc):%H:%M:%S}]")
        for alert in scan_once(
            universe, providers, histories, tracker, max_age_seconds=args.max_age
        ):
            print(render_alert(alert))
        if args.once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
