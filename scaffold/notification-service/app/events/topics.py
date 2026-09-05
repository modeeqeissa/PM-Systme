"""Topics notification-service consumes (must match the producers' base names).

Kept aligned with hr-service/training-service/community-service/iam-service's
own app/events/topics.py. `hr.officer_created` carries no notification of its
own — it only feeds app.models.OfficerUserMap (see that model's docstring).
"""
from app.config import topic_prefix

_BASE_TOPICS = (
    "hr.officer_created",
    "hr.officer_supervisor_changed",
    "hr.transfer_status_changed",
    "hr.leave_status_changed",
    "training.officer_certification_status_changed",
    "community.follow_up_action_status_changed",
    # FR-IAM-05's notification half (TODO.md TD-003's remaining item)
    "account.locked_out",
)


def consumed_topics() -> list[str]:
    prefix = topic_prefix()
    return [f"{prefix}{t}" for t in _BASE_TOPICS]
