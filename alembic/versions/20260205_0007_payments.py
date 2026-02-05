"""Add payments table for payment idempotency tracking.

Revision ID: 20260205_0007
Revises: 20260201_0006
Create Date: 2026-02-05

This migration creates the payments table for tracking processed payments
from payment providers (YooKassa, Stripe) to ensure idempotency of webhook events.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260205_0007"
down_revision = "20260201_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Payment provider info
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("payment_id", sa.String(), nullable=False),
        # Organization context
        sa.Column("org_id", sa.Integer(), nullable=False),
        # Payment details
        sa.Column("plan_code", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(), nullable=True, server_default="RUB"),
        # Status
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        # Metadata from payment provider (renamed from 'metadata' to avoid SQLAlchemy reserved name)
        sa.Column("payment_metadata", sa.JSON(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name="fk_payments_org_id",
        ),
        sa.UniqueConstraint("provider", "payment_id", name="uq_payment_provider_id"),
    )

    # Create indexes for common queries
    op.create_index("ix_payments_provider", "payments", ["provider"])
    op.create_index("ix_payments_payment_id", "payments", ["payment_id"])
    op.create_index("ix_payments_org_id", "payments", ["org_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    # Composite index for idempotency check (provider + payment_id)
    op.create_index(
        "ix_payments_provider_payment_id",
        "payments",
        ["provider", "payment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_payments_provider_payment_id", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_org_id", table_name="payments")
    op.drop_index("ix_payments_payment_id", table_name="payments")
    op.drop_index("ix_payments_provider", table_name="payments")
    op.drop_table("payments")
