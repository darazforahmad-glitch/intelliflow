"""Safe expressions and templates for workflow definitions.

Conditions such as `details.amount > 10000` are parsed with Python's `ast` module and
evaluated by a whitelist interpreter: no calls, no subscripts, no dunder access, no
`eval`. Customer text therefore can never become code (SEC-9).
Templates use `{{path.to.value}}` placeholders resolved from the run context.
"""

from __future__ import annotations

import ast
import json
import re
from decimal import Decimal
from functools import lru_cache
from typing import Any

MAX_EXPRESSION_LENGTH = 300
_TEMPLATE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*\}\}")
_SINGLE_PLACEHOLDER = re.compile(
    r"^\s*\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*\}\}\s*$"
)
_ALIASES = {"true": True, "false": False, "null": None, "none": None}
_ALLOWED = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Constant,
    ast.List,
    ast.Tuple,
)


class ExpressionError(ValueError):
    pass


@lru_cache(maxsize=512)
def parse_expression(expression: str) -> ast.Expression:
    if not expression or len(expression) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError("Conditions must be between 1 and 300 characters.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"The condition “{expression}” is not written correctly.") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ExpressionError(
                f"The condition “{expression}” uses something that is not allowed ({type(node).__name__})."
            )
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ExpressionError("Conditions cannot use names that start with an underscore.")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ExpressionError("Conditions cannot use names that start with an underscore.")
    return tree


def expression_references(expression: str) -> set[str]:
    """Root names an expression reads, e.g. {'details'} for `details.amount > 5`."""
    tree = parse_expression(expression)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.lower() not in _ALIASES:
            roots.add(node.id)
    return roots


def template_references(text: str) -> set[str]:
    return {match.group(1).split(".")[0] for match in _TEMPLATE.finditer(text)}


def value_references(value: Any) -> set[str]:
    if isinstance(value, str):
        return template_references(value)
    if isinstance(value, dict):
        return set().union(*(value_references(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(value_references(v) for v in value)) if value else set()
    return set()


def resolve_path(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _compare(op: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(op, ast.Eq | ast.NotEq):
        lnum, rnum = _to_number(left), _to_number(right)
        equal = (
            lnum == rnum
            if lnum is not None and rnum is not None
            else (
                str(left).strip().lower() == str(right).strip().lower()
                if isinstance(left, str) and isinstance(right, str)
                else left == right
            )
        )
        return equal if isinstance(op, ast.Eq) else not equal
    if isinstance(op, ast.Is):
        return left is right
    if isinstance(op, ast.IsNot):
        return left is not right
    if isinstance(op, ast.In | ast.NotIn):
        try:
            contained = left in right if right is not None else False
        except TypeError:
            contained = False
        return contained if isinstance(op, ast.In) else not contained
    lnum, rnum = _to_number(left), _to_number(right)
    if lnum is None or rnum is None:
        return False  # comparing with missing/non-numeric data is never true
    if isinstance(op, ast.Gt):
        return lnum > rnum
    if isinstance(op, ast.GtE):
        return lnum >= rnum
    if isinstance(op, ast.Lt):
        return lnum < rnum
    return lnum <= rnum


def _eval(node: ast.AST, context: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, context)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id.lower() in _ALIASES:
            return _ALIASES[node.id.lower()]
        return context.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _eval(node.value, context)
        return base.get(node.attr) if isinstance(base, dict) else None
    if isinstance(node, ast.List | ast.Tuple):
        return [_eval(e, context) for e in node.elts]
    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, context)
        if isinstance(node.op, ast.Not):
            return not operand
        number = _to_number(operand)
        return -number if number is not None else None
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval(v, context) for v in node.values)
        return any(_eval(v, context) for v in node.values)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, context)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval(comparator, context)
            if not _compare(op, left, right):
                return False
            left = right
        return True
    raise ExpressionError(f"Unsupported expression element: {type(node).__name__}")


def evaluate(expression: str, context: dict[str, Any]) -> Any:
    return _eval(parse_expression(expression), context)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def render(text: str, context: dict[str, Any]) -> str:
    return _TEMPLATE.sub(lambda m: _stringify(resolve_path(context, m.group(1))), text)


def render_value(value: Any, context: dict[str, Any]) -> Any:
    """Render templates inside nested params. A lone placeholder keeps the raw type."""
    if isinstance(value, str):
        single = _SINGLE_PLACEHOLDER.match(value)
        if single:
            return resolve_path(context, single.group(1))
        return render(value, context)
    if isinstance(value, dict):
        return {k: render_value(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [render_value(v, context) for v in value]
    return value
