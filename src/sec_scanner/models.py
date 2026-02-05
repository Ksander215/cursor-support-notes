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
    events = Column(
        JSON, nullable=False
    )  # список событий: ["scan_completed", "critical_vulnerability_found", ...]
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

    step_name = Column(
        String, nullable=False
    )  # e.g. "ssl", "headers", "ports", "web_vulnerabilities", "report"
    step_status = Column(String, nullable=False)  # "pending", "running", "completed", "failed"
    step_progress = Column(Integer, nullable=True)  # 0-100 percentage
    step_message = Column(String, nullable=True)  # optional status message
    step_error = Column(Text, nullable=True)  # error message if failed

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditLog(Base):
    """
    Security audit log for tracking admin/sensitive actions.

    This table stores security-relevant events for compliance and investigation:
    - API key creation/revocation
    - Plan changes
    - Settings modifications
    - Admin authentication attempts
    - Sensitive data access

    Retention: Keep for compliance period (typically 1-7 years).
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # When the action occurred
    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # What action was performed
    action = Column(String, nullable=False, index=True)  # e.g. "api_key.created", "plan.changed"

    # Who performed the action
    actor_type = Column(String, nullable=False)  # "user", "api_key", "system", "anonymous"
    actor_id = Column(String, nullable=True, index=True)  # API key ID, user ID, or null for system
    actor_ip = Column(String, nullable=True)  # IP address of the actor
    actor_user_agent = Column(String, nullable=True)  # User-Agent header

    # What was affected
    resource_type = Column(String, nullable=False)  # "api_key", "organization", "plan", "settings"
    resource_id = Column(String, nullable=True, index=True)  # ID of the affected resource

    # Organization context
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Action details (JSON)
    # Contains action-specific data like old/new values, request parameters, etc.
    details = Column(JSON, nullable=True)

    # Result of the action
    status = Column(String, nullable=False)  # "success", "failure", "denied"
    error_message = Column(Text, nullable=True)  # Error message if failed

    # Request context
    request_id = Column(String, nullable=True, index=True)  # Correlation ID from X-Request-ID
    request_path = Column(String, nullable=True)  # API endpoint path
    request_method = Column(String, nullable=True)  # HTTP method


class Payment(Base):
    """
    Payment records for idempotency tracking.

    Stores information about processed payments from payment providers (YooKassa, Stripe)
    to prevent duplicate processing of webhook events.
    """

    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("provider", "payment_id", name="uq_payment_provider_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Payment provider info
    provider = Column(String, nullable=False, index=True)  # "yookassa", "stripe"
    payment_id = Column(String, nullable=False, index=True)  # Payment ID from provider

    # Organization context
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Payment details
    plan_code = Column(String, nullable=True)  # Plan code if subscription payment
    amount = Column(Float, nullable=True)  # Payment amount
    currency = Column(String, nullable=True, default="RUB")  # Currency code

    # Status
    status = Column(
        String, nullable=False, index=True
    )  # "succeeded", "canceled", "failed", "pending"
    event_type = Column(String, nullable=False)  # Webhook event type (e.g., "payment.succeeded")

    # Metadata from payment provider (renamed from 'metadata' to avoid SQLAlchemy reserved name)
    payment_metadata = Column(JSON, nullable=True)  # Additional payment metadata

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)  # When webhook was processed
