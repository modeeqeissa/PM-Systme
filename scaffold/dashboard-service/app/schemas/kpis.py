import datetime as dt
import uuid

from pydantic import BaseModel


class CaseKpis(BaseModel):
    opened: int
    closed: int
    arrests_recorded: int
    avg_case_age_days: float | None = None


class CrimeTrendBucket(BaseModel):
    month: dt.date
    incident_type: str | None = None
    count: int


class EvidenceIntegrityKpis(BaseModel):
    evidence_logged: int
    pending_transfer_ack: int
    hash_mismatches: int


class UnitReadiness(BaseModel):
    unit_id: uuid.UUID
    station_id: uuid.UUID
    unit_name: str | None = None
    total_officers: int
    certified_officer_pct: float | None = None
    on_leave_count: int


class KpiSnapshot(BaseModel):
    station_id: uuid.UUID | None = None
    as_of: dt.datetime
    cases: CaseKpis
    crime_trends: list[CrimeTrendBucket]
    evidence_integrity: EvidenceIntegrityKpis
    unit_readiness: list[UnitReadiness]
