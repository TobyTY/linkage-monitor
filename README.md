# Linkage Monitor

Cross-market relationship scanner for INR-denominated instruments.

Watches instruments whose prices are linked by a **computable** relationship —
an ADR against its local listing via USDINR, an ETF against the index it
tracks, gold in INR against XAUUSD with import duty and GST — detects when that
relationship breaks beyond its own historical tolerance, prices the friction
needed to actually capture the gap, and alerts only on what survives that
accounting.

It is not an arbitrage finder. The premise is the opposite: *most gaps are
fully explained by FX, duty, taxes and settlement lag, and the useful output is
the arithmetic that shows why.*

```
python -m linkage.scan --warmup 500 --interval 60     # watch
python -m linkage.backtest --pair gold_etf_pair       # score the rule
python -m linkage.profile_all                         # profile every pair
```

## What it found

The numbers below came out of this repo, not out of a paper. Several of them
argue against the project.

**Statistical pairs mostly do not cointegrate, and the ones that do change.**
Of 50 curated global pairs, 3 cointegrate over a 5-year window, 2 over 2 years,
4 over 3 years — and the sets barely overlap. Only WTI/Brent and EURUSD/USDCHF
survive more than one window. Of 16 Indian pairs, 1 cointegrates.

**Correlation is not the thing.** The three most correlated Indian pairs —
NIFTY/BANKNIFTY (+0.87), Bajaj Finance/Bajaj Finserv (+0.79), Adani
Enterprises/Adani Ports (+0.77) — were among the *worst* on cointegration.
Correlation is about returns moving together; cointegration is about levels
staying tied. A pair can have the first and none of the second.

**Computable beats statistical, by a lot.** Residual standard deviation: gold
ETF pair 19 bps, BANKBEES/index 24 bps, NIFTYBEES/index 32 bps — against
statistical pairs an order of magnitude wider. A relationship you can write
down as arithmetic is tighter than one you have to fit.

**The alerting rule beats a random entry and still loses money.** Walk-forward
on the gold ETF pair: **+13.59 bps** edge over the baseline of entering on every
eligible day, **−13.45 bps** after friction. That verdict — "beats baseline,
loses to friction" — is the honest headline.

**Open question.** In that backtest, 9 of 9 negative-z alerts were profitable
and 0 of 6 positive-z ones were. Perfect separation at n = 15 is a warning, not
a finding: the GOLDBEES/SETFGOLD ratio slid 0.974 → 0.969 over five years on an
expense-ratio differential, so the "edge" may be drift rather than reversion.
Unresolved; the de-trended re-run is the next thing to do.

## The near-miss worth reading

An early run reported **+1400 bps of net edge** on the gold ETF pair. It was
implausible, so it got investigated rather than celebrated.

`SETFGOLD.NS` prints 0.42 on 2022-01-06 and 2022-01-07 against a true price
near 43. Two rows out of 1239 — 0.16% of the sample — inflated the spread's
standard deviation from 28.3 bps to 1851 bps, a 120× error. No NaNs, no infs,
no gaps: every automated sanity check passed.

`linkage/quality.py` is the response. It screens for spikes that reverse (a
real 50% move persists; a bad print does not) and rejects outliers by median
absolute deviation rather than standard deviations, because a 3σ screen run on
contaminated data inflates its own threshold. Both report what they removed.
The corrected pair: 28.3 bps SD, 2.38-day half-life, t = −14.5, needing roughly
2σ to clear 26.95 bps of friction.

## How it decides

Three detectors, composed, each covering a specific way the others are wrong.

| | does | fails alone by |
|---|---|---|
| **Kalman** (`kalman.py`) | tracks a drifting hedge ratio; emits a z from its *own* predicted variance | firing on deviations that take six weeks to come back |
| **Empirical quantile** (`thresholds.py`) | scores against what this pair actually does | nothing — but a σ threshold in its place fires several times more often than the arithmetic promises |
| **OU horizon gate** (`ou.py`) | asks how much reverts *inside the holding period*, net of friction | scoring against a hedge ratio that stopped being true a year ago |

Two details do real work:

- The filter runs on `reference ~ β · fair_value`, not on the raw spread. If the
  config's conversion constants are right, β sits at 1. When one goes stale — an
  ADR ratio changes, an ETF's units-per-gram drifts — β moves and the filter
  absorbs it, so staleness appears as visible drift instead of a permanent fake
  arbitrage that alerts forever.
- θ must be statistically separable from zero (`MIN_THETA_TSTAT = 2.0`). Fitting
  AR(1) to a pure random walk returns a small positive θ nearly every time,
  which then reads as a 600-day half-life and a slow but real relationship. It
  is neither. Adding this check moved two pairs in this repo from "cointegrated,
  slow" to "cannot tell".

## Persistence

Detector state is loaded at startup and written every cycle, so a restart costs
seconds rather than a hundred cycles of warming up in public.

State is only resumed when it still means the same thing. Each row carries a
fingerprint of the linkage definition that produced it — legs, formula, params,
reference leg — and a mismatch discards the state and says so. Friction and
alert thresholds are deliberately *outside* the fingerprint: they are applied
fresh to every verdict and accumulate in nothing, so correcting a brokerage
number must not throw away a month of history.

Resuming is gated on readiness rather than on a row existing. The first live run
of this scanner happened on a closed market: every quote was stale, every
detector learned nothing, and a row was written anyway — after which every
later run skipped its own history replay because state "existed", while
printing a line saying everything had resumed.

Alerts and observations are append-only, each alert storing what the model
predicted at the moment it fired. A backtest says the rule *would* have worked;
only a log of live alerts says whether it did.

```
cp .env.example .env        # LINKAGE_DATABASE_URL, or run --no-db
```

Any SQLAlchemy URL works — `sqlite:///linkage.db` is enough for one machine.
There are no migrations here, unlike the ledger project: every row is either
disposable state or reconstructible from market data, so the cost of being
wrong is a re-warm rather than a lost record.

## Config

A linkage is declared, not coded. `config/universe.yaml` holds 15 linkages over
29 instruments; `config/pairs.yaml` holds 50 statistical pairs with the
mechanism that ties each one and the conditions that break it (`PAIRS.md` is the
generated reference).

Validation happens at load time, on a laptop, rather than at 09:15 when the
market opens. The check that earns its keep: every name in a `fair_value`
expression must be a declared leg or param, so a typo fails at startup instead
of silently resolving to nothing for one pair, once, quietly.

Friction is itemised, not assumed — STT 20 bps round trip, stamp duty 1.5,
exchange transaction 0.6, SEBI 0.02, brokerage 4.0, GST 0.83 → **26.95 bps** on
a ₹1,00,000 NSE trade. Each linkage also records whether a net-edge number means
anything: `validation` (a mathematical identity, present to prove the engine
works against a known answer), `observational` (real, but not both legs
reachable from an Indian retail account), or `tradeable`.

The validation lane currently lands at −1.4 / −5.8 / +2.4 / −13.1 bps across
four triangular FX identities, which is the engine confirming its own
arithmetic.

## Known data issues

- `AUDINR=X` and several NSE symbols fail intermittently from yfinance —
  present on one run, "possibly delisted" on the next. Warmup skips them and
  says which.
- `TATAMOTORS.NS` delisted in the 2025 demerger and the successor has ~24 bars,
  so `M&M.NS` was substituted.
- ADR conversion constants use the ratios filed in each 20-F rather than fitted
  values. Fitting on daily closes assumes simultaneous closing prints, but NSE
  closes at 10:00 UTC and NYSE at 21:00, so every ADR observation carries 11
  hours of overnight move that the fit bakes into the constant. Same-session
  pairs are unaffected.

## Tests

```
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m pytest
```

78 tests. The ones that matter:

- `test_persistence.py::test_a_restart_is_invisible_to_the_verdict` — the same
  series through two detectors, one saved and reloaded halfway, demanding an
  identical verdict. A field left out of `snapshot()` shows up here as a
  divergence rather than as a quiet production bug.
- `test_formula.py` fires eight real sandbox escapes at the expression
  evaluator, including `__import__('os').system(...)` and
  `().__class__.__bases__[0].__subclasses__()`.
- `test_detectors.py` checks that a random walk is reported as "cannot tell"
  rather than as slow reversion.

## Not built yet

News and event scoring (surprise against consensus, event study, calibrated
confidence); statistical pairs are profiled but not wired into the live scan;
Telegram delivery; dashboard.
