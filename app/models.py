from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import CatalogSyncStatus, PaymentStatus, PurchaseStatus, VehicleStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


def uuid_string() -> str:
    return str(uuid4())


def enum_column(enum_type: type, name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class VehicleListing(TimestampMixin, Base):
    __tablename__ = "vehicle_listings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    brand: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[VehicleStatus] = mapped_column(
        enum_column(VehicleStatus, "vehicle_status"),
        default=VehicleStatus.AVAILABLE,
        nullable=False,
        index=True,
    )

    purchases: Mapped[list["Purchase"]] = relationship(back_populates="vehicle")

    __table_args__ = (Index("ix_vehicle_listing_status_price_id", "status", "price", "id"),)


class Purchase(TimestampMixin, Base):
    __tablename__ = "purchases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicle_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    buyer_cpf: Mapped[str] = mapped_column(String(11), nullable=False)
    price_at_purchase: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[PurchaseStatus] = mapped_column(
        enum_column(PurchaseStatus, "purchase_status"),
        default=PurchaseStatus.PENDING,
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    sale_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    catalog_sync_status: Mapped[CatalogSyncStatus] = mapped_column(
        enum_column(CatalogSyncStatus, "catalog_sync_status"),
        default=CatalogSyncStatus.PENDING,
        nullable=False,
        index=True,
    )
    catalog_sync_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    catalog_sync_last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    vehicle: Mapped[VehicleListing] = relationship(back_populates="purchases")
    payment_events: Mapped[list["PaymentEvent"]] = relationship(back_populates="purchase")

    __table_args__ = (
        Index("ix_purchase_status_price_vehicle", "status", "price_at_purchase", "vehicle_id"),
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    purchase_id: Mapped[str] = mapped_column(
        ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus, "payment_event_status"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    purchase: Mapped[Purchase] = relationship(back_populates="payment_events")
