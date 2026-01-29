from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, unique=True)  # e.g. "free", "pro"
    name = Column(String, nullable=False)

    # Limits (NULL means "unlimited"/"not enforced")
    requests_per_minute = Column(Integer, nullable=True)
    monthly_audits_quota = Column(Integer, nullable=True)
    concurrency_limit = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)

    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    # Store as string UUID so it works on both SQLite/Postgres without extensions
    id = Column(String, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    name = Column(String, nullable=True)
    prefix = Column(String, nullable=False)  # for display / lookup hints
    last4 = Column(String, nullable=False)
    hashed_key = Column(String, nullable=False, unique=True)  # sha256 hex

    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    is_admin = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class UsageBucket(Base):
    __tablename__ = "usage_buckets"
    __table_args__ = (
        UniqueConstraint("org_id", "api_key_id", "metric", "bucket_start", name="uq_usage_bucket"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    api_key_id = Column(String, ForeignKey("api_keys.id"), nullable=False, index=True)

    metric = Column(String, nullable=False)  # e.g. "requests", "audits_created"
    bucket_start = Column(DateTime(timezone=True), nullable=False, index=True)  # UTC month start
    count = Column(Integer, nullable=False, server_default=text("0"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Audit(Base):
    __tablename__ = "audits"

    id = Column(String, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    created_by_api_key_id = Column(String, ForeignKey("api_keys.id"), nullable=True, index=True)

    target = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    status = Column(String, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    overall_score = Column(Float, nullable=True)
    risk_level = Column(String, nullable=True)

    result_json = Column(JSON, nullable=True)
    report_md = Column(Text, nullable=True)
    error = Column(Text, nullable=True)


class NotificationSettings(Base):
    __tablename__ = "notification_settings"
    __table_args__ = (
        UniqueConstraint("org_id", "channel", name="uq_notification_settings_org_channel"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    channel = Column(String, nullable=False)  # email, slack, telegram, webhook
    events = Column(JSON, nullable=False)  # список событий: ["scan_completed", "critical_vulnerability_found", ...]
    enabled = Column(Boolean, nullable=False, server_default=text("true"))

    # Канал-специфичные настройки (JSON)
    # Для email: {"smtp_host", "smtp_port", "smtp_user", "smtp_password", "from_email", "to_emails": []}
    # Для slack: {"webhook_url"}
    # Для telegram: {"bot_token", "chat_id"}
    # Для webhook: {"webhook_url", "secret"}
    config = Column(JSON, nullable=False, server_default=text("'{}'"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScanProgress(Base):
    __tablename__ = "scan_progress"
    __table_args__ = (
        UniqueConstraint("audit_id", "step_name", name="uq_scan_progress_audit_step"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audit_id = Column(String, ForeignKey("audits.id"), nullable=False, index=True)

    step_name = Column(String, nullable=False)  # e.g. "ssl", "headers", "ports", "web_vulnerabilities", "report"
    step_status = Column(String, nullable=False)  # "pending", "running", "completed", "failed"
    step_progress = Column(Integer, nullable=True)  # 0-100 percentage
    step_message = Column(String, nullable=True)  # optional status message
    step_error = Column(Text, nullable=True)  # error message if failed

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

