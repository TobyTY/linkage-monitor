"""Turning a statistical pair into something the live scanner can run.

    python -m linkage.stat_pairs --fit
    python -m linkage.stat_pairs --fit --years 3 --horizon 3

The linkages in `universe.yaml` have a fair value you can write down. These do
not: nobody can say what Pepsi should cost given Coca-Cola. So the relationship
is estimated -- and once estimated, it can be WRITTEN DOWN, which is the whole
idea here.

A fitted pair is compiled into an ordinary `LinkageConfig`:

    fair_value:  k * b ** beta
    params:      {k: 1.0034, beta: 0.9734}

and from that point nothing downstream knows it was ever different. It goes
through the same load-time validation, the same Kalman, the same empirical
threshold, the same horizon gate, the same friction accounting, the same
persistence. Three things follow, and they are the reason for doing it this way:

  1. The fitted numbers are VISIBLE. They sit in a generated YAML file with the
     window they were fitted on, instead of living inside a pickle.
  2. Refitting changes `state_fingerprint`, so stored detector state is
     discarded automatically. A new hedge ratio means the old percentile window
     described a different quantity, and nothing has to remember to say so.
  3. Beta near 1 keeps meaning "the declared relationship is holding", exactly
     as it does for an ADR ratio. The fit becomes the declaration.

THE ADMISSION GATE IS THE POINT OF THIS FILE. There are 50 pairs in the
catalogue and wiring all of them into a live scan would be the same mistake as
watching 4,950 combinations and calling the resulting noise a signal. A pair is
admitted only if it clears five tests, and the last two do the work:

    enough history        250+ observations
    cointegrated          Engle-Granger below 5%
    reversion is real     theta separable from zero at the Dickey-Fuller value
    reversion PAYS        a 2-sigma deviation, decaying over the horizon,
                          beats this pair's friction
    the edge is CHECKABLE the mean edge reaches two standard errors from zero
                          inside a number of trades a person could live through

The fourth exists because the first three can all pass on a pair that is
perfectly real and completely useless: a spread with a 12 bps standard deviation
and a 40-day half-life is a genuine relationship that cannot cover a 27 bps
round trip in three days. Admitting it would mean a detector that runs forever
and never fires, which is indistinguishable from one that is broken.

The fifth is the one a backtest never asks. Expected reversion is a drift, and
it has to be seen through the spread's own noise over the same holding period --
which on these pairs is typically several times larger. `trades_to_detect`
reports how many trades it takes for the mean to separate from zero. A pair
needing two thousand of them has an edge that is real on paper and unfalsifiable
in practice, and running it live would be faith wearing a number.
"""

from __future__ import annotations

import argparse
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import yaml
from statsmodels.tsa.stattools import coint

from linkage.config import Access, Catalogue, LinkageConfig, PairSpec, load_catalogue
from linkage.ou import OUFit, fit_ou, horizon_gate
from linkage.pairs import MIN_OBSERVATIONS
from linkage.quality import screen

CATALOGUE = Path(__file__).resolve().parent.parent / "config" / "pairs.yaml"
FITTED = Path(__file__).resolve().parent.parent / "config" / "pairs.fitted.yaml"

#: Deviation size the admission gate asks about. Two sigma is the conventional
#: entry for a pairs trade and, more usefully here, it is roughly where the
#: empirical threshold starts firing -- so this asks about the alerts the system
#: would actually produce rather than about a hypothetical extreme.
ADMISSION_SIGMAS = 2.0

#: Above this many trades to tell the edge from zero, the pair is refused. Not
#: because the edge is wrong -- because it is unfalsifiable. A pair that fires
#: three times a year and needs 2000 trades before its mean is two standard
#: errors from zero cannot be validated inside a career, so running it live is
#: an act of faith wearing a number.
MAX_TRADES_TO_DETECT = 500

#: False-discovery rate the catalogue is screened at.
#:
#: THIS IS THE MOST IMPORTANT NUMBER IN THE FILE. Fifty pairs are tested for
#: cointegration at once. At a nominal 5% each, roughly two and a half of them
#: are expected to pass on pure chance -- measured directly on independent
#: random walks, this fit calls 3.3% of unrelated pairs cointegrated. So an
#: unadjusted screen that admits three pairs out of fifty has found exactly as
#: many as coin-flipping would, and reporting those three as discoveries would
#: be the entire replication crisis in miniature.
#:
#: Benjamini-Hochberg controls the expected proportion of false admissions among
#: those admitted, rather than the per-test error rate. It is less brutal than
#: Bonferroni, which at 0.05/50 = 0.001 would reject essentially everything a
#: five-year daily sample can establish.
FDR_Q = 0.05

#: Friction per pair group, round trip, in basis points.
#:
#: Only the india_* numbers describe trades this account can place. They match
#: universe.yaml: STT 20 + stamp duty 1.5 + exchange 0.6 + SEBI 0.02 +
#: brokerage 4.0 + GST 0.83 = 26.95 bps on a Rs 1,00,000 reference trade.
#:
#: The rest are estimates for instruments an Indian retail account cannot reach
#: at all, and they exist so the gate has SOMETHING to subtract rather than
#: flattering foreign pairs with zero cost. Every such pair is marked
#: observational, so its net edge is a statement about whether the linkage holds
#: -- never a profit estimate.
GROUP_FRICTION_BPS = {
    "india_sector": 26.95,
    "india_supply": 26.95,
    "india_group": 26.95,
    "india_index": 26.95,
    "equity_us": 10.0,     # commission-free, but two spreads plus SEC/TAF fees
    "fx": 4.0,             # major-pair spreads, retail
    "intermarket": 12.0,   # futures/ETF spreads plus commission
}
DEFAULT_FRICTION_BPS = 25.0


@dataclass(frozen=True)
class Relationship:
    """The estimated relationship, and everything needed to distrust it."""

    pair_id: str
    symbol_a: str
    symbol_b: str
    k: float                 # exp(alpha); the multiplicative constant
    beta: float              # elasticity of a with respect to b
    r_squared: float
    coint_pvalue: float
    spread_sd_bps: float
    ou: OUFit
    observations: int
    start: date
    end: date
    removed_rows: int

    @property
    def half_life_days(self) -> float | None:
        return self.ou.half_life

    def net_edge_at(self, sigmas: float, horizon: float, friction_bps: float) -> float:
        """Net basis points from a `sigmas`-sized deviation over the horizon."""
        return horizon_gate(
            sigmas * self.spread_sd_bps,
            self.ou,
            horizon_periods=horizon,
            friction_bps=friction_bps,
        ).net_after_friction_bps

    def horizon_noise_bps(self, horizon: float) -> float:
        """Standard deviation of the spread's move over the holding period.

        The expected reversion is a drift. This is the noise it has to be seen
        through, and on most of these pairs it is several times larger -- which
        is not a reason to refuse the trade, but is the reason a handful of
        wins proves nothing.
        """
        return self.ou.sigma * math.sqrt(horizon)

    def trades_to_detect(
        self, sigmas: float, horizon: float, friction_bps: float
    ) -> float:
        """How many such trades before the mean edge is 2 SE from zero.

        n = (2 * noise / edge)^2. This is the number that turns "positive
        expectancy" into a claim someone could actually check, and it is the
        honest answer to "how would I know if this stopped working".
        """
        edge = self.net_edge_at(sigmas, horizon, friction_bps)
        if edge <= 0:
            return float("inf")
        return (2 * self.horizon_noise_bps(horizon) / edge) ** 2


@dataclass(frozen=True)
class Admission:
    """Whether a pair is fit to run live, and why not when it is not."""

    pair_id: str
    admitted: bool
    reason: str
    net_edge_bps: float


def fit(
    pair_id: str, symbol_a: str, symbol_b: str, prices: pd.DataFrame
) -> Relationship:
    """Estimate the relationship from an aligned two-column price frame."""
    frame = prices[[symbol_a, symbol_b]].dropna()
    # Screen BEFORE fitting. Two bad prints out of 1239 once moved a spread's
    # standard deviation by a factor of 120 -- see linkage/quality.py.
    frame, report = screen(frame)
    if len(frame) < 60:
        raise ValueError(f"{pair_id}: only {len(frame)} usable observations")

    a, b = frame[symbol_a], frame[symbol_b]
    if (a <= 0).any() or (b <= 0).any():
        raise ValueError(f"{pair_id}: non-positive prices cannot be logged")

    # Fit on logs so beta is an elasticity and is scale-free. A ratio fitted on
    # raw prices silently encodes the price levels of the day it was fitted.
    log_a, log_b = np.log(a), np.log(b)
    model = sm.OLS(log_a.values, sm.add_constant(log_b.values)).fit()
    alpha, beta = float(model.params[0]), float(model.params[1])

    spread_bps = (log_a - (alpha + beta * log_b)) * 10_000

    # Cointegration is tested on LOGS, not on raw levels, because the spread
    # actually being traded is the log spread. Testing `coint(a, b)` while
    # trading `log a - beta log b` produces a p-value about a different
    # quantity -- and the two disagree exactly when beta is far from 1, which
    # is when the log form was worth using in the first place. Both are I(1),
    # so the test is equally valid either way; only one of them is the answer
    # to the question being asked.

    return Relationship(
        pair_id=pair_id,
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        k=float(np.exp(alpha)),
        beta=beta,
        r_squared=float(model.rsquared),
        coint_pvalue=float(coint(log_a, log_b)[1]),
        spread_sd_bps=float(spread_bps.std()),
        ou=fit_ou(spread_bps.values),
        observations=len(frame),
        start=frame.index[0].date(),
        end=frame.index[-1].date(),
        removed_rows=report.removed if report else 0,
    )


def bh_threshold(pvalues: list[float], q: float = FDR_Q) -> float:
    """Benjamini-Hochberg critical p-value for a family of tests.

    Sort ascending, find the largest i with p(i) <= (i/m) * q, and return that
    p(i). Nothing above it is admitted. With no p-value passing, the threshold
    is 0 and the honest conclusion is that the family contains no discovery --
    which is a result, not a failure to find one.
    """
    if not pvalues:
        return 0.0
    ordered = sorted(pvalues)
    m = len(ordered)
    passing = [p for i, p in enumerate(ordered, start=1) if p <= (i / m) * q]
    return max(passing) if passing else 0.0


def admit(
    spec: PairSpec,
    rel: Relationship,
    *,
    horizon: float,
    friction_bps: float,
    coint_threshold: float = 0.05,
) -> Admission:
    """The five tests, in the order that fails cheapest first.

    `coint_threshold` is 0.05 for a pair considered on its own and the
    Benjamini-Hochberg critical value when the whole catalogue is screened at
    once. The difference between those two numbers is the difference between a
    finding and a coincidence.
    """
    net = rel.net_edge_at(ADMISSION_SIGMAS, horizon, friction_bps)

    if rel.observations < MIN_OBSERVATIONS:
        return Admission(
            spec.id, False, f"only {rel.observations} observations", net
        )

    if rel.coint_pvalue > coint_threshold or coint_threshold <= 0:
        if coint_threshold >= 0.05:
            detail = f"p={rel.coint_pvalue:.3f}"
        elif coint_threshold <= 0:
            detail = (
                f"p={rel.coint_pvalue:.3f}; nothing in the catalogue survives "
                f"the multiple-testing correction"
            )
        else:
            detail = (
                f"p={rel.coint_pvalue:.3f}, needs <={coint_threshold:.4f} "
                f"once the catalogue is screened as one family"
            )
        return Admission(spec.id, False, f"not cointegrated ({detail})", net)

    if not rel.ou.reverts:
        return Admission(
            spec.id,
            False,
            f"reversion not separable from a random walk "
            f"(t={rel.ou.theta_tstat:+.2f})",
            net,
        )

    detect = rel.trades_to_detect(ADMISSION_SIGMAS, horizon, friction_bps)

    if net <= 0:
        return Admission(
            spec.id,
            False,
            f"{ADMISSION_SIGMAS:g}σ = {ADMISSION_SIGMAS * rel.spread_sd_bps:.0f}bps "
            f"reverts to {net + friction_bps:.0f}bps in {horizon:g}d, under "
            f"{friction_bps:.0f}bps friction",
            net,
        )

    if detect > MAX_TRADES_TO_DETECT:
        return Admission(
            spec.id,
            False,
            f"edge {net:+.0f}bps is real but unfalsifiable: {detect:.0f} trades "
            f"to tell it from zero",
            net,
        )

    return Admission(
        spec.id,
        True,
        f"{ADMISSION_SIGMAS:g}σ nets {net:+.0f}bps over {horizon:g}d "
        f"(half-life {rel.half_life_days:.1f}d, {detect:.0f} trades to confirm)",
        net,
    )


def compile_pair(
    spec: PairSpec, rel: Relationship, *, friction_bps: float
) -> LinkageConfig:
    """Write the fitted relationship down as an ordinary declared linkage.

    `a` is the reference leg and `k * b ** beta` is its fair value, so the
    spread is how far a has moved away from what b implies. Everything
    downstream then treats this exactly like an ADR against its local listing.
    """
    return LinkageConfig.model_validate(
        {
            "id": spec.id,
            "description": f"{spec.a} vs {spec.b} — fitted {spec.group} pair",
            "category": spec.access.category.value,
            "legs": {
                "a": {"symbol": spec.a, "provider": "yfinance"},
                "b": {"symbol": spec.b, "provider": "yfinance"},
            },
            "fair_value": "k * b ** beta",
            "params": {"k": round(rel.k, 8), "beta": round(rel.beta, 6)},
            "reference": "a",
            # One number rather than the itemised breakdown universe.yaml
            # carries: for the foreign groups it is an estimate, and itemising
            # an estimate would dress it up as sourced.
            "friction_bps": {"round_trip": friction_bps},
            "alert": {
                "warn_z": 1.8,
                "alert_z": 2.5,
                "min_net_edge_bps": 0.0,
                "cooldown_minutes": 180,
            },
        }
    )


# ---------------------------------------------------------------------------
# Fitting the whole catalogue
# ---------------------------------------------------------------------------


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
    return pd.DataFrame(out)


def fit_catalogue(
    catalogue: Catalogue, prices: pd.DataFrame, *, horizon: float
) -> list[tuple[PairSpec, Relationship | None, Admission]]:
    results = []
    for spec in catalogue.pairs:
        friction = GROUP_FRICTION_BPS.get(spec.group, DEFAULT_FRICTION_BPS)
        if spec.a not in prices or spec.b not in prices:
            missing = [s for s in (spec.a, spec.b) if s not in prices]
            results.append(
                (spec, None, Admission(spec.id, False, f"no data: {', '.join(missing)}", 0.0))
            )
            continue
        try:
            rel = fit(spec.id, spec.a, spec.b, prices)
        except (ValueError, KeyError) as exc:
            results.append((spec, None, Admission(spec.id, False, str(exc), 0.0)))
            continue
        results.append((spec, rel, None))

    # Screen the whole family at once. Judging each pair on its own 5% would
    # admit two or three from a catalogue of fifty by chance alone.
    threshold = bh_threshold([r.coint_pvalue for _, r, _ in results if r is not None])

    final = []
    for spec, rel, adm in results:
        if rel is None:
            final.append((spec, rel, adm))
            continue
        friction = GROUP_FRICTION_BPS.get(spec.group, DEFAULT_FRICTION_BPS)
        final.append(
            (
                spec,
                rel,
                admit(
                    spec,
                    rel,
                    horizon=horizon,
                    friction_bps=friction,
                    coint_threshold=threshold,
                ),
            )
        )
    return final


def to_universe_yaml(
    results: list[tuple[PairSpec, Relationship | None, Admission]],
    *,
    years: int,
    horizon: float,
) -> str:
    """Emit the admitted pairs as a universe the scanner can load directly."""
    admitted = [(s, r, a) for s, r, a in results if a.admitted and r is not None]

    header = [
        "# ══════════════════════════════════════════════════════════════════════",
        "# GENERATED by `python -m linkage.stat_pairs --fit`. Do not hand-edit:",
        "# the next fit overwrites it. Edit config/pairs.yaml instead.",
        "#",
        f"# Fitted {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC on {years}y of "
        f"daily closes, {horizon:g}-day horizon.",
        f"# {len(admitted)} of {len(results)} catalogue pairs admitted.",
        "#",
        "# Every `beta` and `k` below is ESTIMATED, not declared. That is the",
        "# difference between this file and universe.yaml, where the constants",
        "# come from 20-F filings and duty schedules. A fitted constant carries",
        "# the sampling error of the window it was fitted on, and it goes stale",
        "# as the relationship drifts -- which is why the Kalman filter runs on",
        "# `a ~ beta * fair_value` and beta drifting away from 1 is the signal",
        "# that this file needs regenerating.",
        "#",
        "# Refitting changes each linkage's state fingerprint, so stored detector",
        "# state is discarded automatically rather than resumed against a hedge",
        "# ratio that no longer applies.",
        "# ══════════════════════════════════════════════════════════════════════",
        "",
    ]

    if not admitted:
        header += [
            "# NOTHING WAS ADMITTED. That is a result, not a failure: at a",
            "# nominal 5% each, screening fifty pairs is expected to hand back",
            "# two or three relationships that do not exist, and correcting for",
            "# that leaves none of these standing. An empty universe here is the",
            "# honest output of the screen.",
            "",
            "linkages: []",
        ]
        return "\n".join(header) + "\n"

    header.append("linkages:")
    body = []
    for spec, rel, adm in admitted:
        friction = GROUP_FRICTION_BPS.get(spec.group, DEFAULT_FRICTION_BPS)
        linkage = compile_pair(spec, rel, friction_bps=friction)
        body += [
            "",
            f"  # {spec.mechanism.strip().replace(chr(10), ' ')}",
            f"  # BREAKS WHEN: {spec.breaks_when.strip()}",
            f"  # FIT: {rel.observations} obs {rel.start}..{rel.end}, "
            f"R²={rel.r_squared:.3f}, coint p={rel.coint_pvalue:.4f}, "
            f"SD={rel.spread_sd_bps:.0f}bps, half-life={rel.half_life_days:.1f}d "
            f"(t={rel.ou.theta_tstat:+.1f})",
            f"  # ACCESS: {spec.access.value} — {adm.reason}",
        ]
        body.append(
            yaml.safe_dump(
                [linkage.model_dump(mode="json")],
                sort_keys=False,
                default_flow_style=False,
                indent=2,
            ).rstrip()
            .replace("\n", "\n  ")
            .rjust(0)
        )
        body[-1] = "  " + body[-1]

    return "\n".join(header + body) + "\n"


def report(results: list[tuple[PairSpec, Relationship | None, Admission]]) -> str:
    admitted = [a for _, _, a in results if a.admitted]
    lines = [
        "",
        f"  {'pair':<26} {'coint p':>8} {'SD bps':>8} {'half-life':>10} "
        f"{'2σ net':>8} {'noise':>7}  verdict",
        "  " + "-" * 112,
    ]
    for spec, rel, adm in results:
        if rel is None:
            lines.append(
                f"  {spec.id:<26} {'':>8} {'':>8} {'':>10} {'':>8} {'':>7}  {adm.reason}"
            )
            continue
        hl = f"{rel.half_life_days:.1f}d" if rel.half_life_days else "none"
        mark = "ADMIT " if adm.admitted else "      "
        lines.append(
            f"  {spec.id:<26} {rel.coint_pvalue:>8.4f} {rel.spread_sd_bps:>8.0f} "
            f"{hl:>10} {adm.net_edge_bps:>+8.0f} {rel.horizon_noise_bps(3.0):>7.0f}  "
            f"{mark}{adm.reason}"
        )
    lines += [
        "",
        f"  {len(admitted)} of {len(results)} pairs admitted to the live scan.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit and admit statistical pairs.")
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE)
    parser.add_argument("--out", type=Path, default=FITTED)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--horizon", type=float, default=3.0)
    parser.add_argument("--fit", action="store_true", help="write the fitted universe")
    args = parser.parse_args()

    catalogue = load_catalogue(args.catalogue)
    symbols = sorted(catalogue.symbols())
    print(f"\nfitting {len(catalogue.pairs)} pairs over {len(symbols)} symbols...")

    prices = download(symbols, args.years)
    results = fit_catalogue(catalogue, prices, horizon=args.horizon)
    print(report(results))

    if args.fit:
        args.out.write_text(
            to_universe_yaml(results, years=args.years, horizon=args.horizon),
            encoding="utf-8",
        )
        print(f"  wrote {args.out}\n")


if __name__ == "__main__":
    main()
