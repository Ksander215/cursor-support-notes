from typing import Any, Literal

from pydantic import BaseModel, Field

AuditMode = Literal["safe", "normal", "full"]
AuditStatus = Literal["queued", "running", "completed", "failed"]


class AuditCreateRequest(BaseModel):
    target: str = Field(
        ...,
        description="Domain, IPv4, or URL to audit",
        examples=["example.com", "192.168.1.1", "https://example.com"],
    )
    mode: AuditMode = Field(
        "safe",
        description="Audit depth: 'safe' (quick scan), 'normal' (standard), 'full' (comprehensive)",
    )

    model_config = {"json_schema_extra": {"example": {"target": "example.com", "mode": "safe"}}}


class AuditCreateResponse(BaseModel):
    audit_id: str = Field(
        ...,
        description="UUID of the created audit",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    status: AuditStatus = Field(..., description="Initial status of the audit (usually 'queued')")

    model_config = {
        "json_schema_extra": {
            "example": {"audit_id": "550e8400-e29b-41d4-a716-446655440000", "status": "queued"}
        }
    }


class AuditSummary(BaseModel):
    id: str = Field(..., description="UUID of the audit")
    target: str = Field(..., description="Target that was audited (domain, IP, or URL)")
    mode: AuditMode = Field(..., description="Audit mode used")
    status: AuditStatus = Field(
        ..., description="Current status: queued, running, completed, or failed"
    )
    created_at: str = Field(..., description="ISO 8601 timestamp when audit was created")
    started_at: str | None = Field(None, description="ISO 8601 timestamp when audit started")
    completed_at: str | None = Field(None, description="ISO 8601 timestamp when audit completed")
    overall_score: float | None = Field(
        None, description="Security score (0-100), higher is better", ge=0, le=100
    )
    risk_level: str | None = Field(None, description="Risk level: low, medium, high, critical")
    error: str | None = Field(None, description="Error message if status is 'failed'")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "target": "example.com",
                "mode": "safe",
                "status": "completed",
                "created_at": "2026-01-29T10:00:00Z",
                "started_at": "2026-01-29T10:00:05Z",
                "completed_at": "2026-01-29T10:05:00Z",
                "overall_score": 85.5,
                "risk_level": "low",
                "error": None,
            }
        }
    }


class AuditDetails(AuditSummary):
    result: dict[str, Any] | None = None
    report_md: str | None = None


class AuditListResponse(BaseModel):
    """Paginated list of audits with metadata"""

    items: list[AuditSummary]
    limit: int = Field(..., description="Requested limit (max items per page)")
    has_more: bool = Field(..., description="True if there are more items beyond this page")
    total: int | None = Field(
        None, description="Total count of audits (if available, None for performance)"
    )


class AdminApiKeyCreateRequest(BaseModel):
    """
    Minimal bootstrap to issue an API key.
    Intended for early-stage MVP. Later we can replace with full user/org flows.
    """

    org_name: str = Field(
        ..., min_length=2, max_length=80, description="Organization name", examples=["Acme Corp"]
    )
    key_name: str | None = Field(
        None,
        max_length=120,
        description="Optional name for this API key",
        examples=["Production API Key"],
    )
    is_admin: bool = Field(False, description="Admin key can manage other keys (future use)")

    # Optional plan controls (if plan doesn't exist, it will be created/updated)
    plan_code: str = Field(
        "free",
        min_length=2,
        max_length=32,
        description="Plan code identifier",
        examples=["free", "pro", "enterprise"],
    )
    plan_name: str = Field(
        "Free",
        min_length=2,
        max_length=64,
        description="Plan display name",
        examples=["Free", "Pro Plan", "Enterprise"],
    )
    requests_per_minute: int | None = Field(
        None, ge=1, le=10000, description="Rate limit: requests per minute"
    )
    monthly_audits_quota: int | None = Field(
        None, ge=1, le=1_000_000, description="Monthly audit quota limit"
    )
    concurrency_limit: int | None = Field(
        None, ge=1, le=1000, description="Maximum concurrent audits"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "org_name": "Acme Corp",
                "key_name": "Production API Key",
                "is_admin": False,
                "plan_code": "pro",
                "plan_name": "Pro Plan",
                "requests_per_minute": 100,
                "monthly_audits_quota": 1000,
                "concurrency_limit": 5,
            }
        }
    }


class AdminApiKeyCreateResponse(BaseModel):
    api_key: str = Field(..., description="Plain API key. Shown ONCE. Store securely.")
    api_key_id: str
    prefix: str
    last4: str
    org_id: int
    org_name: str
    plan_code: str


class ApiKeyCreateRequest(BaseModel):
    """Request to create a new API key for the current organization."""

    key_name: str | None = Field(
        None,
        max_length=120,
        description="Optional name for this API key",
        examples=["Production API Key", "Development Key"],
    )


class ApiKeyCreateResponse(BaseModel):
    """Response after creating a new API key."""

    api_key: str = Field(..., description="Plain API key. Shown ONCE. Store securely.")
    api_key_id: str
    prefix: str
    last4: str
    key_name: str | None = None


class ApiKeyInfo(BaseModel):
    """API key metadata (without the plain key)."""

    id: str
    name: str | None = None
    prefix: str
    last4: str
    is_admin: bool
    created_at: str | None = None


class ApiKeyListResponse(BaseModel):
    """List of API keys for the current organization."""

    keys: list[ApiKeyInfo]


class QuotaLimits(BaseModel):
    """Plan limits (None means unlimited)"""

    requests_per_minute: int | None = None
    monthly_audits_quota: int | None = None
    concurrency_limit: int | None = None


class QuotaUsage(BaseModel):
    """Current usage for current month"""

    requests: int = Field(..., ge=0)
    audits_created: int = Field(..., ge=0)
    month_start: str  # ISO datetime


class QuotaResponse(BaseModel):
    """Quota information for authenticated organization"""

    org_id: int
    org_name: str
    plan_code: str
    plan_name: str
    limits: QuotaLimits
    usage: QuotaUsage


class AuditHistoryItem(BaseModel):
    """Single item in audit history timeline"""

    id: str
    completed_at: str
    overall_score: float
    risk_level: str | None = None


class AuditHistoryResponse(BaseModel):
    """History of audits for a target"""

    target: str
    items: list[AuditHistoryItem]


class CIContext(BaseModel):
    """CI/CD context information"""

    provider: str = Field(..., description="CI provider: github, gitlab, azure")
    repo: str | None = Field(None, description="Repository identifier")
    commit: str | None = Field(None, description="Commit SHA")
    branch: str | None = Field(None, description="Branch name")
    pull_request: str | None = Field(None, description="Pull request number")


class CIScanRequest(BaseModel):
    """Request for CI/CD security scan"""

    target: str = Field(..., description="Domain, IPv4, or URL to audit")
    mode: AuditMode = Field("safe", description="Audit depth")
    fail_on: list[str] = Field(
        default=["critical"],
        description="Risk levels that should cause CI failure: critical, high, medium, low, or score threshold (e.g., 'score<60')",
    )
    wait: bool = Field(
        True,
        description="Wait for scan completion (synchronous mode). If false, returns audit_id immediately.",
    )
    timeout: int | None = Field(
        300, ge=30, le=1800, description="Maximum wait time in seconds (only used if wait=true)"
    )
    ci_context: CIContext | None = Field(None, description="CI/CD context information")


class CIScanResponse(BaseModel):
    """Response from CI/CD scan"""

    audit_id: str = Field(..., description="UUID of the created audit")
    status: AuditStatus = Field(..., description="Audit status")
    passed: bool = Field(..., description="Whether scan passed CI checks")
    overall_score: float | None = Field(None, description="Security score (0-100)", ge=0, le=100)
    risk_level: str | None = Field(None, description="Risk level: low, medium, high, critical")
    critical_issues_count: int = Field(0, ge=0, description="Number of critical issues found")
    failure_reason: str | None = Field(None, description="Reason for failure if passed=false")
    report_url: str | None = Field(None, description="URL to view full report")

    model_config = {
        "json_schema_extra": {
            "example": {
                "audit_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "passed": True,
                "overall_score": 85.5,
                "risk_level": "low",
                "critical_issues_count": 0,
                "failure_reason": None,
                "report_url": "/app/audits?id=550e8400-e29b-41d4-a716-446655440000",
            }
        }
    }


NotificationEvent = Literal[
    "scan_completed",
    "critical_vulnerability_found",
    "high_vulnerability_found",
    "quota_exceeded",
]

NotificationChannel = Literal["email", "slack", "telegram", "webhook"]


class NotificationSettingsCreate(BaseModel):
    """Request to create notification settings"""

    channel: NotificationChannel
    events: list[NotificationEvent] = Field(..., min_length=1)
    enabled: bool = Field(True)
    config: dict[str, Any] = Field(..., description="Channel-specific configuration")


class NotificationSettingsUpdate(BaseModel):
    """Request to update notification settings"""

    events: list[NotificationEvent] | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class NotificationSettingsResponse(BaseModel):
    """Notification settings response"""

    id: int
    org_id: int
    channel: NotificationChannel
    events: list[NotificationEvent]
    enabled: bool
    config: dict[str, Any]
    created_at: str
    updated_at: str


StepStatus = Literal["pending", "running", "completed", "failed"]


class ScanProgressStep(BaseModel):
    """Single step in scan progress"""

    step_name: str = Field(
        ..., description="Step identifier: ssl, headers, ports, web_vulnerabilities, report"
    )
    step_status: StepStatus
    step_progress: int | None = Field(None, ge=0, le=100, description="Progress percentage (0-100)")
    step_message: str | None = Field(None, description="Optional status message")
    step_error: str | None = Field(None, description="Error message if failed")
    started_at: str | None = Field(None, description="ISO datetime when step started")
    completed_at: str | None = Field(None, description="ISO datetime when step completed")


class ScanProgressResponse(BaseModel):
    """Scan progress response"""

    audit_id: str
    overall_status: AuditStatus = Field(..., description="Overall audit status")
    steps: list[ScanProgressStep] = Field(..., description="List of scan steps with progress")
    overall_progress: int = Field(..., ge=0, le=100, description="Overall progress percentage")


# ─────────────────────────────────────────────────────────
# Audit Log Schemas
# ─────────────────────────────────────────────────────────


AuditLogAction = Literal[
    "api_key.created",
    "api_key.revoked",
    "api_key.rotated",
    "auth.success",
    "auth.failure",
    "auth.rate_limited",
    "organization.created",
    "organization.updated",
    "plan.changed",
    "settings.updated",
    "notification.created",
    "notification.updated",
    "notification.deleted",
    "payment.initiated",
    "payment.completed",
    "payment.failed",
    "subscription.created",
    "subscription.cancelled",
    "admin.access",
    "admin.action",
    "data.export",
    "data.sensitive_access",
]

AuditLogStatus = Literal["success", "failure", "denied", "pending"]
ActorType = Literal["user", "api_key", "system", "anonymous", "webhook"]


class AuditLogEntry(BaseModel):
    """Single audit log entry"""

    id: int = Field(..., description="Unique log entry ID")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the event")
    action: str = Field(..., description="Action type (e.g., api_key.created)")
    actor_type: ActorType = Field(
        ..., description="Type of actor (user, api_key, system, anonymous)"
    )
    actor_id: str | None = Field(None, description="ID of the actor (API key ID, user ID)")
    actor_ip: str | None = Field(None, description="IP address of the actor")
    resource_type: str = Field(..., description="Type of resource affected")
    resource_id: str | None = Field(None, description="ID of the affected resource")
    org_id: int | None = Field(None, description="Organization ID context")
    details: dict[str, Any] | None = Field(None, description="Action-specific details")
    status: AuditLogStatus = Field(..., description="Result status (success, failure, denied)")
    error_message: str | None = Field(None, description="Error message if failed")
    request_id: str | None = Field(None, description="Request correlation ID")
    request_path: str | None = Field(None, description="API endpoint path")
    request_method: str | None = Field(None, description="HTTP method")


class AuditLogListResponse(BaseModel):
    """Audit log list response with pagination"""

    items: list[AuditLogEntry] = Field(..., description="List of audit log entries")
    total: int = Field(..., description="Total number of matching entries")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more results exist")
