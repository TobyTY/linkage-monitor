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
python -m linkage.backtest --pair gold_etf_pair --detrend   # was it drift?
python -m linkage.stat_pairs --fit                    # screen the 50 pairs
python -m linkage.events --symbol INFY.NS             # event study
python -m linkage.events --universe                   # who reports soon
python -m linkage.dashboard --out dashboard.html      # what it knows
python -m linkage.profile_all                         # profile every pair
```

## What it found

The numbers below came out of this repo, not out of a paper. Several of them
argue against the project.

**Not one of the 50 statistical pairs survives an honest screen.** Judged
individually at 5%, three qualify: EURUSD/USDCHF, WTI/Brent, RELIANCE/ONGC. But
fifty simultaneous tests at 5% are *expected* to return two or three false
positives — measured directly here, this fit calls 3.3% of unrelated random
walks cointegrated — so three out of fifty is exactly what coin-flipping
produces. Correcting the family with Benjamini-Hochberg leaves **zero**: the
smallest p-value is 0.0050 against a rank-1 critical value of 0.00102. The
generated universe of tradeable statistical pairs is an empty file, and that is
the honest output rather than a failure to find something.

**Cointegration tested on levels answers a different question than a log hedge
ratio asks.** The p-value was computed on raw prices while beta was fitted on
logs, so it described a different spread than the one being traded. The two
disagree exactly when beta is far from 1 — TATASTEEL/TATAPOWER moves from
p=0.38 to p=0.005 — which is precisely when the log form was worth using.

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
on the gold ETF pair: **+13.10 bps** edge over the baseline of entering on every
eligible day, **−13.93 bps** after friction. That verdict — "beats baseline,
loses to friction" — is the honest headline.

(Every backtest number on this page uses `--warmup 550`. De-trending needs 250
observations before it can produce anything, so a plain run at the default
warmup would be scored over a longer history than the de-trended one it is
compared against. Raising both to 550 buys the comparison identical days, at the
cost of a shorter sample.)

**That verdict was the drift, not the pair — and it replicates.** The same
backtest fired 8 of 9 profitable alerts below the mean and 0 of 6 above it.
Separation that clean is a warning rather than a finding: the GOLDBEES/SETFGOLD
ratio slid 0.974 → 0.969 over five years on an expense-ratio differential, so
the rule was plausibly booking a trend as if it were reversion. Removing a
**causal** rolling trend (`--detrend`) and re-running over identical days, on
all three tradeable linkages rather than one:

| | plain edge | plain net | de-trended edge | de-trended net |
|---|---|---|---|---|
| gold ETF pair | +13.10 bps | −13.93 bps | +42.23 bps | **+15.29 bps** |
| NIFTYBEES/index | −26.64 bps | −52.10 bps | +44.78 bps | **+17.76 bps** |
| BANKBEES/index | −8.89 bps | −35.08 bps | +82.03 bps | **+55.05 bps** |

The one-sided direction signature collapses every time. Plain, the three fired
0/5, 23/23 and 0/25 of their alerts on a single side of the mean. De-trended,
all three fire on both sides and win on both.

**Believe that only as far as the null test allows.** Subtracting a locally
fitted trend induces negative autocorrelation in what remains — the residual is
pulled toward a line fitted to its own recent past — which is how the
Hodrick-Prescott filter invents business cycles in data that has none. So the
same pipeline was pointed at series whose answer is known before it runs:
random walks, drifting random walks, and a true OU process. De-trending a random
walk produces no edge, and the reverting control is still found
(`tests/test_backtest_null.py`). The filter is not manufacturing the result.

**What that still does not establish.** Alert counts are 13, 13 and 8 — small,
and the de-trend window of 250 days was chosen rather than searched. The two
index pairs also overlap in time and both track Indian equity, so three pairs is
not three independent samples. This is a hypothesis that has now survived three
attempts to kill it instead of one, which is a different thing from an edge.

**The first version of this table was contaminated, and finding out is the
story.** Before the stale-print screen existed, both index pairs showed a −6
sigma alert on 2025-03-18 that was the single largest contributor to each. It
was not a market event. Yahoo returned NIFTYBEES.NS at 252.179993 and
BANKBEES.NS at 495.859985 — exactly their previous closes, to the last decimal —
while the indices they track moved +1.45% and +1.99%. The ETF leg simply did not
update. The detector read the gap as a divergence and the next day's catch-up as
a reversion.

Nothing already in `quality.py` could see it: nothing spiked, and neither price
was an outlier in level. The alert was also untradeable in the most basic sense,
since the price it fired on never existed. And because the same bad date hit two
pairs at once, it was quietly making two "independent replications" into one
observation. `find_stale_prints` is the response — an exact repeat of the
previous close on a day another leg moved more than 0.5%. The numbers in the
table above are all post-screen.

**The Kalman filter was answering a question about units.** The validation lane
exists so that an engine bug shows up somewhere the answer is known in advance,
and it did. The dashboard reported beta drift of 5.63% on `audinr_triangular`,
3.14% on `eurinr` and 2.54% on `jpyinr` — linkages whose beta is **1 by
construction**, because a triangular FX identity cannot have any other hedge
ratio. Fitted directly on two years of closes, the true ratio is 0.99801. The
filter was wrong, not the data.

`Q` is a prior on how far the slope moves per step and `R` a prior on
observation noise, and both are *absolute* variances. But the slope's
contribution to the predicted variance is `x² · P[0,0]`, so the same `delta`
means something entirely different at x = 0.6 than at x = 56,000 — and this
universe spans both, JPYINR quoting at 0.62 and BANKNIFTY at 56,606. Multiplying
**both** legs of the AUDINR identity by a constant, which cannot change a ratio:

| both legs scaled by | beta (true 0.998) | z sd | \|z\| > 2 |
|---|---|---|---|
| ×0.01 | 0.783 | 0.08 | **never fired** |
| ×1 | 0.962 | 0.64 | 1.9% |
| ×100 | 1.003 | 0.66 | 2.2% |

The low end is the dangerous end. A detector that silently stops firing is
indistinguishable from a market with nothing to report, and JPYINR lives there.
Both legs are now divided by a scale fixed at the first observation; beta is
invariant under a common scaling, and z is too, because innovation scales with
*s* while S scales with *s²*.

**Normalising then exposed that neither prior had ever been measured.** `delta`
was 1e-4 — a per-step slope standard deviation of 0.01, compounding to a ±22%
random walk over 500 observations. Beta was absorbing the spread instead of
reporting it, and z collapsed to sd 0.42, so the detector fired at roughly a
fifth of its nominal rate:

| delta | beta | z sd | \|z\| > 2 |
|---|---|---|---|
| 1e-4 *(old)* | 0.816 | 0.42 | 1.0% |
| 1e-6 | 0.911 | 1.06 | 5.8% |
| **1e-7** *(now)* | 0.976 | 1.14 | 6.5% |
| 1e-8 | 0.997 | 1.17 | 6.7% |

`delta` is now 1e-7 and is still a *stated* prior rather than a fit: a per-step
sd of 3.2e-4, so a hedge ratio may drift about half a percent over a trading
year. 1e-8 fits this particular identity better precisely because its beta is
constant — and choosing it for that reason would be tuning on the answer, which
is the thing this file keeps refusing to do.

Every stored detector state was fitted by the broken filter, so `STATE_VERSION`
is bumped to 2 and all fifteen are discarded on the next scan rather than
resumed. The empirical threshold had been quietly absorbing some of this: it
scores against what a pair actually does, so an under-dispersed z still produced
sensible percentiles. That is the layer earning its place, not an excuse for the
layer beneath it.

**The backtest does not replay the whole detector, and that bounds every number
above it.** The live detector composes three things — the Kalman's normalised
innovation, the empirical percentile, and the OU horizon gate. `backtest.py`
replays the second and third. It never constructs a `KalmanHedge`; the z in its
output is a percentile score, not a filter innovation.

So "the alerting rule beats a random entry" is a claim about the threshold and
the gate. It is not evidence about the filter — and the filter is the component
most likely to be wrong, because it carries state across every observation while
the other two are recomputed from a trailing window each step. It *was* wrong,
for as long as this repo has existed, and nothing in the backtest could have
found it. The validation linkages did.

Replaying the Kalman across a walk-forward means persisting and restoring filter
state at each step. That is worth doing and is not done yet, and until it is,
the backtest numbers and the filter are two separate pieces of evidence rather
than one.

**The reversion test was admitting 29% of random walks.** `MIN_THETA_TSTAT` was
2.0, which is what a t-table gives for 5% significance. But the fit — the change
in the spread regressed on its own lagged level, with a constant — *is* the
Dickey-Fuller regression, and under the null of a random walk its t-statistic
does not follow Student's t. It follows the Dickey-Fuller τ_μ distribution,
which sits well to the left. Measured over 3000 simulated random walks per
length:

| cut-off | admitted as "reverting" |
|---|---|
| 2.00 | 29% |
| 2.57 | 10% |
| **2.86** | **5%** |
| 3.43 | 1% |

The simulation reproduces the published critical values to within 0.05. The
check that existed specifically to keep random walks out was letting through
nearly a third of them. Now 2.86. The gold pair is unaffected (t = −14.5), which
is itself worth knowing: the result above does not depend on the loose gate.

**The consensus surprise predicts almost nothing about the move after it.**
R² of 0.031 on INFY (p=0.41) and 0.001 on RELIANCE (p=0.88), measured on 3-day
abnormal returns net of NIFTY across ~24 events each. That is the expected
result rather than a broken fit — the estimate is public and the market has
already priced its own view of it — and it means the original premise, *news
gives a projected dip or rise*, is mostly untrue for scheduled events.

**And the confidence interval was lying.** Walk-forward, an 80% interval built
from empirical residual quantiles caught 50% and 36% of held-out outcomes. Two
causes, both diagnosable: an 80% interval estimated from twelve residuals is
biased inward, and residual quantiles ignore parameter uncertainty entirely. A
proper OLS prediction interval lifts measured coverage from 57% to 66% pooled
across four symbols — better, and still short, because event returns are
fat-tailed and the samples are small. No formula fixes that, so the nominal
figure is never shown alone: every projection prints its measured coverage
beside it and refuses to call itself calibrated until the two agree.

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
- θ must be statistically separable from zero (`MIN_THETA_TSTAT = 2.86`). Fitting
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

## Statistical pairs

`config/pairs.yaml` holds 50 curated pairs with the mechanism that ties each one
and the condition that breaks it. `stat_pairs --fit` estimates each relationship
and compiles the survivors into ordinary linkages —

```yaml
fair_value: k * b ** beta
params: {k: 1.0034, beta: 0.9734}
```

— so from there nothing downstream knows they were ever different. They get
the same validation, Kalman, threshold, horizon gate, friction and persistence
as an ADR. Refitting changes the state fingerprint, so stale detector state is
discarded without anything having to remember to.

A pair must clear five tests, and the last two do the work:

| test | refuses |
|---|---|
| 250+ observations | too little history to fit |
| cointegrated after FDR correction | what chance alone produced |
| θ separable from zero at the Dickey-Fuller value | a random walk |
| a 2σ deviation beats friction over the horizon | real relationships too small to trade |
| the edge is reachable in a survivable number of trades | positive expectancy nobody could ever verify |

The last one reports `trades_to_detect` — how many trades before the mean edge
is two standard errors from zero. Expected reversion is a drift, and the noise
it hides under is typically several times larger. A pair needing two thousand
trades has an edge that is real on paper and unfalsifiable in practice.

Not one of the 50 has `access: full` — none has both legs shortable from a
Groww account — so every statistical pair here is observational by
construction.

## Events

`events.py` studies scheduled earnings: consensus surprise against the abnormal
move over the horizon, net of the listing's index.

Earnings rather than headlines, deliberately. A confidence number is only honest
if it was measured against outcomes, and measuring needs events that are dated,
labelled and numerous. Free news feeds give recent headlines with no history, so
anything trained on them would carry a confidence that was asserted rather than
observed.

The most useful output is not the projection — it is the **suppression**. An
earnings date inside the holding horizon is the `breaks_when` clause written
against nearly every equity pair in the catalogue. A spread that diverges the
day before results is the relationship being tested, not one about to revert,
and entering there is the most expensive thing this system could do while
looking like a perfectly ordinary alert. The scan blocks those and says which
leg reports when.

## Alerts and the dashboard

Alerts go to the console and to any configured channel — **ntfy, Discord or
Telegram** — through one renderer. Two renderers would mean two versions of what
an alert said, and the one that gets read is the one nobody checked. Every
message carries the whole arithmetic (z, percentile, half-life and its
t-statistic, expected reversion, friction, net) because the recipient is on a
phone and cannot open a terminal to check it.

Three channels because at least one should be reachable in two minutes.
Telegram needs a bot registration, a token, a message sent to the bot before it
will talk back, and a chat id dug out of a `getUpdates` response. ntfy needs a
topic name and nothing else — no account anywhere. Discord needs one webhook URL
and posts into a channel rather than a private chat, so more than one person can
watch. Each trims to its own limit rather than the renderer trimming once, since
Discord cuts at 2000 characters and Telegram allows 4096, and a shared cap would
shorten every Telegram alert for no reason.

On the public ntfy server the topic *is* the password: anyone who guesses it
reads the alerts. Acceptable here, because the alerts are prices, z-scores and
public instrument names — and `NTFY_SERVER` points at a self-hosted instance for
when it stops being acceptable.

Credentials are checked at startup with `--verify-alerts`, not at the first
alert. A bad token is silent until something fires, which may be days away and
is exactly the moment it needs to work.

Delivery failure never stops detection: alerts are written to the database
*before* they are sent, configuring no channel at all is the normal case, and
four real transport failures plus the HTTP-200-with-`ok:false` case are fired at
the notifiers under test.

`dashboard.py` writes one self-contained HTML file from the database — no
server, because a dashboard that needs a process running is down exactly when
someone thinks to look at it. Three of its four panels are about doubt (beta
drift, config drift, feed coverage). The fourth joins each alert to what the
spread actually did a horizon later against what the model predicted at the
time. It is the only panel that can make the system look bad, which is why it
is there.

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

155 tests. The ones that matter:

- `test_persistence.py::test_a_restart_is_invisible_to_the_verdict` — the same
  series through two detectors, one saved and reloaded halfway, demanding an
  identical verdict. A field left out of `snapshot()` shows up here as a
  divergence rather than as a quiet production bug.
- `test_backtest_null.py` runs the whole scoring pipeline on series whose
  answer is known in advance — random walks, drifting random walks, a true OU
  process. Without it, "+13 bps of edge" has no scale to be read against.
- `test_formula.py` fires eight real sandbox escapes at the expression
  evaluator, including `__import__('os').system(...)` and
  `().__class__.__bases__[0].__subclasses__()`.
- `test_detectors.py` checks that a random walk is reported as "cannot tell"
  rather than as slow reversion.
- `test_stat_pairs.py` asserts the false-positive RATE on unrelated random
  walks rather than the verdict on one draw — a single seed passing or failing
  is exactly the mistake the multiple-testing correction exists to prevent.
- `test_dashboard.py` pins the three details that decide whether the outcome
  column is honest: absolute rather than signed moves, open horizons reported
  rather than dropped, and no credit for a reversion that happened inside the
  horizon.

## Not built yet

Headline and unscheduled-news scoring — the event engine covers scheduled
events only, and calibrating anything on headlines needs labelled history that
free feeds do not provide. Intraday data: everything here is daily closes, so
the half-lives and thresholds describe a daily world while the scanner runs by
the minute. The de-trended
backtest result has replicated on all three tradeable linkages, but on 13, 13
and 8 alerts, and the two index pairs are not independent of each other.
