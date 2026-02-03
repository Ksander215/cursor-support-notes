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
    NotificationSettings,
    Organization,
    Plan,
    ScanProgress,
    UsageBucket,
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
