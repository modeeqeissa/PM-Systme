"""Domain event -> audit_logs fields (FR-AUD-01)."""

NIL_UUID = "00000000-0000-0000-0000-000000000000"

# event_type -> (entity_type, action, key in payload holding the entity id)
EVENT_MAP: dict[str, tuple[str, str, str]] = {
    "IncidentReported": ("incident", "create", "incident_id"),
    "CaseOpened": ("case", "create", "case_id"),
    "CaseStatusChanged": ("case", "update", "case_id"),
    "ArrestRecorded": ("arrest", "create", "arrest_id"),
    "EvidenceLogged": ("evidence_item", "create", "evidence_id"),
    "CustodyEventRecorded": ("custody_event", "create", "custody_event_id"),
}


def to_audit_fields(envelope: dict) -> dict | None:
    """Return audit_logs field values for an event envelope, or None to skip it."""
    mapped = EVENT_MAP.get(envelope.get("event_type"))
    if mapped is None:
        return None
    entity_type, action, id_key = mapped
    payload = envelope.get("payload") or {}
    if id_key not in payload:
        return None
    return {
        "actor_id": envelope.get("actor_id") or NIL_UUID,
        "actor_role": envelope.get("actor_role") or "unknown",
        "service_name": envelope.get("service") or "unknown",
        "entity_type": entity_type,
        "entity_id": str(payload[id_key]),
        "action": action,
        "metadata": {
            "event_id": envelope.get("event_id"),
            "event_type": envelope.get("event_type"),
            "occurred_at": envelope.get("occurred_at"),
            "payload": payload,
        },
    }
