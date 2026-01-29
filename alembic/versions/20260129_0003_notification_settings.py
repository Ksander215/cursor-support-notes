"""notification settings table

Revision ID: 20260129_0003
Revises: 20260125_0002
Create Date: 2026-01-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260129_0003"
down_revision = "20260125_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Notification settings
    op.create_table(
        "notification_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),  # email, slack, telegram, webhook
        sa.Column("events", sa.JSON(), nullable=False),  # список событий
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
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
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="fk_notification_settings_org_id_organizations"),
        sa.UniqueConstraint("org_id", "channel", name="uq_notification_settings_org_channel"),
    )
    op.create_index("ix_notification_settings_org_id", "notification_settings", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_settings_org_id", table_name="notification_settings")
    op.drop_table("notification_settings")
