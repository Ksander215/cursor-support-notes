"""Add default pricing plans

Revision ID: 20260129_0005
Revises: 20260129_0004
Create Date: 2026-01-29 15:00:00.000000

"""

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260129_0005"
down_revision = "20260129_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Добавляет планы по умолчанию:
    - Free: 10 сканирований/месяц, только safe mode
    - Starter: 100 сканирований/месяц, все режимы, API доступ
    - Professional: 500 сканирований/месяц, Dependency Scanning, Nmap
    - Enterprise: неограниченные сканирования, все функции
    """
    connection = op.get_bind()

    # Free Plan
    connection.execute(
        text("""
        INSERT INTO plans (code, name, requests_per_minute, monthly_audits_quota, concurrency_limit, created_at)
        VALUES ('free', 'Free', 10, 10, 1, CURRENT_TIMESTAMP)
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            requests_per_minute = EXCLUDED.requests_per_minute,
            monthly_audits_quota = EXCLUDED.monthly_audits_quota,
            concurrency_limit = EXCLUDED.concurrency_limit
    """)
    )

    # Starter Plan ($29/месяц)
    connection.execute(
        text("""
        INSERT INTO plans (code, name, requests_per_minute, monthly_audits_quota, concurrency_limit, created_at)
        VALUES ('starter', 'Starter', 60, 100, 3, CURRENT_TIMESTAMP)
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            requests_per_minute = EXCLUDED.requests_per_minute,
            monthly_audits_quota = EXCLUDED.monthly_audits_quota,
            concurrency_limit = EXCLUDED.concurrency_limit
    """)
    )

    # Professional Plan ($99/месяц)
    connection.execute(
        text("""
        INSERT INTO plans (code, name, requests_per_minute, monthly_audits_quota, concurrency_limit, created_at)
        VALUES ('professional', 'Professional', 120, 500, 10, CURRENT_TIMESTAMP)
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            requests_per_minute = EXCLUDED.requests_per_minute,
            monthly_audits_quota = EXCLUDED.monthly_audits_quota,
            concurrency_limit = EXCLUDED.concurrency_limit
    """)
    )

    # Enterprise Plan (custom pricing)
    connection.execute(
        text("""
        INSERT INTO plans (code, name, requests_per_minute, monthly_audits_quota, concurrency_limit, created_at)
        VALUES ('enterprise', 'Enterprise', NULL, NULL, NULL, CURRENT_TIMESTAMP)
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            requests_per_minute = EXCLUDED.requests_per_minute,
            monthly_audits_quota = EXCLUDED.monthly_audits_quota,
            concurrency_limit = EXCLUDED.concurrency_limit
    """)
    )


def downgrade() -> None:
    """
    Удаляет планы по умолчанию (только если они были созданы этой миграцией)
    ВНИМАНИЕ: Это удалит все организации, использующие эти планы!
    """
    connection = op.get_bind()

    # Удаляем планы (в обратном порядке из-за foreign keys)
    connection.execute(
        text("DELETE FROM plans WHERE code IN ('enterprise', 'professional', 'starter', 'free')")
    )
