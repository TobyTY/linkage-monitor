"""A page showing what the monitor knows, built from the database.

    python -m linkage.dashboard --out dashboard.html

One self-contained HTML file: no server, no framework, no JavaScript build, and
no new dependency. That is a deliberate choice rather than a shortcut. A
dashboard that needs a process running is a dashboard that is down exactly when
someone thinks to look at it, and this one is a file you can open, mail, or
commit next to the numbers it describes.

WHAT IT SHOWS, AND WHY THOSE THINGS. Four panels, and three of them are about
doubt rather than about signal:

    detectors    how much each one has seen, and how far beta has drifted from
                 1. Drift is the standing question on every computable linkage:
                 a conversion constant going stale produces a permanent gap that
                 looks exactly like a standing arbitrage.
    alerts       what fired, with what the model PREDICTED at the time, so a
                 prediction can be read next to the outcome instead of being
                 quietly forgotten.
    outcomes     what the spread actually did over the horizon after each alert,
                 recovered by joining alerts against observations. This is the
                 only panel that can make the system look bad, which is why it
                 is here.
    coverage     when each linkage was last seen, because a feed that silently
                 stopped looks identical to a market that went quiet.

Numbers are rendered as they are stored. Nothing on this page is rounded into
looking better than it is.
"""

from __future__ import annotations

import argparse
import html
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import func, select

from linkage.config import Universe
from linkage.scan import PROJECT_ROOT, default_universes, load_universes
from linkage.store import StateStore, alerts, detector_state, observations


@dataclass(frozen=True)
class Outcome:
    """What happened after an alert, measured rather than predicted."""

    linkage_id: str
    when: datetime
    spread_bps: float
    predicted_reversion_bps: float | None
    friction_bps: float
    actual_move_bps: float | None      # how much |spread| shrank over the horizon
    resolved: bool

    @property
    def net_bps(self) -> float | None:
        if self.actual_move_bps is None:
            return None
        return self.actual_move_bps - self.friction_bps


def outcomes(store: StateStore, *, horizon_days: float) -> list[Outcome]:
    """Join each alert to the observation nearest its horizon.

    An alert whose horizon has not elapsed is reported as unresolved rather
    than dropped. Silently excluding open positions is how a hit rate ends up
    describing only the trades that finished early.
    """
    horizon = timedelta(days=horizon_days)
    found: list[Outcome] = []

    with store.engine.connect() as conn:
        rows = conn.execute(
            select(alerts).order_by(alerts.c.ts.desc()).limit(200)
        ).all()

        for row in rows:
            fired_at = _utc(row.ts)
            target = fired_at + horizon

            after = conn.execute(
                select(observations.c.spread_bps, observations.c.ts)
                .where(observations.c.linkage_id == row.linkage_id)
                .where(observations.c.ts >= target)
                .order_by(observations.c.ts.asc())
                .limit(1)
            ).one_or_none()

            move = None
            if after is not None:
                move = abs(row.spread_bps) - abs(after.spread_bps)

            found.append(
                Outcome(
                    linkage_id=row.linkage_id,
                    when=fired_at,
                    spread_bps=row.spread_bps,
                    predicted_reversion_bps=row.predicted_reversion_bps,
                    friction_bps=row.friction_bps,
                    actual_move_bps=move,
                    resolved=move is not None,
                )
            )
    return found


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _e(value: object) -> str:
    return html.escape(str(value))


def _num(value: float | None, spec: str = "+.1f", dash: str = "—") -> str:
    if value is None:
        return f'<td class="n dim">{dash}</td>'
    cls = "pos" if value > 0 else "neg" if value < 0 else ""
    return f'<td class="n {cls}">{value:{spec}}</td>'


CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a1a;--dim:#6b6b6b;--line:#e3e3e0;--card:#fff;
      --pos:#0a7d4f;--neg:#b0341d;--warn:#8a6200;}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#e8e8e6;--dim:#9a9a97;
      --line:#2c2c2c;--card:#1c1c1c;--pos:#4ec98a;--neg:#f0846a;--warn:#d9ad4a;}}
*{box-sizing:border-box}
body{margin:0;padding:2rem 1.25rem 4rem;background:var(--bg);color:var(--fg);
     font:14px/1.55 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif;}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:1.4rem;margin:0 0 .2rem;letter-spacing:-.01em}
h2{font-size:.95rem;margin:2.4rem 0 .5rem;letter-spacing:.02em;text-transform:uppercase;
   color:var(--dim);font-weight:600}
.sub{color:var(--dim);margin:0 0 .4rem}
.note{color:var(--dim);font-size:12.5px;margin:.1rem 0 .7rem;max-width:74ch}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
      overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th{text-align:left;font-weight:600;font-size:11.5px;text-transform:uppercase;
   letter-spacing:.03em;color:var(--dim);padding:.6rem .75rem;
   border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:.5rem .75rem;border-bottom:1px solid var(--line);white-space:nowrap}
tr:last-child td{border-bottom:none}
td.n,th.n{text-align:right}
.pos{color:var(--pos)}.neg{color:var(--neg)}.dim{color:var(--dim)}
.warn{color:var(--warn)}
.tag{font-size:11px;padding:.1rem .4rem;border:1px solid var(--line);
     border-radius:4px;color:var(--dim)}
.empty{padding:1.4rem .9rem;color:var(--dim)}
footer{margin-top:3rem;color:var(--dim);font-size:12px;border-top:1px solid var(--line);
       padding-top:.8rem}
"""


def _detector_panel(store: StateStore, universe: Universe) -> str:
    by_id = {link.id: link for link in universe.linkages}
    with store.engine.connect() as conn:
        rows = conn.execute(
            select(detector_state).order_by(detector_state.c.linkage_id)
        ).all()

    if not rows:
        return '<div class="card"><p class="empty">No detector has stored state yet. Run the scanner.</p></div>'

    out = [
        '<div class="card"><table><tr><th>linkage</th><th>category</th>'
        '<th class="n">seen</th><th class="n">window</th><th class="n">beta</th>'
        '<th class="n">drift</th><th>saved</th><th>config</th></tr>'
    ]
    for row in rows:
        snap = row.snapshot or {}
        kal = snap.get("kalman", {})
        state = kal.get("state") or []
        beta = float(state[0]) if state else None
        drift = abs(beta - 1.0) if beta is not None else None
        link = by_id.get(row.linkage_id)

        # A fingerprint that no longer matches means this row was written under
        # a different formula or constant. The state will be discarded on the
        # next load, and saying so here is cheaper than wondering why the
        # detector went back to warming up.
        stale_cfg = link is not None and link.state_fingerprint != row.fingerprint

        if drift is None:
            drift_cell = '<td class="n dim">—</td>'
        elif drift > 0.01:
            drift_cell = f'<td class="n warn">{drift:.2%}</td>'
        else:
            drift_cell = f'<td class="n dim">{drift:.2%}</td>'

        out.append(
            "<tr>"
            f"<td>{_e(row.linkage_id)}</td>"
            f'<td><span class="tag">{_e(link.category.value) if link else "?"}</span></td>'
            f'<td class="n">{snap.get("seen", 0)}</td>'
            f'<td class="n">{len(snap.get("threshold", {}).get("values", []))}</td>'
            + (f'<td class="n">{beta:.4f}</td>' if beta is not None
               else '<td class="n dim">—</td>')
            + drift_cell
            + f'<td class="dim">{_utc(row.updated_at):%Y-%m-%d %H:%M}</td>'
            + ('<td class="warn">changed since save</td>' if stale_cfg
               else '<td class="dim">unchanged</td>')
            + "</tr>"
        )
    out.append("</table></div>")
    return "".join(out)


def _alerts_panel(found: list[Outcome]) -> str:
    if not found:
        return (
            '<div class="card"><p class="empty">No alerts recorded. On this '
            "universe that is the expected state most of the time — the gates "
            "exist to produce exactly this.</p></div>"
        )
    out = [
        '<div class="card"><table><tr><th>when</th><th>linkage</th>'
        '<th class="n">spread</th><th class="n">predicted</th>'
        '<th class="n">actual</th><th class="n">friction</th>'
        '<th class="n">net</th><th>status</th></tr>'
    ]
    for o in found[:60]:
        out.append(
            f'<tr><td class="dim">{o.when:%Y-%m-%d %H:%M}</td>'
            f"<td>{_e(o.linkage_id)}</td>"
            + _num(o.spread_bps)
            + _num(o.predicted_reversion_bps)
            + _num(o.actual_move_bps)
            + f'<td class="n dim">{o.friction_bps:.1f}</td>'
            + _num(o.net_bps)
            + (
                "<td>resolved</td>"
                if o.resolved
                else '<td class="dim">horizon still open</td>'
            )
            + "</tr>"
        )
    out.append("</table></div>")
    return "".join(out)


def _scorecard(found: list[Outcome]) -> str:
    resolved = [o for o in found if o.resolved and o.net_bps is not None]
    if not resolved:
        return (
            '<p class="note">Nothing has been alerted and then observed a full '
            "horizon later yet, so there is no live scorecard. The backtest is "
            "the only evidence until there is.</p>"
        )
    wins = sum(1 for o in resolved if o.net_bps > 0)
    mean = sum(o.net_bps for o in resolved) / len(resolved)
    predicted = [o for o in resolved if o.predicted_reversion_bps is not None]
    bias = (
        sum(o.actual_move_bps - o.predicted_reversion_bps for o in predicted)
        / len(predicted)
        if predicted
        else None
    )
    cls = "pos" if mean > 0 else "neg"
    line = (
        f'<p class="note"><b>{len(resolved)}</b> alerts have run their full '
        f"horizon. {wins} beat friction. Mean net "
        f'<b class="{cls}">{mean:+.1f} bps</b>.'
    )
    if bias is not None:
        line += (
            f" The model over/under-predicted reversion by "
            f"<b>{bias:+.1f} bps</b> on average — the number that says whether "
            f"the OU fit is describing this market or flattering it."
        )
    if len(resolved) < 15:
        line += (
            " At this sample size none of that is evidence of anything; it is "
            "a record being kept so that it eventually can be."
        )
    return line + "</p>"


def _coverage_panel(store: StateStore) -> str:
    with store.engine.connect() as conn:
        rows = conn.execute(
            select(
                observations.c.linkage_id,
                func.count().label("n"),
                func.max(observations.c.ts).label("last"),
            ).group_by(observations.c.linkage_id)
        ).all()
    if not rows:
        return (
            '<div class="card"><p class="empty">No observations recorded yet. '
            "Every leg was stale, or the scanner has not run with a database.</p></div>"
        )
    now = datetime.now(timezone.utc)
    out = [
        '<div class="card"><table><tr><th>linkage</th><th class="n">observations</th>'
        '<th>last seen</th><th class="n">age</th></tr>'
    ]
    for row in sorted(rows, key=lambda r: r.last, reverse=True):
        age = now - _utc(row.last)
        hours = age.total_seconds() / 3600
        cls = "warn" if hours > 24 else "dim"
        out.append(
            f'<tr><td>{_e(row.linkage_id)}</td><td class="n">{row.n}</td>'
            f'<td class="dim">{_utc(row.last):%Y-%m-%d %H:%M}</td>'
            f'<td class="n {cls}">{hours:.1f}h</td></tr>'
        )
    out.append("</table></div>")
    return "".join(out)


def build_page(store: StateStore, universe: Universe, *, horizon_days: float) -> str:
    found = outcomes(store, horizon_days=horizon_days)
    generated = datetime.now(timezone.utc)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Linkage Monitor</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>Linkage Monitor</h1>
<p class="sub">{len(universe.linkages)} linkages · {horizon_days:g}-day horizon ·
generated {generated:%Y-%m-%d %H:%M} UTC</p>

<h2>Detectors</h2>
<p class="note">Beta is the fitted ratio between the reference leg and its
computed fair value. It sits at 1 when the configured constants are right.
Persistent drift is a stale constant asking to be recalibrated — not a trading
signal, and the most likely cause of a divergence that is not real.</p>
{_detector_panel(store, universe)}

<h2>Alerts and outcomes</h2>
{_scorecard(found)}
{_alerts_panel(found)}

<h2>Coverage</h2>
<p class="note">A feed that stopped and a market that went quiet look identical
from inside the scanner. This is how you tell them apart.</p>
{_coverage_panel(store)}

<footer>Every figure is read straight from the database and rendered unrounded.
Net is the measured move minus that linkage's own itemised friction. On an
observational linkage a net figure says whether the relationship is holding; it
is not a profit estimate.</footer>
</div></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the dashboard.")
    parser.add_argument("--out", type=Path, default=Path("dashboard.html"))
    parser.add_argument("--db", default=None)
    parser.add_argument("--horizon", type=float, default=3.0)
    parser.add_argument("--universe", type=Path, action="append", default=None)
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    url = (
        args.db
        or os.environ.get("LINKAGE_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise SystemExit(
            "no database configured — set LINKAGE_DATABASE_URL or pass --db. "
            "The dashboard reports what was recorded; without a database "
            "nothing was."
        )

    store = StateStore.connect(url)
    universe = load_universes(args.universe or default_universes())
    args.out.write_text(
        build_page(store, universe, horizon_days=args.horizon), encoding="utf-8"
    )
    print(f"wrote {args.out.resolve()}")


if __name__ == "__main__":
    main()
