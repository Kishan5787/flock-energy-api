from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class MeterSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meter_id: str = Field(..., description="Stable meter identifier")
    serial_number: str | None = None
    make: str | None = None
    phase_type: str | None = None
    installation_status: str | None = None
    transformer_code: str | None = None


class NetworkLocation(BaseModel):
    zone: str | None = None
    circle: str | None = None
    division: str | None = None
    subdivision: str | None = None
    substation: str | None = None
    feeder: str | None = None
    transformer: str | None = None


class GeoLocation(BaseModel):
    latitude: float
    longitude: float


class MeterDetail(MeterSummary):
    installation_type: str | None = None
    network: NetworkLocation = Field(default_factory=NetworkLocation)
    location: GeoLocation | None = None


class ConsumptionReading(BaseModel):
    timestamp: datetime
    energy_kwh: float
    energy_kvah: float
    voltage_r: float | None = None


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    has_next: bool


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    data: T
    meta: PageMeta | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
