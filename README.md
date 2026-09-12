# Linkage Monitor

Cross-market relationship scanner for INR-denominated instruments.

Watches instruments whose prices are linked by a **computable** relationship —
an ADR against its local listing via USDINR, MCX gold against XAUUSD with import
duty and GST — detects when that relationship breaks beyond its own historical
tolerance, prices the friction needed to actually capture the gap, and alerts
only on what survives that accounting.

It is not an arbitrage finder. The premise is the opposite: *most gaps are fully
explained by FX, duty, taxes and settlement lag, and the useful output is the
arithmetic that shows why.*

## Status

Early. Built so far:

- `linkage/providers/base.py` — the provider boundary. Each provider declares its
  own `cadence_floor_seconds` rather than trusting a configured poll rate.
- `linkage/formula.py` — safe arithmetic evaluator for fair-value expressions.
  No `eval()`; the AST is walked against a whitelist.
- `linkage/config.py` — declarative universe config, validated at load time.
- `linkage/providers/fake.py` — deterministic provider for tests.

Next: store schema, spread/z-score engine, friction ledger, signal state machine.

## Design notes

**Cadence is matched to horizon, not to ambition.** The forecast horizon is
48–72 hours. Second-by-second polling would collect ~250,000 observations per
horizon; minute bars carry the same information without the noise.

**Breadth × frequency × validity — pick two.** 100 instruments is 4,950 pairs;
at z > 2.5 roughly 61 breach by chance every cycle. The universe is deliberately
curated, each pair present for a stated economic reason.

## Running the tests

```
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m pytest
```
