"""Certification expiry math (FR-TRAIN-02/03).

``expires_date`` is always derived server-side from the course's
``validity_months`` rather than accepted as client input, so it can never
drift out of sync with the course's declared validity period. ``status`` is
likewise derived from today's date against ``expires_date`` — computed once at
issue time and recomputed by ``recompute_status`` (on-demand endpoint and
periodic sweep) as time passes.
"""
import calendar
import datetime as dt


def add_months(start: dt.date, months: int) -> dt.date:
    """``start`` plus ``months`` calendar months, clamped to the target month's
    last day (e.g. Jan 31 + 1 month -> Feb 28/29, never Mar 3)."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def compute_expires_date(issued_date: dt.date, validity_months: int) -> dt.date:
    return add_months(issued_date, validity_months)


def compute_status(expires_date: dt.date, *, today: dt.date, lead_days: int) -> str:
    if expires_date <= today:
        return "expired"
    if (expires_date - today).days <= lead_days:
        return "expiring_soon"
    return "active"
