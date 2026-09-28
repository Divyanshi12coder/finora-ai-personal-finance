"""Decimal money helpers.

Money is stored and computed as ``Decimal`` end to end - never float. Floats
accumulate representation error, and a budget page that says "99.999% used" is
a bug report waiting to happen.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def to_decimal(value: object, default: Decimal = ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def quantize(value: object) -> Decimal:
    return to_decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def as_float(value: object) -> float:
    """Convert to float at the API boundary only (JSON has no Decimal)."""
    return float(quantize(value))


def safe_divide(numerator: object, denominator: object, default: float = 0.0) -> float:
    den = to_decimal(denominator)
    if den == 0:
        return default
    return float(to_decimal(numerator) / den)


def percentage_change(current: object, previous: object) -> float | None:
    """Percent change from ``previous`` to ``current``.

    Returns ``None`` when the previous value is zero: "infinite % increase" is
    meaningless to show a user, so callers render "new" instead.
    """
    prev = to_decimal(previous)
    if prev == 0:
        return None
    return round(float((to_decimal(current) - prev) / abs(prev) * 100), 2)


def percent_of(part: object, whole: object) -> float:
    total = to_decimal(whole)
    if total == 0:
        return 0.0
    return round(float(to_decimal(part) / total * 100), 2)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))
