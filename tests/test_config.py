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


def test_validation_linkages_declare_a_tight_kalman_prior():
    """A triangular identity's beta cannot drift, so its prior must not allow it.

    This is not tidiness. The validation lane exists so that an engine bug
    surfaces where the answer is known in advance, and a permissive prior lets
    beta wander a few percent on its own -- which looks, on the dashboard,
    exactly like the bug it is meant to reveal. Measured on AUDINR, whose true
    ratio is 0.99801: the general prior of 1e-7 lands at 0.9603 (3.97% drift),
    a tight 1e-10 lands at 0.9979 (0.21%).
    """
    from pathlib import Path

    from linkage.config import Category, load_universe

    universe = load_universe(Path(__file__).resolve().parent.parent / "config" / "universe.yaml")
    validation = [k for k in universe.linkages if k.category is Category.VALIDATION]
    assert validation, "the universe lost its validation lane"

    for linkage in validation:
        assert linkage.kalman_delta is not None, (
            f"{linkage.id} is a mathematical identity but inherits the general "
            f"drift prior, so its beta is free to wander"
        )
        assert linkage.kalman_delta <= 1e-9, f"{linkage.id}'s prior is too loose for an identity"


def test_non_validation_linkages_keep_the_general_prior():
    """The converse. An ADR ratio moves on corporate actions and an index
    tracker's units drift with rebalancing, so pinning those would tell the
    filter it knows something it does not."""
    from pathlib import Path

    from linkage.config import Category, load_universe

    universe = load_universe(Path(__file__).resolve().parent.parent / "config" / "universe.yaml")
    for linkage in universe.linkages:
        if linkage.category is not Category.VALIDATION:
            assert linkage.kalman_delta is None, (
                f"{linkage.id} pins its hedge ratio, but only an identity may"
            )


def test_the_prior_reaches_the_detector():
    """The factory exists because the override used to be ignored.

    delta was defined twice -- as the default in kalman.py and again as a
    hardcoded 1e-5 on LinkageDetector -- so correcting the default changed
    nothing on the live path. The bug survived its own fix.
    """
    from pathlib import Path

    from linkage.config import Category, load_universe
    from linkage.detector import LinkageDetector

    universe = load_universe(Path(__file__).resolve().parent.parent / "config" / "universe.yaml")
    for linkage in universe.linkages:
        detector = LinkageDetector.for_linkage(linkage)
        if linkage.kalman_delta is not None:
            assert detector.kalman.delta == linkage.kalman_delta, (
                f"{linkage.id} declares a prior the detector did not pick up"
            )
