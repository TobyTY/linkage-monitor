# Pairs Reference

Measured 2026-09-12 over 5 years of split- and dividend-adjusted daily closes.

## How to read this

**Correlation is measured on returns, not levels.** Any two series that both trend upward show a high level-correlation; it records that both went up and nothing else.

**Cointegration is tested on levels.** That is the opposite convention and it is the correct one — cointegration is the claim that two non-stationary series have a stationary linear combination.

**Half-life is the filter that matters for a 48–72h horizon.** A pair can be beautifully cointegrated on a forty-day reversion cycle and be useless inside three days. Half-life turns *this relationship is real* into *this relationship is real and reachable in the time I have*.

**A hedge ratio β is fitted on log prices**, so it is an elasticity and scale-free. A ratio fitted on raw prices silently encodes the price level of the day it was fitted.

**Result: 3 of 50 pairs cointegrate at 5%. 0 of those revert inside a 72-hour horizon.**

## Summary

| pair | ret corr | EG p | cointegrated | half-life | verdict |
|---|---|---|---|---|---|
| `eurusd_gbpusd` | +0.78 | 0.054 | no | 40d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `eurusd_usdchf` | -0.76 | 0.034 | **yes** | 62d | COINTEGRATED but slow — 62d half-life |
| `audusd_nzdusd` | +0.90 | 0.943 | no | 238d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `audusd_usdcad` | -0.74 | 0.718 | no | 92d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `audusd_gold` | +0.11 | 0.299 | no | 64d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `usdcad_wti` | -0.03 | 0.189 | no | 52d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `usdjpy_us10y` | +0.02 | 0.189 | no | 23d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `eurjpy_gbpjpy` | +0.83 | 0.176 | no | 36d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `gbpusd_gbpjpy` | +0.40 | 0.157 | no | 78d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `usdmxn_wti` | -0.01 | 0.727 | no | 163d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `eurusd_eurgbp` | +0.10 | 0.638 | no | 113d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `usdsgd_usdcnh` | — | — | — | — | usdsgd_usdcnh: only 1 usable observations |
| `usdzar_gold` | -0.02 | 0.198 | no | 29d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `audjpy_spx` | -0.03 | 0.247 | no | 63d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `spx_ndx` | +0.95 | 0.052 | no | 73d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `spx_vix` | -0.75 | 0.987 | no | 321d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `spx_rut` | +0.85 | 0.193 | no | 81d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `dax_stoxx` | +0.95 | 0.705 | no | 127d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `ftse_gbpusd` | +0.01 | 0.472 | no | 94d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `spx_dax` | +0.46 | 0.495 | no | 39d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `asx_em` | +0.19 | 0.476 | no | 41d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `gold_silver` | +0.77 | 0.240 | no | 60d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `copper_spx` | +0.25 | 0.097 | no | 40d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `wti_brent` | +0.95 | 0.011 | **yes** | 7d | COINTEGRATED but slow — 7d half-life |
| `cvx_xom` | +0.85 | 0.150 | no | 65d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `ko_pep` | +0.68 | 0.859 | no | 171d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `v_ma` | +0.88 | 0.079 | no | 33d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `hd_low` | +0.88 | 0.186 | no | 54d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `f_gm` | +0.74 | 0.053 | no | 48d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `jpm_bac` | +0.80 | 0.683 | no | 223d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `wmt_tgt` | +0.34 | 0.917 | no | 276d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `nvda_amd` | +0.66 | 0.746 | no | 327d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `fdx_ups` | +0.59 | 0.627 | no | 91d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `msft_aapl` | +0.53 | 0.536 | no | 104d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `hdfc_icici` | +0.50 | 0.584 | no | 76d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `tcs_infy` | +0.73 | 0.450 | no | 96d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `maruti_mm` | +0.48 | 0.119 | no | 41d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `reliance_ongc` | +0.35 | 0.022 | **yes** | 31d | COINTEGRATED but slow — 31d half-life |
| `apollo_fortis` | +0.29 | 0.315 | no | 28d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `maruti_motherson` | +0.36 | 0.773 | no | 98d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `ultracemco_dlf` | +0.48 | 0.573 | no | 79d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `indigo_bpcl` | +0.38 | 0.088 | no | 39d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `asianpaint_crude` | -0.14 | 0.108 | no | 75d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `hul_godrej` | +0.46 | 0.150 | no | 51d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `tatasteel_tatapower` | +0.51 | 0.380 | no | 46d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `adanient_adaniports` | +0.77 | 0.240 | no | 79d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `bajfinance_bajajfinserv` | +0.79 | 0.542 | no | 78d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `nifty_banknifty` | +0.87 | 0.721 | no | 121d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `niftyit_usdinr` | -0.10 | 0.704 | no | 141d | NOT COINTEGRATED — correlation only, no tradeable spread |
| `niftyfmcg_niftymetal` | +0.34 | 0.928 | no | 320d | NOT COINTEGRATED — correlation only, no tradeable spread |

## Foreign Exchange

#### `eurusd_gbpusd` — EURUSD=X vs GBPUSD=X

**Mechanism.** Both quote a European currency against the USD, so a large share of each move is the USD leg they share. Eurozone-UK trade dependency reinforces it.

**Breaks when.** UK-specific shocks — a Bank of England divergence, or another Brexit-class event.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1300 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.782 |
| Rolling 60d corr (now / min / max) | +0.81 / +0.57 / +0.91 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.0539 |
| ADF p-value on spread | 0.0126 |
| Hedge ratio β (log-log) | +0.9135 |
| R² | 0.865 |
| Spread SD | 170 bps |
| Half-life | 40.2 days |
| Current z | +0.30 |
| Max historical \|z\| | 2.44 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `eurusd_usdchf` — EURUSD=X vs USDCHF=X

**Mechanism.** Near-mirror by construction: EUR/USD has USD in the denominator, USD/CHF in the numerator, and CHF tracks EUR closely through the SNB's management. One of the most reliable inverse relationships in FX.

**Breaks when.** SNB policy shifts — the 2015 floor removal moved this 20%+ in minutes.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1300 days, 2021-09-13 → 2026-09-11 |
| Return correlation | -0.762 |
| Rolling 60d corr (now / min / max) | -0.87 / -0.94 / -0.37 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.0338 |
| ADF p-value on spread | 0.0095 |
| Hedge ratio β (log-log) | -0.5471 |
| R² | 0.644 |
| Spread SD | 277 bps |
| Half-life | 61.9 days |
| Current z | +0.42 |
| Max historical \|z\| | 3.55 |

**Verdict.** COINTEGRATED but slow — 62d half-life


#### `audusd_nzdusd` — AUDUSD=X vs NZDUSD=X

**Mechanism.** Trans-Tasman trade integration and shared exposure to Chinese demand. Historically among the highest correlations in liquid FX.

**Breaks when.** RBA/RBNZ policy divergence, or a dairy-versus-iron-ore terms-of-trade split.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1301 days, 2021-09-13 → 2026-09-12 |
| Return correlation | +0.897 |
| Rolling 60d corr (now / min / max) | +0.74 / +0.73 / +0.97 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.9435 |
| ADF p-value on spread | 0.8552 |
| Hedge ratio β (log-log) | +0.5925 |
| R² | 0.521 |
| Spread SD | 320 bps |
| Half-life | 238.5 days |
| Current z | +2.82 |
| Max historical \|z\| | 2.94 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `audusd_usdcad` — AUDUSD=X vs USDCAD=X

**Mechanism.** Both commodity currencies, quoted opposite ways round, so the raw correlation is negative. AUD carries metals and bulk, CAD carries crude.

**Breaks when.** Oil and metals decoupling — common, and the usual cause of drift here.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1301 days, 2021-09-13 → 2026-09-12 |
| Return correlation | -0.742 |
| Rolling 60d corr (now / min / max) | -0.45 / -0.90 / -0.43 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.7177 |
| ADF p-value on spread | 0.4698 |
| Hedge ratio β (log-log) | -0.9236 |
| R² | 0.510 |
| Spread SD | 324 bps |
| Half-life | 91.9 days |
| Current z | +2.62 |
| Max historical \|z\| | 2.70 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `audusd_gold` — AUDUSD=X vs GC=F

**Mechanism.** Australia is a major gold exporter, so AUD historically tracked bullion.

**Breaks when.** Already weakened. This relationship was strong through the 2010s and has decayed as AUD became more a China-growth proxy than a gold proxy. A good test case for whether the profiler detects a decayed relationship.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1256 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.110 |
| Rolling 60d corr (now / min / max) | +0.13 / -0.28 / +0.43 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.2992 |
| ADF p-value on spread | 0.1343 |
| Hedge ratio β (log-log) | -0.0071 |
| R² | 0.003 |
| Spread SD | 463 bps |
| Half-life | 64.2 days |
| Current z | +1.37 |
| Max historical \|z\| | 2.65 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `usdcad_wti` — USDCAD=X vs CL=F

**Mechanism.** Canada is a major oil exporter; higher crude strengthens CAD, pushing USD/CAD down. One of the more durable commodity-currency links.

**Breaks when.** Widening WCS-WTI differentials, or pipeline capacity shocks.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1256 days, 2021-09-13 → 2026-09-11 |
| Return correlation | -0.030 |
| Rolling 60d corr (now / min / max) | -0.22 / -0.32 / +0.34 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.1888 |
| ADF p-value on spread | 0.0774 |
| Hedge ratio β (log-log) | -0.1133 |
| R² | 0.259 |
| Spread SD | 308 bps |
| Half-life | 52.1 days |
| Current z | +1.68 |
| Max historical \|z\| | 2.81 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `usdjpy_us10y` — USDJPY=X vs ^TNX

**Mechanism.** The clearest macro relationship on this list. USD/JPY is driven by the Fed-BoJ rate differential, so it tracks US 10-year yields closely.

**Breaks when.** BoJ yield-curve-control changes, or risk-off flows into JPY overwhelming the carry.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1173 days, 2022-01-06 → 2026-09-11 |
| Return correlation | +0.020 |
| Rolling 60d corr (now / min / max) | -0.06 / -0.27 / +0.37 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.1892 |
| ADF p-value on spread | 0.0556 |
| Hedge ratio β (log-log) | +0.3475 |
| R² | 0.792 |
| Spread SD | 366 bps |
| Half-life | 22.9 days |
| Current z | -0.85 |
| Max historical \|z\| | 2.66 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `eurjpy_gbpjpy` — EURJPY=X vs GBPJPY=X

**Mechanism.** Both are JPY crosses and function as risk-on/risk-off barometers; they share the JPY leg.

**Breaks when.** EUR-GBP divergence, which is itself a tradeable pair.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1300 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.830 |
| Rolling 60d corr (now / min / max) | +0.92 / +0.66 / +0.95 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.1756 |
| ADF p-value on spread | 0.0612 |
| Hedge ratio β (log-log) | +1.0077 |
| R² | 0.975 |
| Spread SD | 175 bps |
| Half-life | 35.8 days |
| Current z | +0.36 |
| Max historical \|z\| | 2.70 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `gbpusd_gbpjpy` — GBPUSD=X vs GBPJPY=X

**Mechanism.** Shared GBP leg. GBP/JPY swings wider because JPY adds safe-haven flow.

**Breaks when.** JPY-specific risk episodes decoupling the yen from the dollar.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1300 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.399 |
| Rolling 60d corr (now / min / max) | +0.18 / -0.16 / +0.86 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.1568 |
| ADF p-value on spread | 0.0615 |
| Hedge ratio β (log-log) | +0.1764 |
| R² | 0.163 |
| Spread SD | 432 bps |
| Half-life | 78.3 days |
| Current z | +0.71 |
| Max historical \|z\| | 3.47 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `usdmxn_wti` — USDMXN=X vs CL=F

**Mechanism.** MXN as an EM commodity proxy tied to US oil demand and Mexican production.

**Breaks when.** Weaker than the CAD-oil link. MXN is heavily driven by carry and US political risk, both of which can swamp the oil channel entirely.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1256 days, 2021-09-13 → 2026-09-11 |
| Return correlation | -0.014 |
| Rolling 60d corr (now / min / max) | -0.10 / -0.41 / +0.33 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.7273 |
| ADF p-value on spread | 0.5181 |
| Hedge ratio β (log-log) | +0.0428 |
| R² | 0.009 |
| Spread SD | 713 bps |
| Half-life | 163.4 days |
| Current z | -1.50 |
| Max historical \|z\| | 2.17 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `eurusd_eurgbp` — EURUSD=X vs EURGBP=X

**Mechanism.** A triangular identity in disguise: EURUSD = EURGBP x GBPUSD. Not a statistical relationship at all — it is arithmetic, and belongs with the validation linkages.

**Breaks when.** Never. If this one drifts, the data is wrong.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1300 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.099 |
| Rolling 60d corr (now / min / max) | +0.06 / -0.28 / +0.68 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.6380 |
| ADF p-value on spread | 0.3839 |
| Hedge ratio β (log-log) | +0.3264 |
| R² | 0.016 |
| Spread SD | 460 bps |
| Half-life | 113.1 days |
| Current z | +1.14 |
| Max historical \|z\| | 3.60 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `usdsgd_usdcnh` — USDSGD=X vs USDCNH=X

**Mechanism.** The MAS manages SGD against a trade-weighted basket in which CNH carries heavy weight, making SGD a partial CNH proxy.

**Breaks when.** PBoC fixing interventions, or an MAS policy-band reset.

**Access.** `none` — at least one leg unreachable from an Indian retail account

**Measured.** Could not profile: usdsgd_usdcnh: only 1 usable observations


#### `usdzar_gold` — USDZAR=X vs GC=F

**Mechanism.** South Africa is a major precious-metals exporter; gold strength supports ZAR.

**Breaks when.** Domestic South African risk — load-shedding, fiscal stress, political shocks — routinely overwhelms the commodity channel.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1256 days, 2021-09-13 → 2026-09-11 |
| Return correlation | -0.020 |
| Rolling 60d corr (now / min / max) | -0.16 / -0.36 / +0.32 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.1976 |
| ADF p-value on spread | 0.0760 |
| Hedge ratio β (log-log) | -0.0156 |
| R² | 0.005 |
| Spread SD | 731 bps |
| Half-life | 29.2 days |
| Current z | -0.81 |
| Max historical \|z\| | 2.89 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `audjpy_spx` — AUDJPY=X vs ^GSPC

**Mechanism.** The classic carry-trade proxy. Long high-yield AUD against low-yield JPY is a risk-on expression, so it tracks global equities.

**Breaks when.** BoJ normalisation removing the yield differential the carry depends on.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1254 days, 2021-09-13 → 2026-09-11 |
| Return correlation | -0.029 |
| Rolling 60d corr (now / min / max) | -0.24 / -0.42 / +0.45 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.2467 |
| ADF p-value on spread | 0.0907 |
| Hedge ratio β (log-log) | +0.2802 |
| R² | 0.516 |
| Spread SD | 579 bps |
| Half-life | 62.6 days |
| Current z | +0.40 |
| Max historical \|z\| | 2.79 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread



## Intermarket & Index

#### `spx_ndx` — ^GSPC vs ^NDX

**Mechanism.** Overlapping top-weight constituents — Apple, Microsoft, Nvidia, Amazon — appear in both. NOT an identity: the Nasdaq is far more concentrated.

**Breaks when.** Rotation between growth and value, which widens the spread for quarters at a time.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.952 |
| Rolling 60d corr (now / min / max) | +0.89 / +0.86 / +0.99 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.0518 |
| ADF p-value on spread | 0.1032 |
| Hedge ratio β (log-log) | +0.7466 |
| R² | 0.986 |
| Spread SD | 255 bps |
| Half-life | 73.2 days |
| Current z | +0.70 |
| Max historical \|z\| | 2.84 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `spx_vix` — ^GSPC vs ^VIX

**Mechanism.** Near-mechanical rather than statistical: VIX is computed FROM S&P option prices, so the inverse relationship is close to definitional.

**Breaks when.** Rarely. Vol-of-vol events can briefly decouple level from change.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | -0.753 |
| Rolling 60d corr (now / min / max) | -0.80 / -0.95 / -0.54 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.9866 |
| ADF p-value on spread | 0.9530 |
| Hedge ratio β (log-log) | -0.2980 |
| R² | 0.125 |
| Spread SD | 1994 bps |
| Half-life | 320.7 days |
| Current z | +1.74 |
| Max historical \|z\| | 2.03 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `spx_rut` — ^GSPC vs ^RUT

**Mechanism.** Large cap against small cap; the ratio tracks credit conditions and domestic growth.

**Breaks when.** Credit tightening, which hits small caps disproportionately and persistently.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.852 |
| Rolling 60d corr (now / min / max) | +0.77 / +0.47 / +0.96 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.1934 |
| ADF p-value on spread | 0.0770 |
| Hedge ratio β (log-log) | +1.2767 |
| R² | 0.811 |
| Spread SD | 926 bps |
| Half-life | 80.6 days |
| Current z | -0.07 |
| Max historical \|z\| | 2.95 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `dax_stoxx` — ^GDAXI vs ^STOXX50E

**Mechanism.** German large caps are a large weight in the Euro Stoxx 50, so the two overlap heavily.

**Breaks when.** German-specific industrial shocks — energy costs, auto-sector disruption.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1257 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.953 |
| Rolling 60d corr (now / min / max) | +0.88 / +0.81 / +0.99 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.7055 |
| ADF p-value on spread | 0.3821 |
| Hedge ratio β (log-log) | +1.2872 |
| R² | 0.955 |
| Spread SD | 469 bps |
| Half-life | 127.1 days |
| Current z | -0.92 |
| Max historical \|z\| | 2.71 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `ftse_gbpusd` — ^FTSE vs GBPUSD=X

**Mechanism.** Roughly 70% of FTSE 100 revenue is earned abroad, mostly in USD. A weaker pound mechanically inflates reported earnings, so the index rises.

**Breaks when.** Domestic UK shocks hitting both together, which inverts the usual sign.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1262 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.014 |
| Rolling 60d corr (now / min / max) | +0.01 / -0.28 / +0.37 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.4717 |
| ADF p-value on spread | 0.1851 |
| Hedge ratio β (log-log) | +1.4990 |
| R² | 0.322 |
| Spread SD | 1030 bps |
| Half-life | 94.1 days |
| Current z | +1.73 |
| Max historical \|z\| | 2.69 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `spx_dax` — ^GSPC vs ^GDAXI

**Mechanism.** US markets lead European opens; a transatlantic lead-lag rather than a contemporaneous link.

**Breaks when.** Divergent monetary cycles. Note the sessions barely overlap, so daily closes compare prices struck hours apart — same alignment problem as ADRs.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1238 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.458 |
| Rolling 60d corr (now / min / max) | +0.50 / -0.27 / +0.72 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.4954 |
| ADF p-value on spread | 0.1539 |
| Hedge ratio β (log-log) | +0.9341 |
| R² | 0.930 |
| Spread SD | 566 bps |
| Half-life | 39.0 days |
| Current z | +1.33 |
| Max historical \|z\| | 2.67 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `asx_em` — ^AXJO vs EEM

**Mechanism.** Australia's mining and banking weight makes the ASX behave like an EM proxy.

**Breaks when.** China-specific slowdowns hitting EM harder than Australian banks.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1228 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.185 |
| Rolling 60d corr (now / min / max) | +0.02 / -0.30 / +0.56 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.4762 |
| ADF p-value on spread | 0.1645 |
| Hedge ratio β (log-log) | +0.3994 |
| R² | 0.719 |
| Spread SD | 484 bps |
| Half-life | 41.0 days |
| Current z | -1.36 |
| Max historical \|z\| | 2.56 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `gold_silver` — GC=F vs SI=F

**Mechanism.** The gold-silver ratio. Same monetary driver, but silver carries heavy industrial demand and roughly double the volatility.

**Breaks when.** Industrial demand shocks moving silver independently of monetary factors.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1257 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.774 |
| Rolling 60d corr (now / min / max) | +0.87 / +0.45 / +0.90 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.2401 |
| ADF p-value on spread | 0.1130 |
| Hedge ratio β (log-log) | +0.7845 |
| R² | 0.933 |
| Spread SD | 887 bps |
| Half-life | 59.6 days |
| Current z | -0.20 |
| Max historical \|z\| | 3.60 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `copper_spx` — HG=F vs ^GSPC

**Mechanism.** "Dr Copper" as a global industrial demand indicator.

**Breaks when.** Treat with suspicion. The relationship is much weaker than its reputation, and equity indices are now dominated by companies with little industrial copper exposure.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.251 |
| Rolling 60d corr (now / min / max) | +0.46 / -0.25 / +0.73 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.0973 |
| ADF p-value on spread | 0.0370 |
| Hedge ratio β (log-log) | +0.6610 |
| R² | 0.696 |
| Spread SD | 932 bps |
| Half-life | 40.2 days |
| Current z | +1.27 |
| Max historical \|z\| | 2.40 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `wti_brent` — CL=F vs BZ=F

**Mechanism.** Two benchmarks for the same commodity. The spread reflects transport economics and US shale logistics — the tightest genuine spread on this list.

**Breaks when.** Pipeline bottlenecks, US export policy changes, regional supply shocks.

**Access.** `none` — at least one leg unreachable from an Indian retail account

| measure | value |
|---|---|
| Sample | 1257 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.945 |
| Rolling 60d corr (now / min / max) | +0.98 / +0.86 / +0.99 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.0111 |
| ADF p-value on spread | 0.0020 |
| Hedge ratio β (log-log) | +1.0175 |
| R² | 0.985 |
| Spread SD | 195 bps |
| Half-life | 7.0 days |
| Current z | +0.21 |
| Max historical \|z\| | 5.55 |

**Verdict.** COINTEGRATED but slow — 7d half-life



## US Equity Pairs

#### `cvx_xom` — CVX vs XOM

**Mechanism.** Integrated oil majors sharing crude exposure, refining margins and capital cycles.

**Breaks when.** Divergent capex strategy, or a large acquisition by either.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.846 |
| Rolling 60d corr (now / min / max) | +0.82 / +0.52 / +0.95 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.1504 |
| ADF p-value on spread | 0.0581 |
| Hedge ratio β (log-log) | +0.5923 |
| R² | 0.855 |
| Spread SD | 632 bps |
| Half-life | 65.1 days |
| Current z | +1.75 |
| Max historical \|z\| | 3.06 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `ko_pep` — KO vs PEP

**Mechanism.** The textbook consumer-staples pair; shared demand drivers and input costs.

**Breaks when.** PepsiCo's snack business diverging from pure beverages — a slow, persistent drift.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.678 |
| Rolling 60d corr (now / min / max) | +0.68 / +0.26 / +0.93 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.8586 |
| ADF p-value on spread | 0.5528 |
| Hedge ratio β (log-log) | -0.4206 |
| R² | 0.041 |
| Spread SD | 1463 bps |
| Half-life | 170.6 days |
| Current z | +2.33 |
| Max historical \|z\| | 2.75 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `v_ma` — V vs MA

**Mechanism.** A duopoly on the same payment rails, tracking identical transaction volumes.

**Breaks when.** Regulatory action against one, or divergent exposure to a single large market.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.882 |
| Rolling 60d corr (now / min / max) | +0.89 / +0.60 / +0.97 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.0792 |
| ADF p-value on spread | 0.0080 |
| Hedge ratio β (log-log) | +1.0178 |
| R² | 0.973 |
| Spread SD | 354 bps |
| Half-life | 33.0 days |
| Current z | +1.78 |
| Max historical \|z\| | 2.99 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `hd_low` — HD vs LOW

**Mechanism.** Home-improvement retail, both tied to US housing, mortgage rates and renovation cycles.

**Breaks when.** Divergent margin execution — this pair has drifted for extended periods on operations alone.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.881 |
| Rolling 60d corr (now / min / max) | +0.89 / +0.64 / +0.97 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.1861 |
| ADF p-value on spread | 0.0517 |
| Hedge ratio β (log-log) | +1.0141 |
| R² | 0.856 |
| Spread SD | 504 bps |
| Half-life | 54.4 days |
| Current z | +0.99 |
| Max historical \|z\| | 2.32 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `f_gm` — F vs GM

**Mechanism.** Legacy US automakers sharing labour costs, steel inputs and cyclical demand.

**Breaks when.** Divergent EV transition outcomes, or a strike hitting one.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.736 |
| Rolling 60d corr (now / min / max) | +0.64 / +0.47 / +0.95 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.0533 |
| ADF p-value on spread | 0.0198 |
| Hedge ratio β (log-log) | +0.3488 |
| R² | 0.448 |
| Spread SD | 1191 bps |
| Half-life | 48.2 days |
| Current z | +0.33 |
| Max historical \|z\| | 3.83 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `jpm_bac` — JPM vs BAC

**Mechanism.** Money-centre banks driven by the same yield curve and net interest margin dynamics.

**Breaks when.** Credit events, or divergent trading-revenue exposure.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.804 |
| Rolling 60d corr (now / min / max) | +0.85 / +0.57 / +0.96 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.6835 |
| ADF p-value on spread | 0.5554 |
| Hedge ratio β (log-log) | +1.3700 |
| R² | 0.753 |
| Spread SD | 1918 bps |
| Half-life | 223.3 days |
| Current z | -0.15 |
| Max historical \|z\| | 2.51 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `wmt_tgt` — WMT vs TGT

**Mechanism.** Big-box retail sharing consumer data and supply chains.

**Breaks when.** Demographic divergence. Target skews higher-income and discretionary, Walmart defensive — so they separate sharply in a consumer downturn.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.341 |
| Rolling 60d corr (now / min / max) | +0.33 / -0.12 / +0.76 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.9168 |
| ADF p-value on spread | 0.7608 |
| Hedge ratio β (log-log) | -0.9117 |
| R² | 0.305 |
| Spread SD | 3216 bps |
| Half-life | 275.7 days |
| Current z | +2.02 |
| Max historical \|z\| | 2.27 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `nvda_amd` — NVDA vs AMD

**Mechanism.** Semiconductor rivals sharing wafer costs and AI capex demand.

**Breaks when.** ALREADY BROKEN. This pair diverged violently through the AI cycle as Nvidia captured a dominant share. Included deliberately as an example of a relationship the profiler should REJECT.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.655 |
| Rolling 60d corr (now / min / max) | +0.40 / +0.24 / +0.94 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.7461 |
| ADF p-value on spread | 0.7045 |
| Hedge ratio β (log-log) | +1.4804 |
| R² | 0.594 |
| Spread SD | 5980 bps |
| Half-life | 326.7 days |
| Current z | -1.19 |
| Max historical \|z\| | 2.11 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `fdx_ups` — FDX vs UPS

**Mechanism.** Logistics duopoly reflecting freight volumes, fuel costs and e-commerce.

**Breaks when.** Contract losses — the Amazon in-housing shift hit UPS far harder than FedEx.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.593 |
| Rolling 60d corr (now / min / max) | +0.48 / +0.12 / +0.95 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.6274 |
| ADF p-value on spread | 0.2747 |
| Hedge ratio β (log-log) | -0.4998 |
| R² | 0.208 |
| Spread SD | 2069 bps |
| Half-life | 91.3 days |
| Current z | +1.81 |
| Max historical \|z\| | 2.74 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `msft_aapl` — MSFT vs AAPL

**Mechanism.** Both mega-cap tech with heavy passive-index flow.

**Breaks when.** The weakest rationale in the catalogue. Enterprise cloud and consumer hardware are different businesses; "linked by institutional flows" is not a mechanism you can defend. Expect the profiler to reject it.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1255 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.531 |
| Rolling 60d corr (now / min / max) | +0.12 / -0.06 / +0.88 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.5362 |
| ADF p-value on spread | 0.3041 |
| Hedge ratio β (log-log) | +0.8285 |
| R² | 0.684 |
| Spread SD | 1350 bps |
| Half-life | 104.1 days |
| Current z | -0.80 |
| Max historical \|z\| | 2.76 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread



## India — Sector Duopolies

#### `hdfc_icici` — HDFCBANK.NS vs ICICIBANK.NS

**Mechanism.** The two large private banks, driven by RBI policy, domestic credit growth and FII flows into Indian financials.

**Breaks when.** The 2023 HDFC-HDFC Bank merger is a structural break inside any window longer than ~2.5 years. Test post-merger data separately.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1241 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.496 |
| Rolling 60d corr (now / min / max) | +0.26 / +0.06 / +0.78 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.5840 |
| ADF p-value on spread | 0.2395 |
| Hedge ratio β (log-log) | +0.3667 |
| R² | 0.580 |
| Spread SD | 768 bps |
| Half-life | 76.2 days |
| Current z | -2.66 |
| Max historical \|z\| | 3.09 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `tcs_infy` — TCS.NS vs INFY.NS

**Mechanism.** IT services majors with near-identical exposure: US and European tech spending, and a USD revenue base against an INR cost base.

**Breaks when.** Divergent large-deal wins, or margin execution gaps.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1241 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.735 |
| Rolling 60d corr (now / min / max) | +0.77 / +0.46 / +0.89 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.4501 |
| ADF p-value on spread | 0.2463 |
| Hedge ratio β (log-log) | +0.9102 |
| R² | 0.662 |
| Spread SD | 878 bps |
| Half-life | 96.2 days |
| Current z | -0.71 |
| Max historical \|z\| | 2.62 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `maruti_mm` — MARUTI.NS vs M&M.NS

**Mechanism.** Passenger-vehicle makers sharing consumer sentiment, auto-loan rates and steel input costs.

**Breaks when.** SUV-versus-small-car mix shifts, which have driven long divergences.

**Note.** SUBSTITUTED. The original suggestion was MARUTI vs TATAMOTORS, but TATAMOTORS.NS no longer exists — the 2025 demerger split it, and the successor TMPV.NS has about 24 sessions of history. That is far too short to cointegrate, and it is a live example of the structural-break risk in your own framework.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1241 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.483 |
| Rolling 60d corr (now / min / max) | +0.45 / -0.01 / +0.83 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.1195 |
| ADF p-value on spread | 0.0372 |
| Hedge ratio β (log-log) | +0.4510 |
| R² | 0.919 |
| Spread SD | 695 bps |
| Half-life | 40.6 days |
| Current z | -0.89 |
| Max historical \|z\| | 2.84 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `reliance_ongc` — RELIANCE.NS vs ONGC.NS

**Mechanism.** Both crude-linked, but from OPPOSITE sides: ONGC is an upstream producer that gains from high crude, Reliance a refiner and retailer whose margins can compress.

**Breaks when.** Expect this to fail cointegration. Reliance is now dominated by telecom and retail, so the energy channel explains a shrinking share of it.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1241 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.350 |
| Rolling 60d corr (now / min / max) | +0.05 / -0.19 / +0.77 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.0218 |
| ADF p-value on spread | 0.0044 |
| Hedge ratio β (log-log) | +0.2706 |
| R² | 0.700 |
| Spread SD | 615 bps |
| Half-life | 31.3 days |
| Current z | -1.22 |
| Max historical \|z\| | 2.64 |

**Verdict.** COINTEGRATED but slow — 31d half-life


#### `apollo_fortis` — APOLLOHOSP.NS vs FORTIS.NS

**Mechanism.** Hospital chains tracking urban healthcare spend, occupancy and diagnostics demand.

**Breaks when.** Ownership changes at Fortis, or divergent expansion cycles.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1240 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.286 |
| Rolling 60d corr (now / min / max) | +0.42 / -0.10 / +0.76 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.3147 |
| ADF p-value on spread | 0.0117 |
| Hedge ratio β (log-log) | +0.4653 |
| R² | 0.917 |
| Spread SD | 705 bps |
| Half-life | 28.2 days |
| Current z | +1.68 |
| Max historical \|z\| | 2.92 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread



## India — Supply Chain & Cost-Push

#### `maruti_motherson` — MARUTI.NS vs MOTHERSON.NS

**Mechanism.** OEM against component supplier; order books follow vehicle volumes with a lag.

**Breaks when.** Motherson's large international acquisitions have progressively decoupled it from Indian OEM volumes.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1241 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.359 |
| Rolling 60d corr (now / min / max) | +0.28 / -0.07 / +0.75 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.7731 |
| ADF p-value on spread | 0.2085 |
| Hedge ratio β (log-log) | +0.5426 |
| R² | 0.690 |
| Spread SD | 1362 bps |
| Half-life | 98.5 days |
| Current z | -1.64 |
| Max historical \|z\| | 2.38 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `ultracemco_dlf` — ULTRACEMCO.NS vs DLF.NS

**Mechanism.** Cement supplier against real-estate developer; construction velocity drives cement volume.

**Breaks when.** A LEAD-LAG, not a contemporaneous link. Construction demand reaches cement volumes with a multi-quarter lag, so a same-day spread may find nothing.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1240 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.485 |
| Rolling 60d corr (now / min / max) | +0.39 / +0.17 / +0.81 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.5728 |
| ADF p-value on spread | 0.1312 |
| Hedge ratio β (log-log) | +0.6626 |
| R² | 0.798 |
| Spread SD | 1137 bps |
| Half-life | 79.3 days |
| Current z | +0.90 |
| Max historical \|z\| | 2.60 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `indigo_bpcl` — INDIGO.NS vs BPCL.NS

**Mechanism.** Cost-push and inverse. ATF is roughly 40% of an airline's cost base, so crude strength that helps oil marketers hurts IndiGo's margins.

**Breaks when.** Fuel-surcharge pass-through, or OMC marketing margins being administratively capped.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1239 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.382 |
| Rolling 60d corr (now / min / max) | +0.55 / -0.02 / +0.78 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.0882 |
| ADF p-value on spread | 0.0068 |
| Hedge ratio β (log-log) | +1.1536 |
| R² | 0.911 |
| Spread SD | 1287 bps |
| Half-life | 39.0 days |
| Current z | +0.33 |
| Max historical \|z\| | 3.13 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `asianpaint_crude` — ASIANPAINT.NS vs CL=F

**Mechanism.** Decorative paints use crude derivatives — monomers and solvents — as key inputs, so crude spikes compress gross margin.

**Breaks when.** Pricing power letting cost be passed through, which breaks the inverse relation.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1200 days, 2021-09-13 → 2026-09-11 |
| Return correlation | -0.136 |
| Rolling 60d corr (now / min / max) | -0.25 / -0.51 / +0.28 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.1076 |
| ADF p-value on spread | 0.0296 |
| Hedge ratio β (log-log) | +0.1802 |
| R² | 0.059 |
| Spread SD | 1159 bps |
| Half-life | 75.4 days |
| Current z | -1.37 |
| Max historical \|z\| | 2.75 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `hul_godrej` — HINDUNILVR.NS vs GODREJCP.NS

**Mechanism.** FMCG competitors sharing rural demand exposure and palm-oil input costs.

**Breaks when.** Divergent portfolio mix and differing rural-urban revenue splits.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1240 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.463 |
| Rolling 60d corr (now / min / max) | +0.34 / +0.08 / +0.73 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.1496 |
| ADF p-value on spread | 0.0613 |
| Hedge ratio β (log-log) | +0.2190 |
| R² | 0.243 |
| Spread SD | 679 bps |
| Half-life | 51.0 days |
| Current z | -2.20 |
| Max historical \|z\| | 2.38 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread



## India — Corporate House

#### `tatasteel_tatapower` — TATASTEEL.NS vs TATAPOWER.NS

**Mechanism.** Shared group identity and domestic capex exposure.

**Breaks when.** Weak rationale. Steel is a global commodity cyclical, power is a regulated domestic utility. "Same promoter" is a sentiment channel, not an economic one. Expect rejection.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1241 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.511 |
| Rolling 60d corr (now / min / max) | +0.48 / +0.17 / +0.82 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.3795 |
| ADF p-value on spread | 0.0009 |
| Hedge ratio β (log-log) | +0.6989 |
| R² | 0.727 |
| Spread SD | 1318 bps |
| Half-life | 46.2 days |
| Current z | +1.55 |
| Max historical \|z\| | 4.34 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `adanient_adaniports` — ADANIENT.NS vs ADANIPORTS.NS

**Mechanism.** Group flagships sharing debt structure, funding costs and investor perception.

**Breaks when.** The January 2023 short-seller episode is a violent structural break. Any window spanning it will produce a cointegration result that means nothing.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1240 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.773 |
| Rolling 60d corr (now / min / max) | +0.75 / +0.46 / +0.95 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.2401 |
| ADF p-value on spread | 0.1009 |
| Hedge ratio β (log-log) | +0.3132 |
| R² | 0.201 |
| Spread SD | 2096 bps |
| Half-life | 78.6 days |
| Current z | +0.24 |
| Max historical \|z\| | 2.77 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `bajfinance_bajajfinserv` — BAJFINANCE.NS vs BAJAJFINSV.NS

**Mechanism.** The strongest structural rationale among the Indian pairs: Finserv holds the controlling stake in Finance, so part of Finserv's value IS Finance.

**Breaks when.** The 2025 Bajaj Finance split and bonus issue is a mechanical break in the price series — check the data is adjusted before trusting any fit.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1241 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.789 |
| Rolling 60d corr (now / min / max) | +0.68 / +0.56 / +0.92 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.5421 |
| ADF p-value on spread | 0.2202 |
| Hedge ratio β (log-log) | +1.1346 |
| R² | 0.783 |
| Spread SD | 826 bps |
| Half-life | 78.2 days |
| Current z | +2.04 |
| Max historical \|z\| | 2.76 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread



## India — Index & Macro

#### `nifty_banknifty` — ^NSEI vs ^NSEBANK

**Mechanism.** Financials are over 30% of the Nifty 50, so a large part of Bank Nifty is literally inside the Nifty. Close to mechanical.

**Breaks when.** Sector rotation out of financials — real, but historically mean-reverting.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1236 days, 2021-09-13 → 2026-09-11 |
| Return correlation | +0.873 |
| Rolling 60d corr (now / min / max) | +0.82 / +0.70 / +0.96 |
| Relationship stability | stable |
| Engle-Granger p-value | 0.7211 |
| ADF p-value on spread | 0.3748 |
| Hedge ratio β (log-log) | +0.9186 |
| R² | 0.929 |
| Spread SD | 420 bps |
| Half-life | 120.5 days |
| Current z | -1.64 |
| Max historical \|z\| | 2.30 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `niftyit_usdinr` — ^CNXIT vs USDINR=X

**Mechanism.** IT services earn in USD and spend in INR, so rupee depreciation is a direct earnings tailwind. One of the cleanest macro links in Indian equities.

**Breaks when.** Demand shocks in US tech spending overwhelming the currency tailwind.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1233 days, 2021-09-13 → 2026-09-11 |
| Return correlation | -0.101 |
| Rolling 60d corr (now / min / max) | +0.01 / -0.43 / +0.17 |
| Relationship stability | variable |
| Engle-Granger p-value | 0.7041 |
| ADF p-value on spread | 0.4006 |
| Hedge ratio β (log-log) | -0.0516 |
| R² | 0.001 |
| Spread SD | 1353 bps |
| Half-life | 141.2 days |
| Current z | -1.07 |
| Max historical \|z\| | 2.31 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread


#### `niftyfmcg_niftymetal` — ^CNXFMCG vs ^CNXMETAL

**Mechanism.** Defensive against cyclical. The ratio is an economic-cycle expression rather than a mean-reverting spread.

**Breaks when.** Expect rejection as a PAIR. These are not cointegrated in any useful sense; the ratio trends with the cycle rather than reverting to a mean.

**Access.** `long_only` — buyable, but the short leg needs F&O or intraday

| measure | value |
|---|---|
| Sample | 1191 days, 2021-09-13 → 2026-07-17 |
| Return correlation | +0.339 |
| Rolling 60d corr (now / min / max) | +0.15 / -0.11 / +0.77 |
| Relationship stability | unstable |
| Engle-Granger p-value | 0.9279 |
| ADF p-value on spread | 0.7755 |
| Hedge ratio β (log-log) | +0.3866 |
| R² | 0.463 |
| Spread SD | 1134 bps |
| Half-life | 320.0 days |
| Current z | -1.73 |
| Max historical \|z\| | 2.58 |

**Verdict.** NOT COINTEGRATED — correlation only, no tradeable spread

