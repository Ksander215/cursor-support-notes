from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


AuditMode = Literal["safe", "normal", "full"]
AuditStatus = Literal["queued", "running", "completed", "failed"]


class AuditCreateRequest(BaseModel):
    target: str = Field(..., description="Domain, IPv4, or URL to audit")
    mode: AuditMode = Field("safe", description="Audit depth")


class AuditCreateResponse(BaseModel):
    audit_id: str
    status: AuditStatus


class AuditSummary(BaseModel):
    id: str
    target: str
    mode: AuditMode
    status: AuditStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    overall_score: Optional[float] = None
    risk_level: Optional[str] = None
    error: Optional[str] = None


class AuditDetails(AuditSummary):
    result: Optional[Dict[str, Any]] = None
    report_md: Optional[str] = None


class AuditListResponse(BaseModel):
    items: List[AuditSummary]


class AdminApiKeyCreateRequest(BaseModel):
    """
    Minimal bootstrap to issue an API key.
    Intended for early-stage MVP. Later we can replace with full user/org flows.
    """

    org_name: str = Field(..., min_length=2, max_length=80)
    key_name: Optional[str] = Field(None, max_length=120)
    is_admin: bool = Field(False, description="Admin key can manage other keys (future use)")

    # Optional plan controls (if plan doesn't exist, it will be created/updated)
    plan_code: str = Field("free", min_length=2, max_length=32)
    plan_name: str = Field("Free", min_length=2, max_length=64)
    requests_per_minute: Optional[int] = Field(None, ge=1, le=10000)
    monthly_audits_quota: Optional[int] = Field(None, ge=1, le=1_000_000)
    concurrency_limit: Optional[int] = Field(None, ge=1, le=1000)


class AdminApiKeyCreateResponse(BaseModel):
    api_key: str = Field(..., description="Plain API key. Shown ONCE. Store securely.")
    api_key_id: str
    prefix: str
    last4: str
    org_id: int
    org_name: str
    plan_code: str


class QuotaLimits(BaseModel):
    """Plan limits (None means unlimited)"""
    requests_per_minute: Optional[int] = None
    monthly_audits_quota: Optional[int] = None
    concurrency_limit: Optional[int] = None


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
    risk_level: Optional[str] = None


class AuditHistoryResponse(BaseModel):
    """History of audits for a target"""
    target: str
    items: List[AuditHistoryItem]


class CIContext(BaseModel):
    """CI/CD context information"""
    provider: str = Field(..., description="CI provider: github, gitlab, azure")
    repo: Optional[str] = Field(None, description="Repository identifier")
    commit: Optional[str] = Field(None, description="Commit SHA")
    branch: Optional[str] = Field(None, description="Branch name")
    pull_request: Optional[str] = Field(None, description="Pull request number")


class CIScanRequest(BaseModel):
    """Request for CI/CD security scan"""
    target: str = Field(..., description="Domain, IPv4, or URL to audit")
    mode: AuditMode = Field("safe", description="Audit depth")
    fail_on: List[str] = Field(
        default=["critical"],
        description="Risk levels that should cause CI failure: critical, high, medium, low, or score threshold (e.g., 'score<60')"
    )
    wait: bool = Field(
        True,
        description="Wait for scan completion (synchronous mode). If false, returns audit_id immediately."
    )
    timeout: Optional[int] = Field(
        300,
        ge=30,
        le=1800,
        description="Maximum wait time in seconds (only used if wait=true)"
    )
    ci_context: Optional[CIContext] = Field(None, description="CI/CD context information")


class CIScanResponse(BaseModel):
    """Response from CI/CD scan"""
    audit_id: str
    status: AuditStatus
    passed: bool = Field(..., description="Whether scan passed CI checks")
    overall_score: Optional[float] = None
    risk_level: Optional[str] = None
    critical_issues_count: int = Field(0, ge=0)
    failure_reason: Optional[str] = Field(None, description="Reason for failure if passed=false")
    report_url: Optional[str] = Field(None, description="URL to view full report")


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
    events: List[NotificationEvent] = Field(..., min_length=1)
    enabled: bool = Field(True)
    config: Dict[str, Any] = Field(..., description="Channel-specific configuration")


class NotificationSettingsUpdate(BaseModel):
    """Request to update notification settings"""
    events: Optional[List[NotificationEvent]] = None
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


class NotificationSettingsResponse(BaseModel):
    """Notification settings response"""
    id: int
    org_id: int
    channel: NotificationChannel
    events: List[NotificationEvent]
    enabled: bool
    config: Dict[str, Any]
    created_at: str
    updated_at: str


StepStatus = Literal["pending", "running", "completed", "failed"]


class ScanProgressStep(BaseModel):
    """Single step in scan progress"""
    step_name: str = Field(..., description="Step identifier: ssl, headers, ports, web_vulnerabilities, report")
    step_status: StepStatus
    step_progress: Optional[int] = Field(None, ge=0, le=100, description="Progress percentage (0-100)")
    step_message: Optional[str] = Field(None, description="Optional status message")
    step_error: Optional[str] = Field(None, description="Error message if failed")
    started_at: Optional[str] = Field(None, description="ISO datetime when step started")
    completed_at: Optional[str] = Field(None, description="ISO datetime when step completed")


class ScanProgressResponse(BaseModel):
    """Scan progress response"""
    audit_id: str
    overall_status: AuditStatus = Field(..., description="Overall audit status")
    steps: List[ScanProgressStep] = Field(..., description="List of scan steps with progress")
    overall_progress: int = Field(..., ge=0, le=100, description="Overall progress percentage")

