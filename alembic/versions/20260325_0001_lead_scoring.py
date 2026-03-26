"""add lead scoring and attribution

Revision ID: 20260325_0001_lead_scoring
Revises:
Create Date: 2026-03-25

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260325_0001_lead_scoring"
down_revision = "12814dfc9c90"
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to leads table
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("utm_source", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("utm_medium", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("utm_campaign", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("utm_content", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("utm_term", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("score", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("segment", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("email_opens", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("email_clicks", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("page_views", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "converted_to_org_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("pipedrive_deal_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("extra_data", sa.JSON(), nullable=True))

    # Create indexes for new columns
    op.create_index("ix_leads_utm_source", "leads", ["utm_source"])
    op.create_index("ix_leads_utm_medium", "leads", ["utm_medium"])
    op.create_index("ix_leads_utm_campaign", "leads", ["utm_campaign"])
    op.create_index("ix_leads_segment", "leads", ["segment"])

    # Create lead_events table
    op.create_table(
        "lead_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_source", sa.String(), nullable=True),
        sa.Column("event_data", sa.JSON(), nullable=True),
        sa.Column("score_delta", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("utm_source", sa.String(), nullable=True),
        sa.Column("utm_medium", sa.String(), nullable=True),
        sa.Column("utm_campaign", sa.String(), nullable=True),
    )
    op.create_index("ix_lead_events_lead_id", "lead_events", ["lead_id"])
    op.create_index("ix_lead_events_event_type", "lead_events", ["event_type"])

    # Create lead_attribution table
    op.create_table(
        "lead_attribution",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("touch_order", sa.Integer(), nullable=False),
        sa.Column("touch_type", sa.String(), nullable=False),
        sa.Column("utm_source", sa.String(), nullable=True),
        sa.Column("utm_medium", sa.String(), nullable=True),
        sa.Column("utm_campaign", sa.String(), nullable=True),
        sa.Column("utm_content", sa.String(), nullable=True),
        sa.Column("utm_term", sa.String(), nullable=True),
        sa.Column("referrer_url", sa.String(), nullable=True),
        sa.Column("referrer_domain", sa.String(), nullable=True),
        sa.Column("landing_page", sa.String(), nullable=True),
        sa.Column(
            "touched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("led_to_conversion", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("conversion_value", sa.Float(), nullable=True),
    )
    op.create_index("ix_lead_attribution_lead_id", "lead_attribution", ["lead_id"])
    op.create_index("ix_lead_attribution_utm_source", "lead_attribution", ["utm_source"])
    op.create_index("ix_lead_attribution_utm_medium", "lead_attribution", ["utm_medium"])
    op.create_index("ix_lead_attribution_utm_campaign", "lead_attribution", ["utm_campaign"])


def downgrade():
    # Drop lead_attribution table
    op.drop_index("ix_lead_attribution_utm_campaign", "lead_attribution")
    op.drop_index("ix_lead_attribution_utm_medium", "lead_attribution")
    op.drop_index("ix_lead_attribution_utm_source", "lead_attribution")
    op.drop_index("ix_lead_attribution_lead_id", "lead_attribution")
    op.drop_table("lead_attribution")

    # Drop lead_events table
    op.drop_index("ix_lead_events_event_type", "lead_events")
    op.drop_index("ix_lead_events_lead_id", "lead_events")
    op.drop_table("lead_events")

    # Drop indexes from leads
    op.drop_index("ix_leads_segment", "leads")
    op.drop_index("ix_leads_utm_campaign", "leads")
    op.drop_index("ix_leads_utm_medium", "leads")
    op.drop_index("ix_leads_utm_source", "leads")

    # Drop columns from leads
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.drop_column("extra_data")
        batch_op.drop_column("pipedrive_deal_id")
        batch_op.drop_column("converted_at")
        batch_op.drop_column("converted_to_org_id")
        batch_op.drop_column("page_views")
        batch_op.drop_column("email_clicks")
        batch_op.drop_column("email_opens")
        batch_op.drop_column("last_activity_at")
        batch_op.drop_column("segment")
        batch_op.drop_column("score")
        batch_op.drop_column("utm_term")
        batch_op.drop_column("utm_content")
        batch_op.drop_column("utm_campaign")
        batch_op.drop_column("utm_medium")
        batch_op.drop_column("utm_source")
