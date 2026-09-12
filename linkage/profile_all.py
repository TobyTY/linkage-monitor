"""Profile every pair in the catalogue and write the reference document.

    python -m linkage.profile_all --years 5 --out PAIRS.md

Downloads each distinct symbol once, aligns per pair, measures, and emits a
markdown reference combining the WRITTEN mechanism (why the pair should be
linked) with the MEASURED result (whether it actually is). The two disagreeing
is the most useful output this produces -- a pair with a compelling story and a
cointegration p-value of 0.8 is exactly the trade that looks obvious and loses
money.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from linkage.pairs import MIN_OBSERVATIONS, PairProfile, profile_pair

CATALOGUE = Path(__file__).resolve().parent.parent / "config" / "pairs.yaml"

GROUP_TITLES = {
    "fx": "Foreign Exchange",
    "intermarket": "Intermarket & Index",
    "equity_us": "US Equity Pairs",
    "india_sector": "India — Sector Duopolies",
    "india_supply": "India — Supply Chain & Cost-Push",
    "india_group": "India — Corporate House",
    "india_index": "India — Index & Macro",
}

ACCESS_NOTES = {
    "full": "both legs tradeable including the short side",
    "long_only": "buyable, but the short leg needs F&O or intraday",
    "none": "at least one leg unreachable from an Indian retail account",
}


def load_catalogue(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["pairs"]


def download(symbols: list[str], years: int) -> pd.DataFrame:
    import yfinance as yf

    cache = (
        Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
        / "linkage-monitor"
        / "yf-cache"
    )
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache))

    frame = yf.download(
        sorted(set(symbols)),
        period=f"{years}y",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,  # split/dividend adjusted: mandatory for a hedge ratio
        progress=False,
        threads=True,
    )
    closes = {}
    for symbol in sorted(set(symbols)):
        try:
            series = frame[symbol]["Close"].dropna()
            if not series.empty:
                closes[symbol] = series
        except (KeyError, TypeError):
            pass
    return pd.DataFrame(closes)


def _row(entry: dict, profile: PairProfile | None, error: str | None) -> str:
    if profile is None:
        return f"| `{entry['id']}` | — | — | — | — | {error} |"
    hl = f"{profile.half_life_days:.0f}d" if profile.half_life_days else "none"
    flag = "**yes**" if profile.is_cointegrated else "no"
    return (
        f"| `{profile.pair_id}` | {profile.return_corr:+.2f} | "
        f"{profile.coint_pvalue:.3f} | {flag} | {hl} | {profile.verdict} |"
    )


def _detail(entry: dict, profile: PairProfile | None, error: str | None) -> str:
    head = f"#### `{entry['id']}` — {entry['a']} vs {entry['b']}\n\n"
    head += f"**Mechanism.** {entry['mechanism'].strip()}\n\n"
    head += f"**Breaks when.** {entry['breaks_when'].strip()}\n\n"
    if entry.get("note"):
        head += f"**Note.** {entry['note'].strip()}\n\n"
    head += (
        f"**Access.** `{entry['access']}` — {ACCESS_NOTES[entry['access']]}\n\n"
    )

    if profile is None:
        return head + f"**Measured.** Could not profile: {error}\n\n"

    hl = (
        f"{profile.half_life_days:.1f} days"
        if profile.half_life_days
        else "no mean reversion detected"
    )
    return head + (
        "| measure | value |\n|---|---|\n"
        f"| Sample | {profile.observations} days, {profile.start} → {profile.end} |\n"
        f"| Return correlation | {profile.return_corr:+.3f} |\n"
        f"| Rolling 60d corr (now / min / max) | "
        f"{profile.rolling_corr_now:+.2f} / {profile.rolling_corr_min:+.2f} / "
        f"{profile.rolling_corr_max:+.2f} |\n"
        f"| Relationship stability | {profile.stability} |\n"
        f"| Engle-Granger p-value | {profile.coint_pvalue:.4f} |\n"
        f"| ADF p-value on spread | {profile.adf_pvalue:.4f} |\n"
        f"| Hedge ratio β (log-log) | {profile.hedge_ratio:+.4f} |\n"
        f"| R² | {profile.r_squared:.3f} |\n"
        f"| Spread SD | {profile.spread_sd_bps:.0f} bps |\n"
        f"| Half-life | {hl} |\n"
        f"| Current z | {profile.current_z:+.2f} |\n"
        f"| Max historical \\|z\\| | {profile.max_abs_z:.2f} |\n"
        f"\n**Verdict.** {profile.verdict}\n\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("PAIRS.md"))
    args = parser.parse_args()

    entries = load_catalogue(args.catalogue)
    symbols = [s for e in entries for s in (e["a"], e["b"])]
    print(f"{len(entries)} pairs, {len(set(symbols))} distinct symbols")

    prices = download(symbols, args.years)
    print(f"downloaded {prices.shape[1]} series, {prices.shape[0]} rows\n")

    results: list[tuple[dict, PairProfile | None, str | None]] = []
    for entry in entries:
        try:
            profile = profile_pair(entry["id"], entry["a"], entry["b"], prices)
            results.append((entry, profile, None))
            print(f"  {entry['id']:<26} {profile.verdict}")
        except Exception as exc:  # noqa: BLE001 - reported per pair in the doc
            results.append((entry, None, str(exc)))
            print(f"  {entry['id']:<26} FAILED: {exc}")

    passed = [p for _, p, _ in results if p and p.is_cointegrated]
    tradeable = [p for p in passed if p.reachable_in_72h]

    lines = [
        "# Pairs Reference",
        "",
        f"Measured {datetime.now(timezone.utc):%Y-%m-%d} over {args.years} years of "
        "split- and dividend-adjusted daily closes.",
        "",
        "## How to read this",
        "",
        "**Correlation is measured on returns, not levels.** Any two series that "
        "both trend upward show a high level-correlation; it records that both "
        "went up and nothing else.",
        "",
        "**Cointegration is tested on levels.** That is the opposite convention "
        "and it is the correct one — cointegration is the claim that two "
        "non-stationary series have a stationary linear combination.",
        "",
        "**Half-life is the filter that matters for a 48–72h horizon.** A pair can "
        "be beautifully cointegrated on a forty-day reversion cycle and be "
        "useless inside three days. Half-life turns *this relationship is real* "
        "into *this relationship is real and reachable in the time I have*.",
        "",
        "**A hedge ratio β is fitted on log prices**, so it is an elasticity and "
        "scale-free. A ratio fitted on raw prices silently encodes the price "
        "level of the day it was fitted.",
        "",
        f"**Result: {len(passed)} of {len(entries)} pairs cointegrate at 5%. "
        f"{len(tradeable)} of those revert inside a 72-hour horizon.**",
        "",
        "## Summary",
        "",
        "| pair | ret corr | EG p | cointegrated | half-life | verdict |",
        "|---|---|---|---|---|---|",
    ]
    lines += [_row(e, p, err) for e, p, err in results]

    for group, title in GROUP_TITLES.items():
        subset = [(e, p, err) for e, p, err in results if e["group"] == group]
        if not subset:
            continue
        lines += ["", f"## {title}", ""]
        lines += [_detail(e, p, err) for e, p, err in subset]

    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {args.out}  ({len(passed)}/{len(entries)} cointegrated, "
          f"{len(tradeable)} within horizon)")


if __name__ == "__main__":
    main()
