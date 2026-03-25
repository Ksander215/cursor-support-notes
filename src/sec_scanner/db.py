import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    ApiKey,
    Audit,
    AuditLog,
    Base,
    DigitalOrder,
    Lead,
    NotificationSettings,
    Organization,
    Payment,
    Plan,
    Referral,
    ScanProgress,
    UsageBucket,
    Webhook,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


_ENGINE: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_database_url() -> tuple[str, bool]:
    """
    Returns (database_url, is_sqlite).
    Supports:
    - SEC_SCANNER_DATABASE_URL (preferred)
    - SEC_SCANNER_DB_PATH (legacy sqlite path)
    """
    url = os.getenv("SEC_SCANNER_DATABASE_URL", "").strip()
    if url:
        return url, url.startswith("sqlite")

    db_path = os.getenv("SEC_SCANNER_DB_PATH", os.path.join("data", "sec_scanner.db"))
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    # absolute path => 4 slashes
    if db_path.startswith("/"):
        return f"sqlite:////{db_path.lstrip('/')}", True
    return f"sqlite:///{db_path}", True


def get_engine() -> Engine:
    global _ENGINE, _SessionLocal
    if _ENGINE is None:
        url, _is_sqlite = get_database_url()
        connect_args = {"check_same_thread": False} if _is_sqlite else {}
        _ENGINE = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        _SessionLocal = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)
    return _ENGINE


def get_session() -> Session:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def init_db() -> None:
    """
    IMPORTANT:
    - For Postgres in production, schema should be managed by Alembic migrations.
    - For SQLite/dev, we can auto-create tables.
    """
    _url, is_sqlite = get_database_url()
    if is_sqlite and os.getenv("SEC_SCANNER_AUTO_CREATE_SCHEMA", "true").lower() in (
        "1",
        "true",
        "yes",
    ):
        engine = get_engine()
        Base.metadata.create_all(bind=engine)


def create_audit(
    target: str,
    mode: str,
    *,
    tenant_id: int | None = None,
    created_by_api_key_id: str | None = None,
    is_guest: bool = False,
) -> str:
    audit_id = str(uuid.uuid4())
    with get_session() as s:
        s.add(
            Audit(
                id=audit_id,
                tenant_id=tenant_id,
                created_by_api_key_id=created_by_api_key_id,
                target=target,
                mode=mode,
                status="queued",
                is_guest=is_guest,
            )
        )
        s.commit()
    return audit_id


def set_audit_saas_context(
    audit_id: str, *, tenant_id: int | None, created_by_api_key_id: str | None
) -> None:
    with get_session() as s:
        a = s.get(Audit, audit_id)
        if not a:
            return
        a.tenant_id = tenant_id
        a.created_by_api_key_id = created_by_api_key_id
        s.commit()


def upsert_plan(
    *,
    code: str,
    name: str,
    requests_per_minute: int | None,
    monthly_audits_quota: int | None,
    concurrency_limit: int | None,
) -> int:
    """
    Create or update plan by code.
    Returns plan_id.
    """
    with get_session() as s:
        p = s.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
        if p is None:
            p = Plan(
                code=code,
                name=name,
                requests_per_minute=requests_per_minute,
                monthly_audits_quota=monthly_audits_quota,
                concurrency_limit=concurrency_limit,
            )
            s.add(p)
            s.commit()
            s.refresh(p)
            return int(p.id)

        # Update mutable fields (keep existing when input is None)
        p.name = name or p.name
        if requests_per_minute is not None:
            p.requests_per_minute = requests_per_minute
        if monthly_audits_quota is not None:
            p.monthly_audits_quota = monthly_audits_quota
        if concurrency_limit is not None:
            p.concurrency_limit = concurrency_limit
        s.commit()
        return int(p.id)


def get_or_create_org(*, name: str, plan_id: int) -> int:
    with get_session() as s:
        org = s.execute(select(Organization).where(Organization.name == name)).scalar_one_or_none()
        if org is None:
            org = Organization(name=name, plan_id=plan_id)
            s.add(org)
            s.commit()
            s.refresh(org)
        return int(org.id)


def get_org_by_id(org_id: int) -> dict[str, Any] | None:
    """Get organization by ID"""
    with get_session() as s:
        org = s.get(Organization, org_id)
        if not org:
            return None
        return {
            "id": org.id,
            "name": org.name,
            "plan_id": org.plan_id,
            "is_active": org.is_active,
            "white_label_config": org.white_label_config
            if hasattr(org, "white_label_config")
            else None,
        }


def get_plan_by_code(plan_code: str) -> dict[str, Any] | None:
    """Get plan by code"""
    with get_session() as s:
        plan = s.execute(select(Plan).where(Plan.code == plan_code)).scalar_one_or_none()
        if not plan:
            return None
        return {
            "id": plan.id,
            "code": plan.code,
            "name": plan.name,
            "requests_per_minute": plan.requests_per_minute,
            "monthly_audits_quota": plan.monthly_audits_quota,
            "concurrency_limit": plan.concurrency_limit,
        }


def update_org_plan(org_id: int, plan_id: int) -> None:
    """Update organization's plan"""
    with get_session() as s:
        org = s.get(Organization, org_id)
        if not org:
            raise ValueError(f"Organization {org_id} not found")
        org.plan_id = plan_id
        s.commit()


def update_org_whitelabel_config(org_id: int, config: dict[str, Any]) -> None:
    """Update organization's white-label configuration"""
    with get_session() as s:
        org = s.get(Organization, org_id)
        if not org:
            raise ValueError(f"Organization {org_id} not found")
        org.white_label_config = config
        s.commit()


def insert_api_key(
    *,
    api_key_id: str,
    org_id: int,
    name: str | None,
    prefix: str,
    last4: str,
    hashed_key: str,
    is_admin: bool,
) -> None:
    with get_session() as s:
        s.add(
            ApiKey(
                id=api_key_id,
                org_id=org_id,
                name=name,
                prefix=prefix,
                last4=last4,
                hashed_key=hashed_key,
                is_admin=bool(is_admin),
                is_active=True,
            )
        )
        s.commit()


def get_api_keys_by_org(org_id: int) -> list[dict[str, Any]]:
    """Get list of API keys for an organization (metadata only, no plain keys)."""
    with get_session() as s:
        keys = (
            s.execute(
                select(ApiKey)
                .where(ApiKey.org_id == org_id)
                .where(ApiKey.is_active.is_(True))
                .where(ApiKey.revoked_at.is_(None))
                .order_by(ApiKey.created_at.desc())
            )
            .scalars()
            .all()
        )

        return [
            {
                "id": key.id,
                "name": key.name,
                "prefix": key.prefix,
                "last4": key.last4,
                "is_admin": bool(key.is_admin),
                "created_at": key.created_at.isoformat() if key.created_at else None,
            }
            for key in keys
        ]


def revoke_api_key(api_key_id: str, org_id: int) -> bool:
    """Revoke an API key. Returns True if revoked, False if not found or already revoked."""
    with get_session() as s:
        key = s.get(ApiKey, api_key_id)
        if not key or key.org_id != org_id or key.revoked_at is not None:
            return False
        key.revoked_at = datetime.now(UTC)
        s.commit()
        return True


def mark_started(audit_id: str) -> None:
    with get_session() as s:
        a = s.get(Audit, audit_id)
        if not a:
            return
        a.status = "running"
        a.started_at = datetime.now(UTC)
        s.commit()


def mark_completed(
    audit_id: str,
    *,
    overall_score: float | None,
    risk_level: str | None,
    result: dict[str, Any],
    report_md: str | None,
) -> None:
    with get_session() as s:
        a = s.get(Audit, audit_id)
        if not a:
            return
        a.status = "completed"
        a.completed_at = datetime.now(UTC)
        a.overall_score = overall_score
        a.risk_level = risk_level
        a.result_json = result
        a.report_md = report_md
        a.error = None
        s.commit()


def mark_failed(audit_id: str, error: str) -> None:
    with get_session() as s:
        a = s.get(Audit, audit_id)
        if not a:
            return
        a.status = "failed"
        a.completed_at = datetime.now(UTC)
        a.error = error
        s.commit()


def get_audit(audit_id: str) -> dict[str, Any] | None:
    with get_session() as s:
        a = s.get(Audit, audit_id)
        if not a:
            return None
        return _audit_to_dict(a)


def list_audits(
    limit: int = 50,
    *,
    tenant_id: int | None = None,
    include_total: bool = False,
    status: str | None = None,
    target: str | None = None,
    mode: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[dict[str, Any]], bool, int | None]:
    """
    List audits with pagination metadata, filtering, and sorting.

    Args:
        limit: Maximum number of items to return
        tenant_id: Filter by tenant/organization ID
        include_total: Include total count in response
        status: Filter by status (queued, running, completed, failed)
        target: Filter by target (partial match, case-insensitive)
        mode: Filter by mode (safe, normal, full)
        sort: Field to sort by (created_at, completed_at, overall_score, target)
        order: Sort order (asc, desc)

    Returns:
        (items, has_more, total_count)
        - items: List of audit dictionaries
        - has_more: True if there are more items beyond the limit
        - total_count: Total count (if include_total=True), None otherwise
    """
    lim = max(1, min(limit, 200))

    # Validate sort field
    valid_sort_fields = {"created_at", "completed_at", "overall_score", "target"}
    if sort not in valid_sort_fields:
        sort = "created_at"

    # Validate order
    order_lower = order.lower()
    if order_lower not in {"asc", "desc"}:
        order_lower = "desc"

    with get_session() as s:
        base_query = select(Audit)

        # Apply filters
        if tenant_id is not None:
            base_query = base_query.where(Audit.tenant_id == tenant_id)

        if status:
            base_query = base_query.where(Audit.status == status)

        if target:
            # Case-insensitive partial match
            base_query = base_query.where(Audit.target.ilike(f"%{target}%"))

        if mode:
            base_query = base_query.where(Audit.mode == mode)

        # Apply sorting
        sort_column = getattr(Audit, sort, Audit.created_at)
        if order_lower == "asc":
            order_by = sort_column.asc()
        else:
            order_by = sort_column.desc()

        # Get one extra item to check if there are more
        query = base_query.order_by(order_by).limit(lim + 1)
        rows = list(s.execute(query).scalars())

        # Check if there are more items
        has_more = len(rows) > lim
        items = rows[:lim]  # Take only requested limit

        # Calculate total if requested (can be expensive for large tables)
        total_count: int | None = None
        if include_total:
            count_query = select(func.count()).select_from(base_query.subquery())
            total_count = s.execute(count_query).scalar() or 0

        return ([_audit_to_dict(a) for a in items], has_more, total_count)


def get_audit_history(
    target: str, limit: int = 50, *, tenant_id: int | None = None
) -> list[dict[str, Any]]:
    """
    Get historical audits for a specific target, ordered by completion time (most recent first).
    Only returns completed audits with overall_score.
    """
    lim = max(1, min(limit, 200))
    with get_session() as s:
        q = (
            select(Audit)
            .where(Audit.target == target)
            .where(Audit.status == "completed")
            .where(Audit.overall_score.isnot(None))
        )
        if tenant_id is not None:
            q = q.where(Audit.tenant_id == tenant_id)
        rows = s.execute(q.order_by(Audit.completed_at.desc()).limit(lim)).scalars()
        return [_audit_to_dict(a) for a in rows]


def _audit_to_dict(a: Audit) -> dict[str, Any]:
    return {
        "id": a.id,
        "tenant_id": getattr(a, "tenant_id", None),
        "created_by_api_key_id": getattr(a, "created_by_api_key_id", None),
        "target": a.target,
        "mode": a.mode,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else _utc_now_iso(),
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "overall_score": a.overall_score,
        "risk_level": a.risk_level,
        "result_json": a.result_json,
        "report_md": a.report_md,
        "error": a.error,
    }


def get_api_key_context_by_hash(hashed_key: str) -> dict[str, Any] | None:
    """
    Returns a dict used by SaaS auth middleware (ApiKey + Organization + Plan flattened).
    """
    with get_session() as s:
        row = s.execute(
            select(ApiKey, Organization, Plan)
            .join(Organization, ApiKey.org_id == Organization.id)
            .join(Plan, Organization.plan_id == Plan.id)
            .where(ApiKey.hashed_key == hashed_key)
            .where(ApiKey.is_active.is_(True))
            .where(ApiKey.revoked_at.is_(None))
            .where(Organization.is_active.is_(True))
        ).first()
        if not row:
            return None

        api_key, org, plan = row
        return {
            "org_id": org.id,
            "tenant_id": org.id,
            "api_key_id": api_key.id,
            "api_key_prefix": api_key.prefix,
            "plan_code": plan.code,
            "requests_per_minute": plan.requests_per_minute,
            "monthly_audits_quota": plan.monthly_audits_quota,
            "concurrency_limit": plan.concurrency_limit,
            "is_admin": bool(api_key.is_admin),
        }


def increment_usage(
    *,
    org_id: int,
    api_key_id: str,
    metric: str,
    bucket_start: datetime,
    amount: int = 1,
) -> None:
    """
    Atomic upsert increment for usage buckets.
    Works for both SQLite and Postgres (via dialect-specific INSERT).
    """
    amount = int(amount)
    if amount == 0:
        return

    with get_session() as s:
        dialect = s.bind.dialect.name if s.bind is not None else ""
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            from sqlalchemy import insert as dialect_insert

        stmt = dialect_insert(UsageBucket).values(
            org_id=org_id,
            api_key_id=api_key_id,
            metric=metric,
            bucket_start=bucket_start,
            count=amount,
            updated_at=func.now(),
        )

        # Unique(org_id, api_key_id, metric, bucket_start)
        stmt = stmt.on_conflict_do_update(
            index_elements=["org_id", "api_key_id", "metric", "bucket_start"],
            set_={
                "count": UsageBucket.count + amount,
                "updated_at": func.now(),
            },
        )
        s.execute(stmt)
        s.commit()


def get_usage_sum_for_month(*, org_id: int, metric: str, bucket_start: datetime) -> int:
    with get_session() as s:
        total = s.execute(
            select(func.coalesce(func.sum(UsageBucket.count), 0))
            .where(UsageBucket.org_id == org_id)
            .where(UsageBucket.metric == metric)
            .where(UsageBucket.bucket_start == bucket_start)
        ).scalar_one()
        return int(total or 0)


def get_quota_info(*, tenant_id: int) -> dict[str, Any] | None:
    """
    Returns quota information for an organization:
    - Plan limits (requests_per_minute, monthly_audits_quota, concurrency_limit)
    - Current usage for current month (requests, audits_created)
    """
    with get_session() as s:
        org = s.get(Organization, tenant_id)
        if not org:
            return None

        plan = s.get(Plan, org.plan_id)
        if not plan:
            return None

        # Get current month bucket start (UTC)
        now = datetime.now(UTC)
        month_start = datetime(now.year, now.month, 1, tzinfo=UTC)

        # Get usage for current month
        requests_used = get_usage_sum_for_month(
            org_id=tenant_id, metric="requests", bucket_start=month_start
        )
        audits_used = get_usage_sum_for_month(
            org_id=tenant_id, metric="audits_created", bucket_start=month_start
        )

        return {
            "org_id": org.id,
            "org_name": org.name,
            "plan_code": plan.code,
            "plan_name": plan.name,
            "limits": {
                "requests_per_minute": plan.requests_per_minute,
                "monthly_audits_quota": plan.monthly_audits_quota,
                "concurrency_limit": plan.concurrency_limit,
            },
            "usage": {
                "requests": requests_used,
                "audits_created": audits_used,
                "month_start": month_start.isoformat(),
            },
        }


def count_running_audits(*, tenant_id: int) -> int:
    """Count running/queued audits for an organization."""
    with get_session() as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.tenant_id == tenant_id)
                .where(Audit.status.in_(["queued", "running"]))
            )
            or 0
        )


def get_notification_settings(*, org_id: int) -> list[dict[str, Any]]:
    """Get all notification settings for an organization"""
    with get_session() as s:
        rows = s.execute(
            select(NotificationSettings).where(NotificationSettings.org_id == org_id)
        ).scalars()
        return [
            {
                "id": ns.id,
                "org_id": ns.org_id,
                "channel": ns.channel,
                "events": ns.events or [],
                "enabled": ns.enabled,
                "config": ns.config or {},
            }
            for ns in rows
        ]


def create_notification_settings(
    *,
    org_id: int,
    channel: str,
    events: list[str],
    enabled: bool,
    config: dict[str, Any],
) -> int:
    """Create or update notification settings (upsert by org_id + channel)"""
    with get_session() as s:
        existing = (
            s.execute(
                select(NotificationSettings).where(
                    NotificationSettings.org_id == org_id,
                    NotificationSettings.channel == channel,
                )
            )
            .scalars()
            .first()
        )

        if existing:
            existing.events = events
            existing.enabled = enabled
            existing.config = config
            existing.updated_at = datetime.now(UTC)
            s.commit()
            return existing.id
        else:
            ns = NotificationSettings(
                org_id=org_id,
                channel=channel,
                events=events,
                enabled=enabled,
                config=config,
            )
            s.add(ns)
            s.commit()
            return ns.id


def update_notification_settings(
    *,
    settings_id: int,
    events: list[str] | None = None,
    enabled: bool | None = None,
    config: dict[str, Any] | None = None,
) -> None:
    """Update notification settings"""
    with get_session() as s:
        ns = s.get(NotificationSettings, settings_id)
        if not ns:
            return

        if events is not None:
            ns.events = events
        if enabled is not None:
            ns.enabled = enabled
        if config is not None:
            ns.config = config
        ns.updated_at = datetime.now(UTC)
        s.commit()


def delete_notification_settings(*, settings_id: int) -> None:
    """Delete notification settings"""
    with get_session() as s:
        ns = s.get(NotificationSettings, settings_id)
        if ns:
            s.delete(ns)
            s.commit()


# Scan Progress functions


def create_scan_progress(
    *,
    audit_id: str,
    step_name: str,
    step_status: str = "pending",
    step_progress: int | None = None,
    step_message: str | None = None,
) -> int:
    """Create or update scan progress step"""
    with get_session() as s:
        existing = (
            s.execute(
                select(ScanProgress).where(
                    ScanProgress.audit_id == audit_id,
                    ScanProgress.step_name == step_name,
                )
            )
            .scalars()
            .first()
        )

        if existing:
            existing.step_status = step_status
            if step_progress is not None:
                existing.step_progress = step_progress
            if step_message is not None:
                existing.step_message = step_message
            if step_status == "running" and existing.started_at is None:
                existing.started_at = datetime.now(UTC)
            if step_status in ("completed", "failed"):
                existing.completed_at = datetime.now(UTC)
            existing.updated_at = datetime.now(UTC)
            s.commit()
            return existing.id
        else:
            sp = ScanProgress(
                audit_id=audit_id,
                step_name=step_name,
                step_status=step_status,
                step_progress=step_progress,
                step_message=step_message,
                started_at=datetime.now(UTC) if step_status == "running" else None,
                completed_at=datetime.now(UTC) if step_status in ("completed", "failed") else None,
            )
            s.add(sp)
            s.commit()
            return sp.id


def update_scan_progress_step(
    *,
    audit_id: str,
    step_name: str,
    step_status: str | None = None,
    step_progress: int | None = None,
    step_message: str | None = None,
    step_error: str | None = None,
) -> None:
    """Update scan progress step"""
    with get_session() as s:
        sp = (
            s.execute(
                select(ScanProgress).where(
                    ScanProgress.audit_id == audit_id,
                    ScanProgress.step_name == step_name,
                )
            )
            .scalars()
            .first()
        )

        if not sp:
            return

        if step_status is not None:
            sp.step_status = step_status
            if step_status == "running" and sp.started_at is None:
                sp.started_at = datetime.now(UTC)
            if step_status in ("completed", "failed"):
                sp.completed_at = datetime.now(UTC)
        if step_progress is not None:
            sp.step_progress = step_progress
        if step_message is not None:
            sp.step_message = step_message
        if step_error is not None:
            sp.step_error = step_error
        sp.updated_at = datetime.now(UTC)
        s.commit()


def get_scan_progress(audit_id: str) -> list[dict[str, Any]]:
    """Get all progress steps for an audit"""
    with get_session() as s:
        steps = (
            s.execute(
                select(ScanProgress)
                .where(ScanProgress.audit_id == audit_id)
                .order_by(ScanProgress.created_at)
            )
            .scalars()
            .all()
        )
        return [
            {
                "step_name": sp.step_name,
                "step_status": sp.step_status,
                "step_progress": sp.step_progress,
                "step_message": sp.step_message,
                "step_error": sp.step_error,
                "started_at": sp.started_at.isoformat() if sp.started_at else None,
                "completed_at": sp.completed_at.isoformat() if sp.completed_at else None,
            }
            for sp in steps
        ]


# ─────────────────────────────────────────────────────────
# Audit Log Functions
# ─────────────────────────────────────────────────────────


def insert_audit_log(log_data: dict[str, Any]) -> int:
    """
    Insert an audit log entry.

    Args:
        log_data: Dictionary with audit log fields

    Returns:
        The ID of the created audit log entry
    """
    with get_session() as s:
        log_entry = AuditLog(
            timestamp=log_data.get("timestamp"),
            action=log_data["action"],
            actor_type=log_data["actor_type"],
            actor_id=log_data.get("actor_id"),
            actor_ip=log_data.get("actor_ip"),
            actor_user_agent=log_data.get("actor_user_agent"),
            resource_type=log_data["resource_type"],
            resource_id=log_data.get("resource_id"),
            org_id=log_data.get("org_id"),
            details=log_data.get("details"),
            status=log_data["status"],
            error_message=log_data.get("error_message"),
            request_id=log_data.get("request_id"),
            request_path=log_data.get("request_path"),
            request_method=log_data.get("request_method"),
        )
        s.add(log_entry)
        s.commit()
        s.refresh(log_entry)
        return log_entry.id


def get_audit_logs(
    *,
    org_id: int | None = None,
    action: str | None = None,
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    Query audit logs with filters.

    Args:
        org_id: Filter by organization ID
        action: Filter by action type
        actor_id: Filter by actor ID
        resource_type: Filter by resource type
        resource_id: Filter by resource ID
        status: Filter by status
        from_timestamp: Filter by timestamp (from)
        to_timestamp: Filter by timestamp (to)
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        Tuple of (list of audit logs, total count)
    """
    with get_session() as s:
        # Build query
        query = select(AuditLog)
        count_query = select(func.count()).select_from(AuditLog)

        # Apply filters
        if org_id is not None:
            query = query.where(AuditLog.org_id == org_id)
            count_query = count_query.where(AuditLog.org_id == org_id)
        if action is not None:
            query = query.where(AuditLog.action == action)
            count_query = count_query.where(AuditLog.action == action)
        if actor_id is not None:
            query = query.where(AuditLog.actor_id == actor_id)
            count_query = count_query.where(AuditLog.actor_id == actor_id)
        if resource_type is not None:
            query = query.where(AuditLog.resource_type == resource_type)
            count_query = count_query.where(AuditLog.resource_type == resource_type)
        if resource_id is not None:
            query = query.where(AuditLog.resource_id == resource_id)
            count_query = count_query.where(AuditLog.resource_id == resource_id)
        if status is not None:
            query = query.where(AuditLog.status == status)
            count_query = count_query.where(AuditLog.status == status)
        if from_timestamp is not None:
            query = query.where(AuditLog.timestamp >= from_timestamp)
            count_query = count_query.where(AuditLog.timestamp >= from_timestamp)
        if to_timestamp is not None:
            query = query.where(AuditLog.timestamp <= to_timestamp)
            count_query = count_query.where(AuditLog.timestamp <= to_timestamp)

        # Get total count
        total = s.execute(count_query).scalar() or 0

        # Apply ordering and pagination
        query = query.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)

        # Execute query
        logs = s.execute(query).scalars().all()

        return [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "action": log.action,
                "actor_type": log.actor_type,
                "actor_id": log.actor_id,
                "actor_ip": log.actor_ip,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "org_id": log.org_id,
                "details": log.details,
                "status": log.status,
                "error_message": log.error_message,
                "request_id": log.request_id,
                "request_path": log.request_path,
                "request_method": log.request_method,
            }
            for log in logs
        ], total


def get_payment_by_provider_id(provider: str, payment_id: str) -> dict[str, Any] | None:
    """
    Get payment record by provider and payment ID (for idempotency check).

    Args:
        provider: Payment provider name ("yookassa", "stripe")
        payment_id: Payment ID from provider

    Returns:
        Payment record dict or None if not found
    """
    with get_session() as s:
        payment = s.scalar(
            select(Payment).where(Payment.provider == provider, Payment.payment_id == payment_id)
        )
        if not payment:
            return None
        return {
            "id": payment.id,
            "provider": payment.provider,
            "payment_id": payment.payment_id,
            "org_id": payment.org_id,
            "plan_code": payment.plan_code,
            "amount": payment.amount,
            "currency": payment.currency,
            "status": payment.status,
            "event_type": payment.event_type,
            "payment_metadata": payment.payment_metadata,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
            "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
        }


def create_payment_record(
    provider: str,
    payment_id: str,
    org_id: int,
    *,
    plan_code: str | None = None,
    amount: float | None = None,
    currency: str = "RUB",
    status: str = "pending",
    event_type: str = "payment.created",
    payment_metadata: dict[str, Any] | None = None,
) -> int:
    """
    Create a payment record for idempotency tracking.

    Args:
        provider: Payment provider name ("yookassa", "stripe")
        payment_id: Payment ID from provider
        org_id: Organization ID
        plan_code: Plan code if subscription payment
        amount: Payment amount
        currency: Currency code (default: "RUB")
        status: Payment status (default: "pending")
        event_type: Webhook event type
        payment_metadata: Additional payment metadata

    Returns:
        The ID of the created payment record
    """
    with get_session() as s:
        payment = Payment(
            provider=provider,
            payment_id=payment_id,
            org_id=org_id,
            plan_code=plan_code,
            amount=amount,
            currency=currency,
            status=status,
            event_type=event_type,
            payment_metadata=payment_metadata,
            processed_at=datetime.now(UTC),
        )
        s.add(payment)
        s.commit()
        s.refresh(payment)
        return payment.id


def update_payment_status(
    provider: str,
    payment_id: str,
    status: str,
    *,
    event_type: str | None = None,
    payment_metadata: dict[str, Any] | None = None,
) -> bool:
    """
    Update payment status (for webhook processing).

    Args:
        provider: Payment provider name
        payment_id: Payment ID from provider
        status: New status
        event_type: Optional event type
        payment_metadata: Optional metadata to update

    Returns:
        True if updated, False if payment not found
    """
    with get_session() as s:
        payment = s.scalar(
            select(Payment).where(Payment.provider == provider, Payment.payment_id == payment_id)
        )
        if not payment:
            return False
        payment.status = status
        payment.processed_at = datetime.now(UTC)
        if event_type:
            payment.event_type = event_type
        if payment_metadata:
            if payment.payment_metadata:
                payment.payment_metadata.update(payment_metadata)
            else:
                payment.payment_metadata = payment_metadata
        s.commit()
        return True


# ============================================================================
# Реферальная система
# ============================================================================

import secrets
import string


def generate_referral_code() -> str:
    """Генерирует уникальный реферальный код (8 символов, буквы и цифры)."""
    alphabet = string.ascii_uppercase + string.digits
    with get_session() as s:
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            # Проверяем уникальность
            exists = s.scalar(select(Organization).filter(Organization.referral_code == code))
            if not exists:
                return code


def set_referral_code(org_id: int) -> str:
    """Устанавливает реферальный код для организации. Возвращает код."""
    with get_session() as s:
        org = s.scalar(select(Organization).filter(Organization.id == org_id))
        if not org:
            raise ValueError(f"Organization {org_id} not found")

        if org.referral_code:
            return org.referral_code  # Уже есть код

        code = generate_referral_code()
        org.referral_code = code
        s.commit()
        return code


def get_referral_code(org_id: int) -> str | None:
    """Получает реферальный код организации."""
    with get_session() as s:
        org = s.scalar(select(Organization).filter(Organization.id == org_id))
        return org.referral_code if org else None


def register_referral(client_org_id: int, referral_code: str) -> bool:
    """Регистрирует реферала по коду. Возвращает True если успешно."""
    with get_session() as s:
        # Находим партнёра по коду
        partner_org = s.scalar(
            select(Organization).filter(Organization.referral_code == referral_code)
        )

        if not partner_org:
            return False

        # Проверяем, что клиент ещё не был зарегистрирован
        client_org = s.scalar(select(Organization).filter(Organization.id == client_org_id))

        if not client_org or client_org.referred_by_org_id:
            return False  # Уже зарегистрирован или не найден

        # Регистрируем реферала
        client_org.referred_by_org_id = partner_org.id
        s.commit()
        return True


def calculate_referral_commission(payment_id: int, payment_amount: float, plan_code: str) -> None:
    """Рассчитывает и создаёт запись о комиссии для реферала."""
    with get_session() as s:
        # Находим платеж
        payment = s.scalar(select(Payment).filter(Payment.id == payment_id))
        if not payment:
            return

        # Находим организацию клиента
        client_org = s.scalar(select(Organization).filter(Organization.id == payment.org_id))

        if not client_org or not client_org.referred_by_org_id:
            return  # Нет реферала

        # Проверяем, не была ли уже создана запись о комиссии для этого платежа
        existing = s.scalar(select(Referral).filter(Referral.payment_id == payment_id))
        if existing:
            return  # Уже создана

        # Рассчитываем комиссию (20% от первого платежа)
        commission_percent = 20.0
        commission_amount = payment_amount * (commission_percent / 100.0)

        # Создаём запись о комиссии
        referral = Referral(
            partner_org_id=client_org.referred_by_org_id,
            client_org_id=client_org.id,
            payment_id=payment_id,
            commission_amount=commission_amount,
            commission_percent=commission_percent,
            payment_amount=payment_amount,
            plan_code=plan_code,
            status="pending",
        )
        s.add(referral)
        s.commit()


def get_referral_stats(org_id: int) -> dict[str, Any]:
    """Получает статистику по реферальной программе для организации."""
    with get_session() as s:
        org = s.scalar(select(Organization).filter(Organization.id == org_id))
        if not org:
            raise ValueError(f"Organization {org_id} not found")

        # Получаем реферальный код (создаём если нет)
        referral_code = org.referral_code or set_referral_code(org_id)

        # Получаем всех рефералов
        referrals = s.scalars(select(Referral).filter(Referral.partner_org_id == org_id)).all()

        # Получаем организации клиентов
        client_orgs = {}
        for ref in referrals:
            if ref.client_org_id not in client_orgs:
                client_org = s.scalar(
                    select(Organization).filter(Organization.id == ref.client_org_id)
                )
                if client_org:
                    client_orgs[ref.client_org_id] = client_org.name

        # Подсчитываем статистику
        total_referrals = len(referrals)
        active_referrals = len([r for r in referrals if r.status == "paid"])
        total_commission = sum(r.commission_amount for r in referrals)
        pending_commission = sum(r.commission_amount for r in referrals if r.status == "pending")
        paid_commission = sum(r.commission_amount for r in referrals if r.status == "paid")

        # Формируем список рефералов
        referrals_list = []
        for ref in referrals:
            referrals_list.append(
                {
                    "client_org_id": ref.client_org_id,
                    "client_name": client_orgs.get(ref.client_org_id, "Unknown"),
                    "plan_code": ref.plan_code,
                    "commission_amount": ref.commission_amount,
                    "status": ref.status,
                    "created_at": ref.created_at.isoformat() if ref.created_at else None,
                }
            )

        return {
            "referral_code": referral_code,
            "total_referrals": total_referrals,
            "active_referrals": active_referrals,
            "total_commission": total_commission,
            "pending_commission": pending_commission,
            "paid_commission": paid_commission,
            "referrals": referrals_list,
        }


# Webhooks
def create_webhook(
    *,
    org_id: int,
    url: str,
    events: list[str],
    secret: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Create a new webhook configuration."""
    with get_session() as s:
        webhook = Webhook(
            org_id=org_id,
            url=url,
            events=events,
            secret=secret,
            enabled=enabled,
        )
        s.add(webhook)
        s.commit()
        s.refresh(webhook)

        return {
            "id": webhook.id,
            "org_id": webhook.org_id,
            "url": webhook.url,
            "events": webhook.events,
            "enabled": webhook.enabled,
            "retry_count": webhook.retry_count,
            "last_delivery_at": webhook.last_delivery_at.isoformat()
            if webhook.last_delivery_at
            else None,
            "last_failure_at": webhook.last_failure_at.isoformat()
            if webhook.last_failure_at
            else None,
            "last_failure_reason": webhook.last_failure_reason,
            "created_at": webhook.created_at.isoformat(),
            "updated_at": webhook.updated_at.isoformat(),
        }


def get_webhooks(*, org_id: int) -> list[dict[str, Any]]:
    """Get all webhooks for an organization."""
    with get_session() as s:
        webhooks = s.scalars(
            select(Webhook).filter(Webhook.org_id == org_id).order_by(Webhook.created_at.desc())
        ).all()

        return [
            {
                "id": w.id,
                "org_id": w.org_id,
                "url": w.url,
                "events": w.events,
                "enabled": w.enabled,
                "retry_count": w.retry_count,
                "last_delivery_at": w.last_delivery_at.isoformat() if w.last_delivery_at else None,
                "last_failure_at": w.last_failure_at.isoformat() if w.last_failure_at else None,
                "last_failure_reason": w.last_failure_reason,
                "created_at": w.created_at.isoformat(),
                "updated_at": w.updated_at.isoformat(),
            }
            for w in webhooks
        ]


def get_webhook_by_id(*, webhook_id: int, org_id: int) -> dict[str, Any] | None:
    """Get a webhook by ID (with org_id check for security)."""
    with get_session() as s:
        webhook = s.scalar(
            select(Webhook).filter(Webhook.id == webhook_id, Webhook.org_id == org_id)
        )

        if not webhook:
            return None

        return {
            "id": webhook.id,
            "org_id": webhook.org_id,
            "url": webhook.url,
            "events": webhook.events,
            "enabled": webhook.enabled,
            "retry_count": webhook.retry_count,
            "last_delivery_at": webhook.last_delivery_at.isoformat()
            if webhook.last_delivery_at
            else None,
            "last_failure_at": webhook.last_failure_at.isoformat()
            if webhook.last_failure_at
            else None,
            "last_failure_reason": webhook.last_failure_reason,
            "created_at": webhook.created_at.isoformat(),
            "updated_at": webhook.updated_at.isoformat(),
        }


def get_webhook_by_id_internal(*, webhook_id: int) -> dict[str, Any] | None:
    """Get a webhook by ID (internal use, no org_id check)."""
    with get_session() as s:
        webhook = s.scalar(select(Webhook).filter(Webhook.id == webhook_id))

        if not webhook:
            return None

        return {
            "id": webhook.id,
            "org_id": webhook.org_id,
            "url": webhook.url,
            "events": webhook.events,
            "secret": webhook.secret,
            "enabled": webhook.enabled,
            "retry_count": webhook.retry_count,
        }


def update_webhook(
    *,
    webhook_id: int,
    org_id: int,
    url: str | None = None,
    events: list[str] | None = None,
    secret: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    """Update a webhook configuration."""
    with get_session() as s:
        webhook = s.scalar(
            select(Webhook).filter(Webhook.id == webhook_id, Webhook.org_id == org_id)
        )

        if not webhook:
            return None

        if url is not None:
            webhook.url = url
        if events is not None:
            webhook.events = events
        if secret is not None:
            webhook.secret = secret
        if enabled is not None:
            webhook.enabled = enabled

        webhook.updated_at = datetime.now(UTC)
        s.commit()
        s.refresh(webhook)

        return {
            "id": webhook.id,
            "org_id": webhook.org_id,
            "url": webhook.url,
            "events": webhook.events,
            "enabled": webhook.enabled,
            "retry_count": webhook.retry_count,
            "last_delivery_at": webhook.last_delivery_at.isoformat()
            if webhook.last_delivery_at
            else None,
            "last_failure_at": webhook.last_failure_at.isoformat()
            if webhook.last_failure_at
            else None,
            "last_failure_reason": webhook.last_failure_reason,
            "created_at": webhook.created_at.isoformat(),
            "updated_at": webhook.updated_at.isoformat(),
        }


def delete_webhook(*, webhook_id: int, org_id: int) -> bool:
    """Delete a webhook (returns True if deleted, False if not found)."""
    with get_session() as s:
        webhook = s.scalar(
            select(Webhook).filter(Webhook.id == webhook_id, Webhook.org_id == org_id)
        )

        if not webhook:
            return False

        s.delete(webhook)
        s.commit()
        return True


def get_enabled_webhooks_for_event(*, event: str) -> list[dict[str, Any]]:
    """Get all enabled webhooks that subscribe to a specific event."""
    with get_session() as s:
        # Get all enabled webhooks and filter in Python (works for both SQLite and PostgreSQL)
        webhooks = s.scalars(
            select(Webhook).filter(Webhook.enabled == True)  # noqa: E712
        ).all()

        # Filter webhooks that subscribe to this event
        matching_webhooks = [
            w for w in webhooks if isinstance(w.events, list) and event in w.events
        ]

        return [
            {
                "id": w.id,
                "org_id": w.org_id,
                "url": w.url,
                "events": w.events,
                "secret": w.secret,
                "retry_count": w.retry_count,
            }
            for w in matching_webhooks
        ]


def update_webhook_delivery_status(
    *,
    webhook_id: int,
    success: bool,
    failure_reason: str | None = None,
) -> None:
    """Update webhook delivery status (success or failure)."""
    with get_session() as s:
        webhook = s.scalar(select(Webhook).filter(Webhook.id == webhook_id))

        if not webhook:
            return

        if success:
            webhook.last_delivery_at = datetime.now(UTC)
            webhook.last_failure_at = None
            webhook.last_failure_reason = None
            webhook.retry_count = 0
        else:
            webhook.last_failure_at = datetime.now(UTC)
            webhook.last_failure_reason = failure_reason
            webhook.retry_count += 1

        webhook.updated_at = datetime.now(UTC)
        s.commit()


# ============================================================================
# Digital Orders (for digital products: PDF guides, CI/CD templates)
# ============================================================================


def create_digital_order(
    *,
    order_id: str,
    email: str,
    product_type: str,
    product_name: str,
    amount: float,
    currency: str = "RUB",
    payment_provider: str = "yookassa",
    org_id: int | None = None,
    referral_code: str | None = None,
    customer_ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """
    Create a new digital product order.

    Args:
        order_id: Unique order UUID
        email: Customer email for delivery
        product_type: Product type ("pdf_guide", "ci_templates", "audit")
        product_name: Display name of the product
        amount: Price
        currency: Currency code (default: "RUB")
        payment_provider: "yookassa" or "stripe"
        org_id: Optional organization ID
        referral_code: Optional referral code
        customer_ip: Customer IP address
        user_agent: User agent string

    Returns:
        Dictionary with order details
    """
    with get_session() as s:
        order = DigitalOrder(
            order_id=order_id,
            email=email,
            org_id=org_id,
            product_type=product_type,
            product_name=product_name,
            amount=amount,
            currency=currency,
            payment_provider=payment_provider,
            payment_status="pending",
            delivery_status="pending",
            referral_code=referral_code,
            customer_ip=customer_ip,
            user_agent=user_agent,
        )
        s.add(order)
        s.commit()
        s.refresh(order)

        return {
            "id": order.id,
            "order_id": order.order_id,
            "email": order.email,
            "org_id": order.org_id,
            "product_type": order.product_type,
            "product_name": order.product_name,
            "amount": order.amount,
            "currency": order.currency,
            "payment_provider": order.payment_provider,
            "payment_status": order.payment_status,
            "delivery_status": order.delivery_status,
            "referral_code": order.referral_code,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }


def get_digital_order_by_id(order_id: str) -> dict[str, Any] | None:
    """Get digital order by order_id (UUID)."""
    with get_session() as s:
        order = s.scalar(select(DigitalOrder).filter(DigitalOrder.order_id == order_id))
        if not order:
            return None

        return {
            "id": order.id,
            "order_id": order.order_id,
            "email": order.email,
            "org_id": order.org_id,
            "product_type": order.product_type,
            "product_name": order.product_name,
            "amount": order.amount,
            "currency": order.currency,
            "payment_provider": order.payment_provider,
            "payment_id": order.payment_id,
            "payment_status": order.payment_status,
            "delivery_status": order.delivery_status,
            "referral_code": order.referral_code,
            "commission_calculated": order.commission_calculated,
            "delivery_attempts": order.delivery_attempts,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "delivery_error": order.delivery_error,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        }


def update_digital_order_payment(
    order_id: str,
    *,
    payment_id: str,
    payment_status: str,
) -> bool:
    """
    Update digital order payment status.

    Args:
        order_id: Order UUID
        payment_id: Payment ID from provider
        payment_status: New status ("paid", "failed", "refunded")

    Returns:
        True if updated, False if order not found
    """
    with get_session() as s:
        order = s.scalar(select(DigitalOrder).filter(DigitalOrder.order_id == order_id))
        if not order:
            return False

        order.payment_id = payment_id
        order.payment_status = payment_status
        order.updated_at = datetime.now(UTC)

        if payment_status == "paid":
            order.paid_at = datetime.now(UTC)

        s.commit()
        return True


def update_digital_order_delivery(
    order_id: str,
    *,
    delivery_status: str,
    delivery_error: str | None = None,
) -> bool:
    """
    Update digital order delivery status.

    Args:
        order_id: Order UUID
        delivery_status: "pending", "sent", "failed"
        delivery_error: Error message if failed

    Returns:
        True if updated, False if order not found
    """
    with get_session() as s:
        order = s.scalar(select(DigitalOrder).filter(DigitalOrder.order_id == order_id))
        if not order:
            return False

        order.delivery_status = delivery_status
        order.delivery_attempts = (order.delivery_attempts or 0) + 1

        if delivery_status == "sent":
            order.delivered_at = datetime.now(UTC)
            order.delivery_error = None
        elif delivery_error:
            order.delivery_error = delivery_error

        order.updated_at = datetime.now(UTC)
        s.commit()
        return True


def mark_digital_order_commission_calculated(order_id: str) -> bool:
    """Mark that referral commission was calculated for this order."""
    with get_session() as s:
        order = s.scalar(select(DigitalOrder).filter(DigitalOrder.order_id == order_id))
        if not order:
            return False

        order.commission_calculated = True
        order.updated_at = datetime.now(UTC)
        s.commit()
        return True


def get_pending_digital_deliveries(limit: int = 50) -> list[dict[str, Any]]:
    """
    Get orders that are paid but not yet delivered.
    Used by background workers or n8n for automated delivery.

    Args:
        limit: Maximum number of orders to return

    Returns:
        List of pending delivery orders
    """
    with get_session() as s:
        orders = s.scalars(
            select(DigitalOrder)
            .filter(DigitalOrder.payment_status == "paid")
            .filter(DigitalOrder.delivery_status.in_(["pending", "failed"]))
            .filter(DigitalOrder.delivery_attempts < 3)  # Max 3 attempts
            .order_by(DigitalOrder.created_at)
            .limit(limit)
        ).all()

        return [
            {
                "id": o.id,
                "order_id": o.order_id,
                "email": o.email,
                "product_type": o.product_type,
                "product_name": o.product_name,
                "delivery_attempts": o.delivery_attempts,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ]


# ============================================================================
# Leads (marketing funnel capture)
# ============================================================================


def create_lead(
    email: str,
    source: str,
    *,
    name: str | None = None,
    ip_address: str | None = None,
    referral_code: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    utm_content: str | None = None,
    utm_term: str | None = None,
    extra_data: dict[str, Any] | None = None,
) -> int:
    """
    Persist a new marketing lead.

    Args:
        email: Lead's email address
        source: Acquisition channel — "checklist", "free_scan", or "beta"
        name: Optional display name
        ip_address: Remote IP for fraud detection
        referral_code: Referral code used (if any)
        utm_source: UTM source parameter
        utm_medium: UTM medium parameter
        utm_campaign: UTM campaign parameter
        utm_content: UTM content parameter
        utm_term: UTM term parameter
        extra_data: Additional metadata (company, role, etc.)

    Returns:
        The new lead's database ID
    """
    with get_session() as s:
        lead = Lead(
            email=email.lower().strip(),
            name=name,
            source=source,
            ip_address=ip_address,
            referral_code=referral_code,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            utm_term=utm_term,
            extra_data=extra_data,
            score=0,
            segment="cold",
        )
        s.add(lead)
        s.commit()
        s.refresh(lead)
        return lead.id


def get_lead(lead_id: int) -> dict[str, Any] | None:
    """Get lead by ID."""
    with get_session() as s:
        lead = s.get(Lead, lead_id)
        if not lead:
            return None
        return {
            "id": lead.id,
            "email": lead.email,
            "name": lead.name,
            "source": lead.source,
            "score": lead.score,
            "segment": lead.segment,
            "utm_source": lead.utm_source,
            "utm_medium": lead.utm_medium,
            "utm_campaign": lead.utm_campaign,
            "utm_content": lead.utm_content,
            "utm_term": lead.utm_term,
            "extra_data": lead.extra_data,
            "pipedrive_deal_id": lead.pipedrive_deal_id,
            "last_activity_at": lead.last_activity_at.isoformat()
            if lead.last_activity_at
            else None,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
        }


def update_lead_pipedrive_deal_id(lead_id: int, deal_id: int) -> None:
    """Update Pipedrive deal ID for a lead."""
    with get_session() as s:
        lead = s.get(Lead, lead_id)
        if lead:
            lead.pipedrive_deal_id = deal_id
            s.commit()


def get_guest_scan_count_last_24h(email: str) -> int:
    """
    Count how many free-scan leads were created for this email in the last 24 hours.
    Used as a DB-level rate-limit fallback when Redis is unavailable.
    """
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    with get_session() as s:
        count = s.execute(
            select(func.count())
            .select_from(Lead)
            .where(Lead.email == email.lower().strip())
            .where(Lead.source == "free_scan")
            .where(Lead.created_at >= cutoff)
        ).scalar_one()
        return int(count or 0)


def check_guest_scan_rate_limit(email: str) -> bool:
    """
    Return True when the email is allowed to run a guest scan (not rate-limited).

    Strategy:
    1. Try Redis first — key ``guest_scan:<email>`` with a 24-hour TTL.
       If the key already exists the quota is exhausted → return False.
       On first call the key is created and the limit window starts.
    2. Fall back to a DB count when Redis is unavailable.

    Rate: 1 scan per email per 24 hours.
    """
    import os

    redis_url = os.getenv("SEC_SCANNER_REDIS_URL", "").strip()
    if redis_url:
        try:
            import redis as _redis

            r = _redis.from_url(redis_url, decode_responses=True)
            key = f"guest_scan:{email.lower().strip()}"
            # SETNX-style: SET key 1 NX EX 86400
            result = r.set(key, "1", nx=True, ex=86400)
            # result is True  → key was newly set   → first scan, allowed
            # result is None  → key already existed → already scanned, blocked
            return result is True
        except Exception:
            pass

    # Redis unavailable — use DB count
    return get_guest_scan_count_last_24h(email) == 0


def get_financial_metrics() -> dict[str, Any]:
    """
    Calculate financial metrics for the current and previous month.

    Returns MRR (subscription revenue), digital product revenue, subscriber counts,
    churn rate, and progress toward revenue targets.
    """
    from sqlalchemy import distinct as sa_distinct

    now = datetime.now(UTC)
    current_month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    if now.month == 1:
        prev_month_start = datetime(now.year - 1, 12, 1, tzinfo=UTC)
    else:
        prev_month_start = datetime(now.year, now.month - 1, 1, tzinfo=UTC)

    with get_session() as s:
        # MRR: subscription payments this month (exclude free plan and digital products)
        mrr = float(
            s.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0.0))
                .where(Payment.status == "succeeded")
                .where(Payment.created_at >= current_month_start)
                .where(Payment.currency == "RUB")
                .where(Payment.plan_code.isnot(None))
                .where(Payment.plan_code != "free")
                .where(~Payment.plan_code.like("digital_%"))
            )
            or 0.0
        )

        # Digital product revenue this month (RUB only)
        digital_revenue = float(
            s.scalar(
                select(func.coalesce(func.sum(DigitalOrder.amount), 0.0))
                .where(DigitalOrder.payment_status == "paid")
                .where(DigitalOrder.paid_at >= current_month_start)
                .where(DigitalOrder.currency == "RUB")
            )
            or 0.0
        )

        # Active unique subscribers this month (orgs with at least one succeeded subscription payment)
        active_subscribers = int(
            s.scalar(
                select(func.count(sa_distinct(Payment.org_id)))
                .where(Payment.status == "succeeded")
                .where(Payment.created_at >= current_month_start)
                .where(Payment.plan_code.isnot(None))
                .where(Payment.plan_code != "free")
                .where(~Payment.plan_code.like("digital_%"))
            )
            or 0
        )

        # New subscribers: orgs whose very first succeeded payment is this month
        first_payment_subq = (
            select(
                Payment.org_id,
                func.min(Payment.created_at).label("first_payment"),
            )
            .where(Payment.status == "succeeded")
            .where(Payment.plan_code.isnot(None))
            .where(Payment.plan_code != "free")
            .where(~Payment.plan_code.like("digital_%"))
            .group_by(Payment.org_id)
            .subquery()
        )
        new_subscribers = int(
            s.scalar(
                select(func.count())
                .select_from(first_payment_subq)
                .where(first_payment_subq.c.first_payment >= current_month_start)
            )
            or 0
        )

        # Churn: orgs that paid last month but have no payment this month
        paid_last_month_ids: set[int] = set(
            s.scalars(
                select(sa_distinct(Payment.org_id))
                .where(Payment.status == "succeeded")
                .where(Payment.created_at >= prev_month_start)
                .where(Payment.created_at < current_month_start)
                .where(Payment.plan_code.isnot(None))
                .where(Payment.plan_code != "free")
            ).all()
        )
        paid_this_month_ids: set[int] = set(
            s.scalars(
                select(sa_distinct(Payment.org_id))
                .where(Payment.status == "succeeded")
                .where(Payment.created_at >= current_month_start)
                .where(Payment.plan_code.isnot(None))
                .where(Payment.plan_code != "free")
            ).all()
        )
        churned_count = len(paid_last_month_ids - paid_this_month_ids)
        churn_rate = (
            round(churned_count / len(paid_last_month_ids) * 100.0, 2)
            if paid_last_month_ids
            else 0.0
        )

        # Digital orders count this month
        digital_orders_count = int(
            s.scalar(
                select(func.count())
                .select_from(DigitalOrder)
                .where(DigitalOrder.payment_status == "paid")
                .where(DigitalOrder.paid_at >= current_month_start)
            )
            or 0
        )

    mrr_target = 500_000.0
    total_revenue = mrr + digital_revenue

    return {
        "period": current_month_start.strftime("%Y-%m"),
        "mrr_rub": round(mrr, 2),
        "digital_revenue_rub": round(digital_revenue, 2),
        "total_revenue_rub": round(total_revenue, 2),
        "active_subscribers": active_subscribers,
        "new_subscribers_this_month": new_subscribers,
        "churned_subscribers": churned_count,
        "churn_rate_percent": churn_rate,
        "digital_orders_count": digital_orders_count,
        "targets": {
            "mrr_target_rub": mrr_target,
            "mrr_progress_percent": round(mrr / mrr_target * 100.0, 1) if mrr_target else 0.0,
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def get_digital_orders_by_email(email: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get all digital orders for a customer email."""
    with get_session() as s:
        orders = s.scalars(
            select(DigitalOrder)
            .filter(DigitalOrder.email == email)
            .order_by(DigitalOrder.created_at.desc())
            .limit(limit)
        ).all()

        return [
            {
                "order_id": o.order_id,
                "product_type": o.product_type,
                "product_name": o.product_name,
                "amount": o.amount,
                "payment_status": o.payment_status,
                "delivery_status": o.delivery_status,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ]
