"""Case lifecycle state machine (FR-CASE-03).

The status column is constrained to these five values by ck_cases_status in
migration 0001; this map defines which moves between them are legal. Anything
not listed is a 409 on PATCH /cases/{case_id}/status.
"""
from app.schemas.case import CaseStatus

# current status -> set of statuses it may move to
VALID_TRANSITIONS: dict[str, set[str]] = {
    CaseStatus.open.value: {
        CaseStatus.investigating.value,
        CaseStatus.suspended.value,
        CaseStatus.closed.value,
    },
    CaseStatus.investigating.value: {
        CaseStatus.referred_prosecution.value,
        CaseStatus.suspended.value,
        CaseStatus.closed.value,
    },
    CaseStatus.referred_prosecution.value: {
        CaseStatus.investigating.value,
        CaseStatus.closed.value,
    },
    CaseStatus.suspended.value: {
        CaseStatus.open.value,
        CaseStatus.investigating.value,
        CaseStatus.closed.value,
    },
    # closed is terminal
    CaseStatus.closed.value: set(),
}


def can_transition(current: str, target: str) -> bool:
    """True when moving a case from ``current`` to ``target`` is allowed.

    A no-op (current == target) is not a transition and returns False.
    """
    return target in VALID_TRANSITIONS.get(current, set())
