"""Safe evaluation of fair-value formulas from config.

Linkages declare their fair value as an expression over leg names and
parameters:

    fair_value: "spot * fx / 31.1035 * 10 * (1 + import_duty) * (1 + gst)"

The obvious implementation is ``eval()``. It is also the wrong one: config is
data, and data that reaches ``eval()`` is code. A universe file shared, copied
from a forum, or edited by someone else becomes arbitrary execution. Given the
expressions here are pure arithmetic, nothing is lost by refusing everything
else.

So the expression is parsed into an AST and walked against a whitelist. Anything
outside plain arithmetic over declared names -- a function call, an attribute
access, a subscript, a name that was not supplied -- is refused before
evaluation rather than caught during it.
"""

from __future__ import annotations

import ast
import operator
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Mapping

__all__ = ["FormulaError", "evaluate", "referenced_names"]


class FormulaError(ValueError):
    """The expression is not a permitted arithmetic formula, or cannot resolve."""


# Operators we allow. Deliberately no bitwise, no comparison, no boolean ops:
# a fair value is arithmetic, and anything else signals a misunderstanding of
# what this field is for.
_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _to_decimal(value: object, where: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is an int subclass; never a price
        raise FormulaError(f"{where}: booleans are not values in a formula")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # Route through str so 0.1 becomes Decimal("0.1") and not the binary
        # expansion. Prices are exact quantities; float is a transport, never a
        # representation.
        return Decimal(str(value))
    raise FormulaError(f"{where}: expected a number, got {type(value).__name__}")


def _eval_node(node: ast.AST, names: Mapping[str, object]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, names)

    if isinstance(node, ast.Constant):
        return _to_decimal(node.value, "literal")

    if isinstance(node, ast.Name):
        if node.id not in names:
            raise FormulaError(
                f"unknown name {node.id!r} -- declare it as a leg or a param"
            )
        return _to_decimal(names[node.id], f"name {node.id!r}")

    if isinstance(node, ast.BinOp):
        op = _BINARY_OPS.get(type(node.op))
        if op is None:
            raise FormulaError(f"operator {type(node.op).__name__} is not permitted")
        left = _eval_node(node.left, names)
        right = _eval_node(node.right, names)
        try:
            return op(left, right)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as exc:
            raise FormulaError(f"arithmetic error: {exc}") from exc

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise FormulaError(f"unary {type(node.op).__name__} is not permitted")
        return op(_eval_node(node.operand, names))

    # Everything else -- Call, Attribute, Subscript, Lambda, comprehensions,
    # walrus, f-strings -- lands here and is refused by construction.
    raise FormulaError(f"{type(node).__name__} is not permitted in a formula")


def _parse(expression: str) -> ast.Expression:
    try:
        return ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"could not parse formula: {exc}") from exc


def referenced_names(expression: str) -> set[str]:
    """Names the formula depends on.

    Used at config-load time to check a linkage declares every name its formula
    uses, so a typo fails when the file is read rather than when the market is
    open.
    """
    return {
        node.id for node in ast.walk(_parse(expression)) if isinstance(node, ast.Name)
    }


def evaluate(expression: str, names: Mapping[str, object]) -> Decimal:
    """Evaluate an arithmetic formula over ``names``, returning a Decimal."""
    return _eval_node(_parse(expression), names)
