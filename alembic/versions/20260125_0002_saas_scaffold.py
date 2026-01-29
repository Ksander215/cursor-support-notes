"""saas scaffold tables

Revision ID: 20260125_0002
Revises: 20260125_0001
Create Date: 2026-01-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260125_0002"
down_revision = "20260125_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SaaS: plans
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("requests_per_minute", sa.Integer(), nullable=True),
        sa.Column("monthly_audits_quota", sa.Integer(), nullable=True),
        sa.Column("concurrency_limit", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    # SaaS: organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name="fk_organizations_plan_id_plans"),
    )

    # SaaS: api keys
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("prefix", sa.String(), nullable=False),
        sa.Column("last4", sa.String(), nullable=False),
        sa.Column("hashed_key", sa.String(), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="fk_api_keys_org_id_organizations"),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["org_id"])

    # SaaS: usage buckets
    op.create_table(
        "usage_buckets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("api_key_id", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="fk_usage_buckets_org_id_organizations"),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], name="fk_usage_buckets_api_key_id_api_keys"),
        sa.UniqueConstraint("org_id", "api_key_id", "metric", "bucket_start", name="uq_usage_bucket"),
    )
    op.create_index("ix_usage_buckets_org_id", "usage_buckets", ["org_id"])
    op.create_index("ix_usage_buckets_api_key_id", "usage_buckets", ["api_key_id"])
    op.create_index("ix_usage_buckets_bucket_start", "usage_buckets", ["bucket_start"])

    # Extend audits (tenant + key attribution). Use batch for sqlite compatibility.
    with op.batch_alter_table("audits") as batch:
        batch.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("created_by_api_key_id", sa.String(), nullable=True))
        batch.create_index("ix_audits_tenant_id", ["tenant_id"])
        batch.create_index("ix_audits_created_by_api_key_id", ["created_by_api_key_id"])
        batch.create_foreign_key(
            "fk_audits_tenant_id_organizations",
            "organizations",
            ["tenant_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_audits_created_by_api_key_id_api_keys",
            "api_keys",
            ["created_by_api_key_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("audits") as batch:
        batch.drop_constraint("fk_audits_created_by_api_key_id_api_keys", type_="foreignkey")
        batch.drop_constraint("fk_audits_tenant_id_organizations", type_="foreignkey")
        batch.drop_index("ix_audits_created_by_api_key_id")
        batch.drop_index("ix_audits_tenant_id")
        batch.drop_column("created_by_api_key_id")
        batch.drop_column("tenant_id")

    op.drop_index("ix_usage_buckets_bucket_start", table_name="usage_buckets")
    op.drop_index("ix_usage_buckets_api_key_id", table_name="usage_buckets")
    op.drop_index("ix_usage_buckets_org_id", table_name="usage_buckets")
    op.drop_table("usage_buckets")

    op.drop_index("ix_api_keys_org_id", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_table("organizations")
    op.drop_table("plans")
