"""Custody-chain business rules (FR-EVID-03, FR-EVID-04)."""
import hashlib

from app.models.custody_event import ACK_REQUIRED_ACTIONS

# custody action -> the evidence_items.status it moves the item to (if any)
ACTION_STATUS = {
    "analyzed": "in_analysis",
    "submitted_court": "in_court",
    "disposed": "disposed",
}


def acknowledgement_required(action: str) -> bool:
    return action in ACK_REQUIRED_ACTIONS


def hash_signature(raw: str) -> str:
    """Store the receiving officer's signature/PIN only as a hash (FR-EVID-04)."""
    return hashlib.sha256(raw.encode()).hexdigest()
