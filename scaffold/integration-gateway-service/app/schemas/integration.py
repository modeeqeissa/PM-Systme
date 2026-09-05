import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict


class LogDirection(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class IntegrationConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    system_name: str
    enabled: bool


class IntegrationConfigUpdate(BaseModel):
    enabled: bool


class ExternalSystemLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    system_name: str
    direction: LogDirection
    correlation_id: uuid.UUID
    response_status: int | None


class AdapterCallResponse(BaseModel):
    mock: bool
    system_name: str
    correlation_id: str
    message: str
    request_echo: dict
