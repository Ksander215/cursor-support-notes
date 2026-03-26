"""Add white_label_config field to organizations table.

Revision ID: 12814dfc9c90
Revises: 20260307_0011
Create Date: 2026-02-06

This migration adds white-label configuration support for organizations:
- white_label_config JSON field in organizations table
- Stores company_name, logo_url, primary_color for white-label PDF reports
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "12814dfc9c90"
down_revision = "20260307_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Проверяем существование колонки перед добавлением
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("organizations")]

    # Проверяем, SQLite ли это
    is_sqlite = conn.dialect.name == "sqlite"

    # Добавляем white_label_config только если его нет
    if "white_label_config" not in columns:
        if is_sqlite:
            # Для SQLite используем batch mode для совместимости
            with op.batch_alter_table("organizations") as batch:
                batch.add_column(sa.Column("white_label_config", sa.JSON(), nullable=True))
        else:
            # Для PostgreSQL и других БД используем обычный add_column
            op.add_column(
                "organizations",
                sa.Column("white_label_config", sa.JSON(), nullable=True),
            )


def downgrade() -> None:
    # Проверяем существование колонки перед удалением
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("organizations")]

    # Проверяем, SQLite ли это
    is_sqlite = conn.dialect.name == "sqlite"

    # Удаляем white_label_config только если он существует
    if "white_label_config" in columns:
        if is_sqlite:
            # Для SQLite используем batch mode
            with op.batch_alter_table("organizations") as batch:
                batch.drop_column("white_label_config")
        else:
            # Для PostgreSQL и других БД используем обычный drop_column
            op.drop_column("organizations", "white_label_config")
