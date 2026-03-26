"""Add leads table and is_guest column on audits.

Revision ID: 20260307_0011
Revises: 20260226_0010
Create Date: 2026-03-07

Creates the ``leads`` table for marketing-funnel lead capture
(free-checklist, free-scan, beta sign-ups) and adds the
``is_guest`` boolean flag to ``audits`` so guest scans are
never mixed with paid-user data.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260307_0011"
down_revision = "20260226_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. leads table
    # ------------------------------------------------------------------
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),  # checklist | free_scan | beta
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("referral_code", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_source", "leads", ["source"])
    op.create_index("ix_leads_referral_code", "leads", ["referral_code"])
    # Composite index for rate-limit query (email + source + created_at)
    op.create_index(
        "ix_leads_email_source_created_at",
        "leads",
        ["email", "source", "created_at"],
    )

    # ------------------------------------------------------------------
    # 2. audits.is_guest flag
    # ------------------------------------------------------------------
    op.add_column(
        "audits",
        sa.Column(
            "is_guest",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("audits", "is_guest")

    op.drop_index("ix_leads_email_source_created_at", table_name="leads")
    op.drop_index("ix_leads_referral_code", table_name="leads")
    op.drop_index("ix_leads_source", table_name="leads")
    op.drop_index("ix_leads_email", table_name="leads")
    op.drop_table("leads")
