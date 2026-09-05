"""Stub adapters — one per named external system (FR-INT-01..04).

There is nothing real to integrate with yet, and the SRS gives only a
one-line functional description per system, not a request/response contract
— so each adapter here logs a well-formed request/response pair and returns
clearly-marked fake data, rather than guessing at real field names (CLAUDE.md
rule 5). See TODO.md TD-005 for what unblocks a real implementation.
"""

ADAPTERS: dict[str, str] = {
    "CAD": "Computer-Aided Dispatch — FR-INT-01 (incident and unit-status sync)",
    "NCDB": "National/regional Crime Database — FR-INT-02 (identity verification, "
    "cross-jurisdictional case checks)",
    "COURTS": "Court system — FR-INT-03 (case scheduling, evidence submission "
    "metadata, verdict retrieval)",
    "JAIL": "Jail / detention management system — FR-INT-04 (continuity-of-custody)",
}


def fake_response(system_name: str, correlation_id: str, request_body: dict) -> dict:
    return {
        "mock": True,
        "system_name": system_name,
        "correlation_id": correlation_id,
        "message": f"No real {system_name} integration exists yet ({ADAPTERS[system_name]}) "
        "— this is a stub response only. See TODO.md TD-005.",
        "request_echo": request_body,
    }
