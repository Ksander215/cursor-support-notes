"""Add referral system for partner program.

Revision ID: 20260206_0008
Revises: 20260205_0007
Create Date: 2026-02-06

This migration adds referral system support:
- referral_code field in organizations table
- referred_by_org_id field in organizations table
- referrals table for tracking referral commissions
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260206_0008"
down_revision = "20260205_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Проверяем существование колонок перед добавлением
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("organizations")]
    indexes = [idx["name"] for idx in inspector.get_indexes("organizations")]
    foreign_keys = [fk["name"] for fk in inspector.get_foreign_keys("organizations")]

    # Проверяем, SQLite ли это
    is_sqlite = conn.dialect.name == "sqlite"

    # Определяем, что нужно добавить
    need_referral_code = "referral_code" not in columns
    need_referred_by = "referred_by_org_id" not in columns
    need_index = "ix_organizations_referral_code" not in indexes
    need_fk = "fk_organizations_referred_by_org_id" not in foreign_keys

    # Для SQLite: если нужно добавить FK или колонки, используем batch mode
    if is_sqlite and (need_referral_code or need_referred_by or need_fk):
        with op.batch_alter_table("organizations") as batch:
            if need_referral_code:
                batch.add_column(sa.Column("referral_code", sa.String(), nullable=True))
            if need_referred_by:
                batch.add_column(sa.Column("referred_by_org_id", sa.Integer(), nullable=True))
            if need_fk:
                # Для SQLite внешний ключ добавляется через batch mode
                # Колонка должна существовать (либо уже есть, либо добавлена выше в этом же batch)
                batch.create_foreign_key(
                    "fk_organizations_referred_by_org_id",
                    "organizations",
                    ["referred_by_org_id"],
                    ["id"],
                )
    else:
        # Для PostgreSQL используем обычные операции
        if need_referral_code:
            op.add_column("organizations", sa.Column("referral_code", sa.String(), nullable=True))
        if need_referred_by:
            op.add_column(
                "organizations", sa.Column("referred_by_org_id", sa.Integer(), nullable=True)
            )
        if need_fk:
            op.create_foreign_key(
                "fk_organizations_referred_by_org_id",
                "organizations",
                "organizations",
                ["referred_by_org_id"],
                ["id"],
            )

    # Индекс можно создать отдельно (не требует batch mode)
    if need_index:
        op.create_index(
            "ix_organizations_referral_code", "organizations", ["referral_code"], unique=True
        )

    # Проверяем существование таблицы referrals перед созданием
    tables = inspector.get_table_names()

    if "referrals" not in tables:
        # Создаём таблицу referrals для отслеживания комиссий
        op.create_table(
            "referrals",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            # Партнёр (кто привлёк)
            sa.Column("partner_org_id", sa.Integer(), nullable=False),
            # Клиент (кого привлекли)
            sa.Column("client_org_id", sa.Integer(), nullable=False),
            # Платеж, за который начислена комиссия
            sa.Column("payment_id", sa.Integer(), nullable=True),
            # Детали комиссии
            sa.Column("commission_amount", sa.Float(), nullable=False),  # Сумма комиссии в рублях
            sa.Column(
                "commission_percent", sa.Float(), nullable=False, server_default=sa.text("20.0")
            ),  # Процент комиссии (20% по умолчанию)
            sa.Column("payment_amount", sa.Float(), nullable=False),  # Сумма платежа клиента
            sa.Column("plan_code", sa.String(), nullable=True),  # План, за который заплатил клиент
            # Статус
            sa.Column(
                "status", sa.String(), nullable=False, server_default="pending"
            ),  # pending, paid, cancelled
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["partner_org_id"], ["organizations.id"], name="fk_referrals_partner_org_id"
            ),
            sa.ForeignKeyConstraint(
                ["client_org_id"], ["organizations.id"], name="fk_referrals_client_org_id"
            ),
            sa.ForeignKeyConstraint(
                ["payment_id"], ["payments.id"], name="fk_referrals_payment_id"
            ),
        )

        # Индексы для быстрого поиска
        op.create_index("ix_referrals_partner_org_id", "referrals", ["partner_org_id"])
        op.create_index("ix_referrals_client_org_id", "referrals", ["client_org_id"])
        op.create_index("ix_referrals_status", "referrals", ["status"])
    else:
        # Таблица уже существует, проверяем индексы
        referrals_indexes = [idx["name"] for idx in inspector.get_indexes("referrals")]

        if "ix_referrals_partner_org_id" not in referrals_indexes:
            op.create_index("ix_referrals_partner_org_id", "referrals", ["partner_org_id"])
        if "ix_referrals_client_org_id" not in referrals_indexes:
            op.create_index("ix_referrals_client_org_id", "referrals", ["client_org_id"])
        if "ix_referrals_status" not in referrals_indexes:
            op.create_index("ix_referrals_status", "referrals", ["status"])


def downgrade() -> None:
    # Удаляем таблицу referrals
    op.drop_index("ix_referrals_status", table_name="referrals")
    op.drop_index("ix_referrals_client_org_id", table_name="referrals")
    op.drop_index("ix_referrals_partner_org_id", table_name="referrals")
    op.drop_table("referrals")

    # Удаляем внешний ключ
    op.drop_constraint("fk_organizations_referred_by_org_id", "organizations", type_="foreignkey")

    # Удаляем индекс
    op.drop_index("ix_organizations_referral_code", table_name="organizations")

    # Удаляем поля
    op.drop_column("organizations", "referred_by_org_id")
    op.drop_column("organizations", "referral_code")
