"""Add webhooks table for event delivery.

Revision ID: 20260209_0009
Revises: 20260206_0008
Create Date: 2026-02-09

This migration adds webhooks table for event delivery to external systems:
- webhooks table with org_id, url, events, secret, enabled, retry_count, last_delivery_at
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260209_0009"
down_revision = "20260206_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Проверяем существование таблицы webhooks перед созданием
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "webhooks" not in tables:
        # Создаём таблицу webhooks для доставки событий
        op.create_table(
            "webhooks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("org_id", sa.Integer(), nullable=False),
            # Webhook configuration
            sa.Column("url", sa.String(), nullable=False),
            sa.Column("events", sa.JSON(), nullable=False),
            sa.Column("secret", sa.String(), nullable=True),
            # Status
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            # Delivery tracking
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_failure_reason", sa.Text(), nullable=True),
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
            # Constraints
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="fk_webhooks_org_id"),
        )

        # Индексы для быстрого поиска
        op.create_index("ix_webhooks_org_id", "webhooks", ["org_id"])
        op.create_index("ix_webhooks_enabled", "webhooks", ["enabled"])
    else:
        # Таблица уже существует, проверяем индексы
        webhooks_indexes = [idx["name"] for idx in inspector.get_indexes("webhooks")]

        if "ix_webhooks_org_id" not in webhooks_indexes:
            op.create_index("ix_webhooks_org_id", "webhooks", ["org_id"])
        if "ix_webhooks_enabled" not in webhooks_indexes:
            op.create_index("ix_webhooks_enabled", "webhooks", ["enabled"])


def downgrade() -> None:
    # Удаляем индексы
    op.drop_index("ix_webhooks_enabled", table_name="webhooks")
    op.drop_index("ix_webhooks_org_id", table_name="webhooks")

    # Удаляем таблицу webhooks
    op.drop_table("webhooks")
