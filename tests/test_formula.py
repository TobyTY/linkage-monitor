"""Formula evaluation, and the things it must refuse."""

from __future__ import annotations

from decimal import Decimal

import pytest

from linkage.formula import FormulaError, evaluate, referenced_names


def test_arithmetic_over_named_legs():
    # MCX gold fair value: spot in USD/oz -> INR per 10g, plus duty and GST.
    result = evaluate(
        "spot * fx / 31.1035 * 10 * (1 + import_duty) * (1 + gst)",
        {
            "spot": Decimal("2340.50"),
            "fx": Decimal("83.71"),
            "import_duty": Decimal("0.06"),
            "gst": Decimal("0.03"),
        },
    )
    assert Decimal("68000") < result < Decimal("70000")


def test_values_stay_exact():
    """Decimal in, Decimal out -- no silent trip through binary float."""
    assert evaluate("a + b", {"a": 0.1, "b": 0.2}) == Decimal("0.3")
    assert 0.1 + 0.2 != 0.3  # the reason the line above matters


def test_unknown_name_is_refused_by_name():
    with pytest.raises(FormulaError, match="unknown name 'usdinr'"):
        evaluate("spot * usdinr", {"spot": Decimal("1")})


def test_division_by_zero_is_a_formula_error():
    """Callers handle one exception type, not three."""
    with pytest.raises(FormulaError, match="arithmetic error"):
        evaluate("a / b", {"a": Decimal("1"), "b": Decimal("0")})


@pytest.mark.parametrize(
    "hostile",
    [
        "__import__('os').system('echo pwned')",
        "().__class__.__bases__[0].__subclasses__()",
        "(lambda: 1)()",
        "spot.__class__",
        "spot['key']",
        "[x for x in (1, 2)]",
        "open('/etc/passwd').read()",
        "spot if spot else 1",
    ],
)
def test_only_arithmetic_survives(hostile):
    """Config is data. Data that reaches eval() is code.

    A universe file gets shared, copied off a forum, edited by someone else.
    Every one of these is a valid Python expression and none of them is a fair
    value, so each is refused at parse-walk time rather than caught after the
    fact.
    """
    with pytest.raises(FormulaError):
        evaluate(hostile, {"spot": Decimal("1")})


def test_comparison_and_boolean_operators_are_refused():
    """Not hostile -- just a misunderstanding of what this field is for."""
    with pytest.raises(FormulaError):
        evaluate("spot > 1", {"spot": Decimal("2")})
    with pytest.raises(FormulaError):
        evaluate("spot and 1", {"spot": Decimal("2")})


def test_booleans_are_not_numbers():
    """bool subclasses int in Python; a price is never True."""
    with pytest.raises(FormulaError, match="booleans"):
        evaluate("a * 2", {"a": True})


def test_referenced_names_finds_every_dependency():
    assert referenced_names("spot * fx / 31.1035 * (1 + duty)") == {
        "spot",
        "fx",
        "duty",
    }
    assert referenced_names("2 + 2") == set()


def test_unparseable_formula_reports_clearly():
    with pytest.raises(FormulaError, match="could not parse"):
        evaluate("spot * * fx", {})
