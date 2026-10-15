from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import CatalogSyncStatus, PaymentStatus, PurchaseStatus, VehicleStatus
from app.validation import normalize_cpf


class VehicleUpsert(BaseModel):
    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=1886)
    color: str = Field(min_length=1, max_length=50)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    status: VehicleStatus
    source_version: int = Field(ge=1)

    @field_validator("brand", "model", "color")
    @classmethod
    def clean_text(cls, value: str) -> str:
        clean = " ".join(value.split())
        if not clean:
            raise ValueError("campo não pode ser vazio")
        return clean

    @field_validator("year")
    @classmethod
    def validate_year(cls, value: int) -> int:
        if value > datetime.now(UTC).year + 1:
            raise ValueError("ano não pode ser superior ao próximo ano")
        return value


class VehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brand: str
    model: str
    year: int
    color: str
    price: Decimal
    status: VehicleStatus
    source_version: int
    created_at: datetime
    updated_at: datetime


class VehicleListResponse(BaseModel):
    items: list[VehicleRead]
    total: int
    limit: int
    offset: int


class SoldVehicleRead(BaseModel):
    id: str
    brand: str
    model: str
    year: int
    color: str
    price: Decimal
    status: VehicleStatus
    purchase_date: date
    sale_date: datetime


class SoldVehicleListResponse(BaseModel):
    items: list[SoldVehicleRead]
    total: int
    limit: int
    offset: int


class PurchaseCreate(BaseModel):
    vehicle_id: str = Field(min_length=36, max_length=36)
    buyer_cpf: str
    purchase_date: date

    @field_validator("buyer_cpf")
    @classmethod
    def validate_cpf(cls, value: str) -> str:
        return normalize_cpf(value)

    @field_validator("vehicle_id")
    @classmethod
    def validate_vehicle_id(cls, value: str) -> str:
        try:
            return str(UUID(value))
        except ValueError as exc:
            raise ValueError("vehicle_id deve ser um UUID válido") from exc

    @field_validator("purchase_date")
    @classmethod
    def validate_purchase_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("data da compra não pode ser futura")
        return value


class PurchaseRead(BaseModel):
    id: str
    vehicle_id: str
    buyer_cpf_masked: str
    price_at_purchase: Decimal
    purchase_date: date
    payment_code: str
    status: PurchaseStatus
    sale_date: datetime | None
    catalog_sync_status: CatalogSyncStatus
    created_at: datetime
    updated_at: datetime


class PaymentProcess(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    payment_code: str = Field(min_length=1, max_length=64)
    status: PaymentStatus
    occurred_at: datetime

    @field_validator("event_id", "payment_code")
    @classmethod
    def strip_identifiers(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("identificador não pode ser vazio")
        return clean

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at deve conter fuso horário")
        return value.astimezone(UTC)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
