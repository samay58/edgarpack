"""Positional arithmetic-formula evaluation shared by the SEC and S-1 query paths.

Dependency-free on purpose: both financials.py and s1_financials.py import this,
so it must not import either (keeps the import graph acyclic).
"""

from __future__ import annotations


def eval_formula(formula: str, values: dict[str, float]) -> float | None:
    """Evaluate a positional, left-associative arithmetic formula.

    Supported shapes:

    - ``a op b`` (3 tokens): single binary operation.
    - ``a op1 b op2 c`` (5 tokens): left-associative; ``op1`` is applied first,
      then ``op2`` is applied to that result and ``c``.

    Operands may be names present in ``values`` or numeric literals (e.g.
    ``revenue - 1`` for a YoY growth shape). Division by zero yields ``None``.
    Any other token count, or a missing/non-numeric operand, yields ``None``.

    This is positional, not precedence aware: write ``a / b - c`` for
    ``(a / b) - c``, and decompose ``b + c`` into a named component for
    ``a * (b + c)``.
    """

    def _lookup(token: str) -> float | None:
        try:
            return float(token)
        except ValueError:
            return values.get(token)

    parts = formula.split()
    if len(parts) == 3:
        left_name, op, right_name = parts
        left = _lookup(left_name)
        right = _lookup(right_name)
        if left is None or right is None:
            return None
        if op == "+":
            return left + right
        elif op == "-":
            return left - right
        elif op == "*":
            return left * right
        elif op == "/":
            if right == 0:
                return None
            return left / right
    elif len(parts) == 5:
        a_name, op1, b_name, op2, c_name = parts
        a = _lookup(a_name)
        b = _lookup(b_name)
        c = _lookup(c_name)
        if a is None or b is None or c is None:
            return None
        # Respect precedence for /: (a / b) first, then +/- c.
        if op1 == "/":
            if b == 0:
                return None
            result = a / b
        elif op1 == "*":
            result = a * b
        elif op1 == "+":
            result = a + b
        else:
            result = a - b
        if op2 == "+":
            result = result + c
        elif op2 == "-":
            result = result - c
        elif op2 == "*":
            result = result * c
        elif op2 == "/":
            if c == 0:
                return None
            result = result / c
        return result

    return None
