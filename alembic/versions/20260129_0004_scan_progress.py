"""scan progress table

Revision ID: 20260129_0004
Revises: 20260129_0003
Create Date: 2026-01-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20260129_0004"
down_revision = "20260129_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Scan progress table
    op.create_table(
        "scan_progress",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("audit_id", sa.String(), nullable=False),
        sa.Column(
            "step_name", sa.String(), nullable=False
        ),  # e.g. "ssl", "headers", "ports", "web_vulnerabilities", "report"
        sa.Column(
            "step_status", sa.String(), nullable=False
        ),  # "pending", "running", "completed", "failed"
        sa.Column("step_progress", sa.Integer(), nullable=True),  # 0-100 percentage
        sa.Column("step_message", sa.String(), nullable=True),  # optional status message
        sa.Column("step_error", sa.Text(), nullable=True),  # error message if failed
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["audit_id"], ["audits.id"], name="fk_scan_progress_audit_id_audits"
        ),
        sa.UniqueConstraint("audit_id", "step_name", name="uq_scan_progress_audit_step"),
    )
    op.create_index("ix_scan_progress_audit_id", "scan_progress", ["audit_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_progress_audit_id", table_name="scan_progress")
    op.drop_table("scan_progress")
