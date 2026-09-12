"""One scan cycle, or many.

    python -m linkage.scan --once
    python -m linkage.scan --interval 60
    python -m linkage.scan --warmup 400        # replay history before watching live
    python -m linkage.scan --no-db             # don't persist anything

Prefetches every symbol in one request per provider, evaluates each linkage,
and puts the observation through the composed detector: Kalman for the signal,
an empirical percentile for the threshold, an OU gate for whether the deviation
is reachable inside the holding period.

Detector state is loaded from the database at startup and written back every
cycle, so a restart costs a few seconds rather than a hundred cycles of warming
up in public. Linkages that resume are NOT re-warmed from daily history: they
already know more than a warmup would tell them, and replaying it would feed
every bar in twice.

With no database (`--no-db`, or nothing configured) everything still runs, in
memory, forgetting itself on exit. That is the right mode for looking at
something; it is not a mode to leave running.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from linkage.config import LinkageConfig, Universe, load_universe
from linkage.detector import WARMUP_OBSERVATIONS, LinkageDetector, Verdict
from linkage.engine import SpreadHistory, evaluate_linkage
from linkage.providers.base import MarketDataProvider, ProviderError, Quote
from linkage.providers.yfinance_provider import YFinanceProvider
from linkage.store import StateStore

logger = logging.getLogger("linkage.scan")

PROVIDERS: dict[str, type] = {"yfinance": YFinanceProvider}
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UNIVERSE = PROJECT_ROOT / "config" / "universe.yaml"

#: Written by `python -m linkage.stat_pairs --fit`. Absent until that has been
#: run, which is why it is included only when it exists rather than required.
FITTED_PAIRS = PROJECT_ROOT / "config" / "pairs.fitted.yaml"


def default_universes() -> list[Path]:
    files = [DEFAULT_UNIVERSE]
    if FITTED_PAIRS.exists():
        files.append(FITTED_PAIRS)
    return files


def load_universes(paths: list[Path]) -> Universe:
    """Merge several universe files into one.

    The computable linkages and the fitted statistical pairs live in separate
    files because they are different KINDS of claim -- one set's constants come
    from filings and duty schedules, the other's from a regression over a window
    that is named in the file. Merging them here rather than in the config keeps
    that distinction visible on disk while letting one scan run both.

    Ids must stay unique across files. A pair id colliding with a linkage id
    would otherwise mean two detectors sharing one row of persisted state.
    """
    linkages = []
    seen: dict[str, Path] = {}
    for path in paths:
        for linkage in load_universe(path).linkages:
            if linkage.id in seen:
                raise SystemExit(
                    f"{path}: duplicate linkage id {linkage.id!r}, already "
                    f"defined in {seen[linkage.id]}"
                )
            seen[linkage.id] = path
            linkages.append(linkage)
    return Universe(linkages=linkages)


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
    skip: set[str] | None = None,
) -> None:
    """Replay daily history through each detector before going live.

    Without this the first few hundred live cycles are spent learning, and the
    detector is silent through exactly the period someone is watching it to see
    whether it works.

    `skip` holds the linkages that came back from storage ALREADY PAST WARMUP.
    Warming those would replay history a filter has already seen, which is not a
    no-op: it double-counts every bar into the percentile window and drags the
    Kalman covariance down to a confidence the data does not support.

    Readiness, not the existence of a row, is the right test — and the
    difference is not academic. The first run of this scanner happened on a
    closed market: every quote was stale, so every detector learned nothing, and
    a row was written anyway. Skipping on "a row exists" then suppressed the
    warmup on every subsequent run, permanently, while printing a line that said
    everything had resumed.
    """
    skip = skip or set()
    print(f"warming detectors on {days} days of history...")
    for linkage in universe.linkages:
        if linkage.id in skip:
            print(f"  {linkage.id:<20} already resumed — not re-warming")
            continue
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


def resume(
    universe: Universe,
    store: StateStore,
    detectors: dict[str, LinkageDetector],
    last_alert: dict[str, datetime],
) -> set[str]:
    """Load what each detector knew last time. Returns the ids that resumed.

    Every linkage prints its own line, including the ones that did not resume
    and why. A monitor that silently starts from nothing after a config edit is
    a monitor that goes quiet for a week without anyone noticing.
    """
    ready: set[str] = set()
    print("loading stored state...")
    for linkage in universe.linkages:
        result = store.load(linkage)
        note = result.reason
        if result.restored:
            detectors[linkage.id] = result.detector
            if result.last_alert is not None:
                last_alert[linkage.id] = result.last_alert
            if result.detector.seen >= WARMUP_OBSERVATIONS:
                ready.add(linkage.id)
            else:
                note += " — still inside warmup"
        print(f"  {linkage.id:<20} {note}")
    print()
    return ready


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
    store: StateStore | None = None,
) -> list[tuple[LinkageConfig, Verdict]]:
    for name, provider in providers.items():
        try:
            provider.prefetch(universe.symbols_for(name))
        except ProviderError as exc:
            logger.error("%s prefetch failed: %s", name, exc)

    now = datetime.now(timezone.utc)
    fired: list[tuple[LinkageConfig, Verdict]] = []
    seen_this_cycle: list[tuple[LinkageConfig, object]] = []

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
            seen_this_cycle.append((linkage, observation))

        print(_render(linkage, observation, verdict))

        if verdict.should_alert:
            previous = last_alert.get(linkage.id)
            cooldown = timedelta(minutes=linkage.alert.cooldown_minutes)
            if previous is None or now - previous >= cooldown:
                last_alert[linkage.id] = now
                fired.append((linkage, verdict))
                if store is not None:
                    store.record_alert(linkage, verdict)

        # Written every cycle rather than on exit: the process is expected to
        # be killed, not to shut down politely, and state saved only on a clean
        # exit is state that is never saved.
        if store is not None and detector.seen:
            store.save(linkage, detector, last_alert=last_alert.get(linkage.id))

    if store is not None and seen_this_cycle:
        store.record_observations(seen_this_cycle)

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


def open_store(url: str | None, *, disabled: bool) -> StateStore | None:
    """Connect, or say clearly that nothing is being remembered.

    A failure to reach the database is not fatal. The scan is still correct
    without it, only forgetful, and a monitor that refuses to start because it
    cannot write its cache is worse than one that starts and says so.
    """
    if disabled:
        print("running without persistence (--no-db): state is lost on exit\n")
        return None

    load_dotenv(PROJECT_ROOT / ".env")
    url = url or os.environ.get("LINKAGE_DATABASE_URL") or os.environ.get(
        "DATABASE_URL"
    )
    if not url:
        print(
            "no database configured (set DATABASE_URL or pass --db): "
            "state is lost on exit\n"
        )
        return None

    try:
        return StateStore.connect(url)
    except Exception as exc:  # noqa: BLE001 -- driver errors are not a taxonomy
        print(f"could not open {url.split('@')[-1]}: {exc}")
        print("continuing without persistence; state is lost on exit\n")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan the linkage universe.")
    parser.add_argument(
        "--universe",
        type=Path,
        action="append",
        default=None,
        help="may be repeated; files are merged and ids must stay unique "
        f"(default: {DEFAULT_UNIVERSE.name} plus {FITTED_PAIRS.name} if present)",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=None)
    parser.add_argument("--max-age", type=float, default=900.0)
    parser.add_argument("--horizon", type=float, default=3.0, help="holding period, days")
    parser.add_argument(
        "--warmup", type=int, default=0, help="days of history to replay first"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="database URL for detector state (default: $LINKAGE_DATABASE_URL, "
        "then $DATABASE_URL)",
    )
    parser.add_argument(
        "--no-db", action="store_true", help="run in memory; forget everything on exit"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    universe = load_universes(args.universe or default_universes())
    providers = build_providers(universe)
    histories: dict[str, SpreadHistory] = {}
    detectors: dict[str, LinkageDetector] = {}
    last_alert: dict[str, datetime] = {}

    store = open_store(args.db, disabled=args.no_db)
    ready = resume(universe, store, detectors, last_alert) if store else set()

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
        warm_detectors(
            universe, providers, detectors, histories, days=args.warmup, skip=ready
        )

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
            store=store,
        ):
            print(render_alert(linkage, verdict))
        if args.once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
