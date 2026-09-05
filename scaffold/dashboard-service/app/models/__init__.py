"""CQRS read-model tables for dashboard_db (docs Section 9.3.7).

Named ``mv_*`` per the SRS. They are plain tables updated incrementally by the
Kafka consumer (Postgres materialised views cannot refresh per-event), and are
fully rebuildable by replaying the event log.
"""
from app.models.base import Base
from app.models.projections import (
    ConsumedEvent,
    DashCase,
    DashLeave,
    DashOfficer,
    DashOfficerCert,
    DashTransfer,
    DashUnit,
    MvCrimeTrends,
    MvEvidenceIntegrity,
    MvStationCaseKpis,
)

__all__ = [
    "Base",
    "ConsumedEvent",
    "DashCase",
    "DashUnit",
    "DashOfficer",
    "DashTransfer",
    "DashLeave",
    "DashOfficerCert",
    "MvStationCaseKpis",
    "MvCrimeTrends",
    "MvEvidenceIntegrity",
]
