"""Universe config loading -- every failure must happen at startup, not at 09:15."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from linkage.config import Universe, load_universe

VALID = """
linkages:
  - id: mcx_gold
    description: MCX gold against XAUUSD in INR
    legs:
      mcx:  { symbol: "MCX:GOLD1!",     provider: tradingview }
      spot: { symbol: "OANDA:XAUUSD",   provider: tradingview }
      fx:   { symbol: "FX_IDC:USDINR",  provider: tradingview }
    fair_value: "spot * fx / 31.1035 * 10 * (1 + import_duty) * (1 + gst)"
    params: { import_duty: 0.06, gst: 0.03 }
    reference: mcx
    friction_bps: { fx_spread: 25, brokerage: 3 }
    alert:
      warn_z: 1.8
      alert_z: 2.5
      min_net_edge_bps: 15
      cooldown_minutes: 60
"""


def _load(text: str) -> Universe:
    return Universe.model_validate(yaml.safe_load(text))


def test_valid_universe_loads(tmp_path):
    path = tmp_path / "universe.yaml"
    path.write_text(VALID, encoding="utf-8")

    universe = load_universe(path)
    gold = universe.by_id("mcx_gold")

    assert gold.reference == "mcx"
    assert gold.total_friction_bps == 28
    assert universe.providers_used() == {"tradingview"}


def test_formula_typo_fails_at_load():
    """The rule that earns its keep.

    `usdinr` is not a declared leg -- the leg is called `fx`. Without this
    check the formula resolves to nothing at evaluation time: once, quietly,
    for one pair, and the alert simply never fires. Nobody notices a signal
    that does not arrive.
    """
    broken = VALID.replace("spot * fx /", "spot * usdinr /")
    with pytest.raises(ValidationError, match="undeclared name.*usdinr"):
        _load(broken)


def test_reference_must_be_a_leg():
    broken = VALID.replace("reference: mcx", "reference: mcxx")
    with pytest.raises(ValidationError, match="not one of the legs"):
        _load(broken)


def test_alert_threshold_must_exceed_warn():
    """Otherwise WATCHING is unreachable and the state machine is a lie."""
    broken = VALID.replace("alert_z: 2.5", "alert_z: 1.5")
    with pytest.raises(ValidationError, match="must exceed warn_z"):
        _load(broken)


def test_a_linkage_needs_two_legs():
    broken = """
linkages:
  - id: lonely
    description: nothing to relate to
    legs:
      only: { symbol: "NSE:INFY", provider: tradingview }
    fair_value: "only"
    reference: only
    alert: { warn_z: 1.8, alert_z: 2.5, min_net_edge_bps: 15, cooldown_minutes: 60 }
"""
    with pytest.raises(ValidationError, match="at least two legs"):
        _load(broken)


def test_duplicate_linkage_ids_are_refused():
    doubled = VALID + VALID.split("linkages:")[1]
    with pytest.raises(ValidationError, match="duplicate linkage id"):
        _load(doubled)


def test_symbols_are_deduplicated_across_linkages():
    """USDINR appears in nearly every linkage.

    Quoting it once per cycle instead of once per linkage is most of the
    difference between a scan that fits inside the cadence floor and one that
    does not.
    """
    two = VALID + """
  - id: mcx_silver
    description: MCX silver against XAGUSD in INR
    legs:
      mcx:  { symbol: "MCX:SILVER1!",   provider: tradingview }
      spot: { symbol: "OANDA:XAGUSD",   provider: tradingview }
      fx:   { symbol: "FX_IDC:USDINR",  provider: tradingview }
    fair_value: "spot * fx / 31.1035 * 30"
    reference: mcx
    alert: { warn_z: 1.8, alert_z: 2.5, min_net_edge_bps: 15, cooldown_minutes: 60 }
"""
    universe = _load(two)
    symbols = universe.symbols_for("tradingview")

    assert len(symbols) == 5  # 6 legs, but USDINR is shared
    assert "FX_IDC:USDINR" in symbols
