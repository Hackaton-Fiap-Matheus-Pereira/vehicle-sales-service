from enum import StrEnum


class VehicleStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    SOLD = "SOLD"


class PurchaseStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELED = "CANCELED"


class PaymentStatus(StrEnum):
    PAID = "PAID"
    CANCELED = "CANCELED"


class CatalogSyncStatus(StrEnum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
