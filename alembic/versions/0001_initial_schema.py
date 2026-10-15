"""Create sales service tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

vehicle_status = sa.Enum("AVAILABLE", "RESERVED", "SOLD", name="vehicle_status", native_enum=False)
purchase_status = sa.Enum("PENDING", "PAID", "CANCELED", name="purchase_status", native_enum=False)
catalog_sync_status = sa.Enum(
    "PENDING", "SYNCED", "FAILED", name="catalog_sync_status", native_enum=False
)
payment_event_status = sa.Enum("PAID", "CANCELED", name="payment_event_status", native_enum=False)


def upgrade() -> None:
    op.create_table(
        "vehicle_listings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("brand", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(length=50), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("status", vehicle_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicle_listings_status", "vehicle_listings", ["status"])
    op.create_index(
        "ix_vehicle_listing_status_price_id",
        "vehicle_listings",
        ["status", "price", "id"],
    )

    op.create_table(
        "purchases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vehicle_id", sa.String(length=36), nullable=False),
        sa.Column("buyer_cpf", sa.String(length=11), nullable=False),
        sa.Column("price_at_purchase", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("payment_code", sa.String(length=64), nullable=False),
        sa.Column("status", purchase_status, nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("sale_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("catalog_sync_status", catalog_sync_status, nullable=False),
        sa.Column("catalog_sync_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("catalog_sync_last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicle_listings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("payment_code"),
    )
    op.create_index("ix_purchases_vehicle_id", "purchases", ["vehicle_id"])
    op.create_index("ix_purchases_status", "purchases", ["status"])
    op.create_index("ix_purchases_catalog_sync_status", "purchases", ["catalog_sync_status"])
    op.create_index(
        "ix_purchase_status_price_vehicle",
        "purchases",
        ["status", "price_at_purchase", "vehicle_id"],
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("purchase_id", sa.String(length=36), nullable=False),
        sa.Column("payment_code", sa.String(length=64), nullable=False),
        sa.Column("status", payment_event_status, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_payment_events_purchase_id", "payment_events", ["purchase_id"])
    op.create_index("ix_payment_events_payment_code", "payment_events", ["payment_code"])


def downgrade() -> None:
    op.drop_index("ix_payment_events_payment_code", table_name="payment_events")
    op.drop_index("ix_payment_events_purchase_id", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("ix_purchase_status_price_vehicle", table_name="purchases")
    op.drop_index("ix_purchases_catalog_sync_status", table_name="purchases")
    op.drop_index("ix_purchases_status", table_name="purchases")
    op.drop_index("ix_purchases_vehicle_id", table_name="purchases")
    op.drop_table("purchases")
    op.drop_index("ix_vehicle_listing_status_price_id", table_name="vehicle_listings")
    op.drop_index("ix_vehicle_listings_status", table_name="vehicle_listings")
    op.drop_table("vehicle_listings")
