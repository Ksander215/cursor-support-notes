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


class DigitalOrder(Base):
    """
    Digital order records for product sales (templates, courses, etc.)
    """

    __tablename__ = "digital_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Order ID for external reference
    order_id = Column(String, nullable=False, unique=True, index=True)

    # Customer info
    email = Column(String, nullable=False, index=True)

    # Product info
    product_code = Column(String, nullable=False)  # e.g. "template_01", "course_01"
    product_name = Column(String, nullable=False)

    # Amount
    amount = Column(Float, nullable=False)
    currency = Column(String, default="RUB")

    # Status
    payment_status = Column(
        String, nullable=False, index=True
    )  # "pending", "paid", "canceled", "refunded"
    delivery_status = Column(String, nullable=False, index=True)  # "pending", "delivered", "failed"
    delivery_attempts = Column(Integer, default=0)

    # Delivery info
    delivery_data = Column(JSON, nullable=True)  # Email, download link, etc.

    # Extra data
    extra_data = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)


class Lead(Base):
    """Lead records for marketing funnel."""

    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Contact info
    email = Column(String, nullable=False, unique=True, index=True)
    phone = Column(String, nullable=True)

    # Source attribution
    source = Column(String, nullable=False, index=True)  # "free_scan", "webinar", "organic", etc.
    utm_campaign = Column(String, nullable=True)
    utm_content = Column(String, nullable=True)
    utm_medium = Column(String, nullable=True)
    utm_source = Column(String, nullable=True)
    utm_term = Column(String, nullable=True)

    # Lead data
    name = Column(String, nullable=True)
    company = Column(String, nullable=True)
    role = Column(String, nullable=True)

    # Scoring
    score = Column(Integer, nullable=True)
    segment = Column(String, nullable=True, index=True)  # "hot", "warm", "cold", "cold_out"

    # Status
    status = Column(
        String, nullable=False, index=True
    )  # "new", "contacted", "qualified", "converted", "lost"

    # Audit linkage (if lead came from free scan)
    audit_id = Column(String, nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)


class Referral(Base):
    """Referral tracking for partner program."""

    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Organizations
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    referred_org_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=True, index=True
    )  # New org using referral code
    partner_org_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=True, index=True
    )  # Partner who referred

    # Referral code
    referral_code = Column(String, nullable=False, unique=True, index=True)

    # Payment linkage (for commission tracking)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True, index=True)

    # Commission
    commission_amount = Column(Float, nullable=True)
    commission_paid = Column(Boolean, default=False)

    # Status
    status = Column(String, nullable=False, index=True)  # "pending", "converted", "paid", "expired"

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    converted_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)


class Webhook(Base):
    """Webhook configuration for notifications."""

    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Organization
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Webhook config
    url = Column(String, nullable=False)
    secret = Column(String, nullable=True)

    # Events to listen to
    events = Column(JSON, nullable=False)  # ["payment.succeeded", "payment.failed", etc.]

    # Status
    is_active = Column(Boolean, default=True)
    status = Column(String, nullable=False, index=True)  # "active", "inactive", "failed"

    # Retry config
    max_retries = Column(Integer, default=3)

    # Last attempt
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
