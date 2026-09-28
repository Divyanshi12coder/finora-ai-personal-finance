"""Date helpers used across analytics, budgets and forecasting.

Centralised because "what is this month" and "what is the previous comparable
period" appear in a dozen places, and an off-by-one there quietly corrupts every
percentage the product shows.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

RANGE_PRESETS: dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
}


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> DateRange:
        """The immediately preceding window of identical length."""
        length = self.days
        new_end = self.start - timedelta(days=1)
        return DateRange(start=new_end - timedelta(days=length - 1), end=new_end)

    def contains(self, value: date) -> bool:
        return self.start <= value <= self.end

    def as_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


def month_start(value: date) -> date:
    return value.replace(day=1)


def month_end(value: date) -> date:
    last_day = calendar.monthrange(value.year, value.month)[1]
    return value.replace(day=last_day)


def month_range(value: date) -> DateRange:
    return DateRange(start=month_start(value), end=month_end(value))


def add_months(value: date, months: int) -> date:
    """Shift by whole months, clamping the day to the target month's length."""
    total = value.month - 1 + months
    year = value.year + total // 12
    month = total % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def previous_month_start(value: date) -> date:
    return month_start(add_months(month_start(value), -1))


def month_label(value: date) -> str:
    return value.strftime("%b %Y")


def month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def parse_month_key(value: str) -> date:
    """Parse ``"2026-09"`` (or a full ISO date) into the first of that month."""
    value = value.strip()
    if len(value) == 7:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    return month_start(date.fromisoformat(value))


def resolve_range(
    preset: str | None = None,
    start: date | None = None,
    end: date | None = None,
    today: date | None = None,
) -> DateRange:
    """Turn a preset name (or explicit bounds) into a concrete DateRange.

    Explicit ``start``/``end`` always win over the preset. Unknown presets fall
    back to 30 days rather than raising, so a stale bookmark cannot break a page.
    """
    today = today or date.today()

    if start and end:
        if start > end:
            start, end = end, start
        return DateRange(start=start, end=end)
    if start and not end:
        return DateRange(start=start, end=today)
    if end and not start:
        return DateRange(start=end - timedelta(days=29), end=end)

    if preset == "mtd":
        return DateRange(start=month_start(today), end=today)
    if preset == "all":
        return DateRange(start=date(today.year - 5, today.month, 1), end=today)

    days = RANGE_PRESETS.get(preset or "30d", 30)
    return DateRange(start=today - timedelta(days=days - 1), end=today)


def iter_months(start: date, end: date):
    """Yield the first day of every month between ``start`` and ``end``."""
    cursor = month_start(start)
    limit = month_start(end)
    while cursor <= limit:
        yield cursor
        cursor = add_months(cursor, 1)


def days_remaining_in_month(value: date) -> int:
    return (month_end(value) - value).days
