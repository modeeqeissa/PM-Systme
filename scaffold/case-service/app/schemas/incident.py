import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class IncidentCreate(BaseModel):
    """Request body for POST /incidents — matches openapi.yaml IncidentCreate."""

    reported_by: uuid.UUID
    incident_type: str
    description: str
    latitude: float | None = None
    longitude: float | None = None
    station_id: uuid.UUID
    reported_at: dt.datetime


class IncidentOut(IncidentCreate):
    """Response body — matches openapi.yaml Incident (IncidentCreate + id, created_at)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: dt.datetime
