"""Follow-up action overdue detection (FR-COMM-04).

A pending action becomes overdue once its due_date has passed. This is a pure
function of today's date, so — like training-service's certification expiry
status — it is recomputed rather than accepted as client input.
"""
import datetime as dt


def is_overdue(due_date: dt.date, *, today: dt.date) -> bool:
    return due_date < today
