"""Add digital_orders table for digital product sales.

Revision ID: 20260226_0010
Revises: 20260209_0009
Create Date: 2026-02-26

This migration creates the digital_orders table for tracking purchases of
digital products (PDF guides, CI/CD templates) with automatic delivery.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260226_0010"
down_revision = "20260209_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "digital_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Order identification
        sa.Column("order_id", sa.String(), nullable=False, unique=True),
        # Customer information
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        # Product details
        sa.Column("product_type", sa.String(), nullable=False),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="RUB"),
        # Payment tracking
        sa.Column("payment_provider", sa.String(), nullable=False, server_default="yookassa"),
        sa.Column("payment_id", sa.String(), nullable=True),
        sa.Column("payment_status", sa.String(), nullable=False, server_default="pending"),
        # Referral tracking
        sa.Column("referral_code", sa.String(), nullable=True),
        sa.Column(
            "commission_calculated", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        # Delivery tracking
        sa.Column("delivery_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_error", sa.Text(), nullable=True),
        # Customer metadata
        sa.Column("customer_ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name="fk_digital_orders_org_id",
        ),
    )

    # Create indexes for common queries
    op.create_index("ix_digital_orders_order_id", "digital_orders", ["order_id"], unique=True)
    op.create_index("ix_digital_orders_email", "digital_orders", ["email"])
    op.create_index("ix_digital_orders_org_id", "digital_orders", ["org_id"])
    op.create_index("ix_digital_orders_product_type", "digital_orders", ["product_type"])
    op.create_index("ix_digital_orders_payment_status", "digital_orders", ["payment_status"])
    op.create_index("ix_digital_orders_delivery_status", "digital_orders", ["delivery_status"])
    op.create_index("ix_digital_orders_payment_id", "digital_orders", ["payment_id"])
    op.create_index("ix_digital_orders_referral_code", "digital_orders", ["referral_code"])
    # Composite index for payment status queries
    op.create_index(
        "ix_digital_orders_payment_delivery_status",
        "digital_orders",
        ["payment_status", "delivery_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_digital_orders_payment_delivery_status", table_name="digital_orders")
    op.drop_index("ix_digital_orders_referral_code", table_name="digital_orders")
    op.drop_index("ix_digital_orders_payment_id", table_name="digital_orders")
    op.drop_index("ix_digital_orders_delivery_status", table_name="digital_orders")
    op.drop_index("ix_digital_orders_payment_status", table_name="digital_orders")
    op.drop_index("ix_digital_orders_product_type", table_name="digital_orders")
    op.drop_index("ix_digital_orders_org_id", table_name="digital_orders")
    op.drop_index("ix_digital_orders_email", table_name="digital_orders")
    op.drop_index("ix_digital_orders_order_id", table_name="digital_orders")
    op.drop_table("digital_orders")
