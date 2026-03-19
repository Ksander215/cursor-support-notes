"""
Repository module — data access layer.
Extracts data operations from db.py for better separation of concerns.
Keeps db.py minimal (session management only).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.sec_scanner.db import get_session
from src.sec_scanner.models import (
    ApiKey,
    Audit,
    AuditLog,
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

        if name:
            p.name = name
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
    with get_session() as s:
        org = s.get(Organization, org_id)
        if not org:
            return None
        return {
            "id": org.id,
            "name": org.name,
            "plan_id": org.plan_id,
            "is_active": org.is_active,
            "white_label_config": getattr(org, "white_label_config", None),
        }


def get_plan_by_code(plan_code: str) -> dict[str, Any] | None:
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
    with get_session() as s:
        org = s.get(Organization, org_id)
        if org:
            org.plan_id = plan_id
            s.commit()


def update_org_whitelabel_config(org_id: int, config: dict[str, Any]) -> None:
    with get_session() as s:
        org = s.get(Organization, org_id)
        if org:
            org.white_label_config = config
            s.commit()


def create_api_key(
    *,
    tenant_id: int,
    hashed_key: str,
    prefix: str,
    name: str = "",
) -> None:
    with get_session() as s:
        key = ApiKey(
            tenant_id=tenant_id,
            hashed_key=hashed_key,
            prefix=prefix,
            name=name,
        )
        s.add(key)
        s.commit()


def list_api_keys_for_tenant(tenant_id: int) -> list[dict[str, Any]]:
    with get_session() as s:
        keys = s.execute(select(ApiKey).where(ApiKey.tenant_id == tenant_id)).scalars().all()
        return [
            {
                "id": k.id,
                "prefix": k.prefix,
                "name": k.name,
                "created_at": _utc_now_iso(),
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            }
            for k in keys
        ]


def revoke_api_key(api_key_id: str, tenant_id: int) -> bool:
    with get_session() as s:
        key = s.execute(
            select(ApiKey).where(
                ApiKey.prefix == api_key_id,
                ApiKey.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if not key:
            return False
        key.revoked_at = datetime.now(UTC)
        s.commit()
        return True


def mark_audit_started(audit_id: str) -> None:
    with get_session() as s:
        audit = s.get(Audit, audit_id)
        if audit:
            audit.status = "running"
            audit.started_at = datetime.now(UTC)
            s.commit()


def mark_audit_completed(
    audit_id: str,
    result: dict[str, Any] | None = None,
    report_markdown: str | None = None,
    overall_score: float | None = None,
    risk_level: str | None = None,
    critical_issues_count: int | None = None,
) -> None:
    with get_session() as s:
        audit = s.get(Audit, audit_id)
        if audit:
            audit.status = "completed"
            audit.completed_at = datetime.now(UTC)
            if result:
                audit.result = result
            if report_markdown:
                audit.report_markdown = report_markdown
            if overall_score is not None:
                audit.overall_score = overall_score
            if risk_level:
                audit.risk_level = risk_level
            if critical_issues_count is not None:
                audit.critical_issues_count = critical_issues_count
            s.commit()


def mark_audit_failed(audit_id: str, error: str) -> None:
    with get_session() as s:
        audit = s.get(Audit, audit_id)
        if audit:
            audit.status = "failed"
            audit.completed_at = datetime.now(UTC)
            audit.error = error
            s.commit()


def get_audit(audit_id: str) -> dict[str, Any] | None:
    with get_session() as s:
        audit = s.get(Audit, audit_id)
        if not audit:
            return None
        return _audit_to_dict(audit)


def list_audits(
    tenant_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    with get_session() as s:
        query = select(Audit)
        if tenant_id is not None:
            query = query.where(Audit.tenant_id == tenant_id)
        if status:
            query = query.where(Audit.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total = s.execute(count_query).scalar() or 0

        sort_column = getattr(Audit, sort_by, Audit.created_at)
        if sort_order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        query = query.offset(offset).limit(limit)
        audits = s.execute(query).scalars().all()

        return [_audit_to_dict(a) for a in audits], total


def get_audit_history(target: str, limit: int = 50) -> list[dict[str, Any]]:
    with get_session() as s:
        audits = (
            s.execute(
                select(Audit)
                .where(Audit.target == target)
                .where(Audit.status == "completed")
                .order_by(Audit.completed_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": a.id,
                "completed_at": a.completed_at.isoformat() if a.completed_at else "",
                "overall_score": a.overall_score,
                "risk_level": a.risk_level,
            }
            for a in audits
        ]


def _audit_to_dict(a: Audit) -> dict[str, Any]:
    return {
        "id": a.id,
        "tenant_id": a.tenant_id,
        "created_by_api_key_id": a.created_by_api_key_id,
        "target": a.target,
        "mode": a.mode,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else "",
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "overall_score": a.overall_score,
        "risk_level": a.risk_level,
        "critical_issues_count": a.critical_issues_count,
        "error": a.error,
        "result": getattr(a, "result", None),
        "report_markdown": getattr(a, "report_markdown", None),
    }


def get_api_key_context_by_hash(hashed_key: str) -> dict[str, Any] | None:
    with get_session() as s:
        key = s.execute(select(ApiKey).where(ApiKey.hashed_key == hashed_key)).scalar_one_or_none()
        if not key or key.revoked_at:
            return None

        org = s.get(Organization, key.tenant_id)
        if not org or not org.is_active:
            return None

        plan = s.get(Plan, org.plan_id)
        if not plan:
            return None

        key.last_used_at = datetime.now(UTC)
        s.commit()

        return {
            "org_id": org.id,
            "tenant_id": key.tenant_id,
            "api_key_id": key.prefix,
            "api_key_prefix": key.prefix,
            "plan_code": plan.code,
            "requests_per_minute": plan.requests_per_minute,
            "monthly_audits_quota": plan.monthly_audits_quota,
            "concurrency_limit": plan.concurrency_limit,
            "is_admin": False,
        }


def increment_usage(
    org_id: int,
    api_key_id: str,
    metric: str,
    bucket_start: datetime,
    amount: int = 1,
) -> None:
    with get_session() as s:
        bucket = s.execute(
            select(UsageBucket).where(
                UsageBucket.org_id == org_id,
                UsageBucket.metric == metric,
                UsageBucket.bucket_start == bucket_start,
            )
        ).scalar_one_or_none()

        if bucket:
            bucket.total += amount
        else:
            bucket = UsageBucket(
                org_id=org_id,
                metric=metric,
                bucket_start=bucket_start,
                total=amount,
            )
            s.add(bucket)
        s.commit()


def get_usage_sum_for_month(*, org_id: int, metric: str, bucket_start: datetime) -> int:
    with get_session() as s:
        result = s.execute(
            select(func.coalesce(func.sum(UsageBucket.total), 0)).where(
                UsageBucket.org_id == org_id,
                UsageBucket.metric == metric,
                UsageBucket.bucket_start == bucket_start,
            )
        ).scalar()
        return int(result) if result else 0


def get_quota_info(*, tenant_id: int) -> dict[str, Any] | None:
    with get_session() as s:
        org = s.get(Organization, tenant_id)
        if not org:
            return None

        plan = s.get(Plan, org.plan_id)
        if not plan:
            return None

        now = datetime.now(UTC)
        month_start = datetime(now.year, now.month, 1, tzinfo=UTC)

        from src.sec_scanner.saas import month_bucket_start

        month_start = month_bucket_start(now)

        requests_used = get_usage_sum_for_month(
            org_id=tenant_id, metric="requests", bucket_start=month_start
        )
        audits_used = get_usage_sum_for_month(
            org_id=tenant_id, metric="audits", bucket_start=month_start
        )

        return {
            "org_id": org.id,
            "plan_code": plan.code,
            "monthly_audits_quota": plan.monthly_audits_quota,
            "monthly_audits_used": audits_used,
            "requests_per_minute": plan.requests_per_minute,
            "concurrency_limit": plan.concurrency_limit,
            "month_start": month_start.isoformat(),
        }


def count_running_audits(tenant_id: int) -> int:
    with get_session() as s:
        return (
            s.execute(
                select(func.count())
                .select_from(Audit)
                .where(
                    Audit.tenant_id == tenant_id,
                    Audit.status == "running",
                )
            ).scalar()
            or 0
        )


def list_notification_settings(org_id: int) -> list[dict[str, Any]]:
    with get_session() as s:
        settings = (
            s.execute(select(NotificationSettings).where(NotificationSettings.org_id == org_id))
            .scalars()
            .all()
        )
        return [_notification_to_dict(s) for s in settings]


def create_notification_settings(
    *,
    tenant_id: int,
    provider: str,
    events: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    with get_session() as s:
        settings = NotificationSettings(
            org_id=tenant_id,
            provider=provider,
            events=events,
            config=config,
            enabled=True,
        )
        s.add(settings)
        s.commit()
        s.refresh(settings)
        return _notification_to_dict(settings)


def update_notification_settings(
    *,
    settings_id: int,
    tenant_id: int,
    events: list[str] | None = None,
    config: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    with get_session() as s:
        settings = s.get(NotificationSettings, settings_id)
        if not settings or settings.org_id != tenant_id:
            raise ValueError("Settings not found")
        if events is not None:
            settings.events = events
        if config is not None:
            settings.config = config
        if enabled is not None:
            settings.enabled = enabled
        s.commit()
        return _notification_to_dict(settings)


def get_notification_settings(settings_id: int, tenant_id: int) -> dict[str, Any] | None:
    with get_session() as s:
        settings = s.get(NotificationSettings, settings_id)
        if not settings or settings.org_id != tenant_id:
            return None
        return _notification_to_dict(settings)


def delete_notification_settings(*, settings_id: int, tenant_id: int) -> bool:
    with get_session() as s:
        settings = s.get(NotificationSettings, settings_id)
        if not settings or settings.org_id != tenant_id:
            return False
        s.delete(settings)
        s.commit()
        return True


def _notification_to_dict(s: NotificationSettings) -> dict[str, Any]:
    return {
        "id": s.id,
        "org_id": s.org_id,
        "provider": s.provider,
        "events": s.events,
        "config": s.config or {},
        "enabled": s.enabled,
        "created_at": s.created_at.isoformat() if s.created_at else "",
    }


def create_scan_progress(
    audit_id: str,
    steps: list[dict[str, Any]],
) -> None:
    with get_session() as s:
        for step in steps:
            progress = ScanProgress(
                audit_id=audit_id,
                step_name=step["name"],
                step_status="pending",
                step_order=step.get("order", 0),
            )
            s.add(progress)
        s.commit()


def update_scan_progress_step(
    audit_id: str,
    step_name: str,
    status: str,
    progress: int | None = None,
    message: str | None = None,
) -> None:
    with get_session() as s:
        step = s.execute(
            select(ScanProgress).where(
                ScanProgress.audit_id == audit_id,
                ScanProgress.step_name == step_name,
            )
        ).scalar_one_or_none()
        if step:
            step.step_status = status
            if progress is not None:
                step.step_progress = progress
            if message:
                step.message = message
            s.commit()


def get_scan_progress(audit_id: str) -> list[dict[str, Any]]:
    with get_session() as s:
        steps = (
            s.execute(
                select(ScanProgress)
                .where(ScanProgress.audit_id == audit_id)
                .order_by(ScanProgress.step_order)
            )
            .scalars()
            .all()
        )
        return [
            {
                "step_name": s.step_name,
                "step_status": s.step_status,
                "step_progress": s.step_progress,
                "message": s.message,
            }
            for s in steps
        ]


def insert_audit_log(log_data: dict[str, Any]) -> int:
    with get_session() as s:
        log = AuditLog(**log_data)
        s.add(log)
        s.commit()
        return log.id


def get_audit_logs(
    tenant_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    with get_session() as s:
        query = select(AuditLog)
        if tenant_id is not None:
            query = query.where(AuditLog.org_id == tenant_id)
        query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        logs = s.execute(query).scalars().all()
        return [
            {
                "id": log_item.id,
                "action": log_item.action,
                "org_id": log_item.org_id,
                "api_key_id": log_item.api_key_id,
                "details": log_item.details,
                "created_at": log_item.created_at.isoformat() if log_item.created_at else "",
            }
            for log_item in logs
        ]


def get_payment_by_provider_id(provider: str, payment_id: str) -> dict[str, Any] | None:
    with get_session() as s:
        payment = s.execute(
            select(Payment).where(
                Payment.provider == provider,
                Payment.provider_payment_id == payment_id,
            )
        ).scalar_one_or_none()
        if not payment:
            return None
        return {
            "id": payment.id,
            "org_id": payment.org_id,
            "provider": payment.provider,
            "provider_payment_id": payment.provider_payment_id,
            "status": payment.status,
            "amount": payment.amount,
            "currency": payment.currency,
        }


def create_payment_record(
    *,
    org_id: int,
    provider: str,
    provider_payment_id: str,
    amount: float,
    currency: str,
    plan_code: str,
) -> int:
    with get_session() as s:
        payment = Payment(
            org_id=org_id,
            provider=provider,
            provider_payment_id=provider_payment_id,
            amount=amount,
            currency=currency,
            plan_code=plan_code,
            status="pending",
        )
        s.add(payment)
        s.commit()
        return payment.id


def update_payment_status(
    payment_id: int,
    status: str,
    provider_data: dict[str, Any] | None = None,
) -> None:
    with get_session() as s:
        payment = s.get(Payment, payment_id)
        if payment:
            payment.status = status
            if provider_data:
                payment.provider_data = provider_data
            s.commit()


def generate_referral_code() -> str:
    return f"REF{uuid.uuid4().hex[:8].upper()}"


def set_referral_code(org_id: int) -> str:
    code = generate_referral_code()
    with get_session() as s:
        referral = Referral(org_id=org_id, referral_code=code)
        s.add(referral)
        s.commit()
    return code


def get_referral_code(org_id: int) -> str | None:
    with get_session() as s:
        referral = s.execute(select(Referral).where(Referral.org_id == org_id)).scalar_one_or_none()
        return referral.referral_code if referral else None


def register_referral(client_org_id: int, referral_code: str) -> bool:
    with get_session() as s:
        referrer = s.execute(
            select(Referral).where(Referral.referral_code == referral_code)
        ).scalar_one_or_none()
        if not referrer or referrer.org_id == client_org_id:
            return False
        referrer.referred_org_id = client_org_id
        s.commit()
        return True


def calculate_referral_commission(payment_id: int, payment_amount: float, plan_code: str) -> None:
    COMMISSION_PERCENT = 20.0
    commission = payment_amount * (COMMISSION_PERCENT / 100)

    with get_session() as s:
        payment = s.get(Payment, payment_id)
        if not payment:
            return

        referral = s.execute(
            select(Referral).where(Referral.referred_org_id == payment.org_id)
        ).scalar_one_or_none()

        if referral:
            referral.pending_commission += commission
            referral.total_commission += commission
            s.commit()


def get_referral_stats(org_id: int) -> dict[str, Any]:
    with get_session() as s:
        referral = s.execute(select(Referral).where(Referral.org_id == org_id)).scalar_one_or_none()

        if not referral:
            return {
                "referral_code": "",
                "total_referrals": 0,
                "total_commission": 0.0,
                "pending_commission": 0.0,
                "paid_commission": 0.0,
            }

        return {
            "referral_code": referral.referral_code,
            "total_referrals": referral.referred_org_id or 0,
            "total_commission": referral.total_commission,
            "pending_commission": referral.pending_commission,
            "paid_commission": referral.paid_commission,
        }


def create_webhook(
    *,
    tenant_id: int,
    url: str,
    events: list[str],
    name: str = "",
    secret: str | None = None,
) -> dict[str, Any]:
    with get_session() as s:
        webhook = Webhook(
            org_id=tenant_id,
            url=url,
            events=events,
            name=name,
            secret=secret,
            enabled=True,
        )
        s.add(webhook)
        s.commit()
        s.refresh(webhook)
        return _webhook_to_dict(webhook)


def list_webhooks(tenant_id: int) -> list[dict[str, Any]]:
    with get_session() as s:
        webhooks = s.execute(select(Webhook).where(Webhook.org_id == tenant_id)).scalars().all()
        return [_webhook_to_dict(w) for w in webhooks]


def get_webhook(webhook_id: int, tenant_id: int) -> dict[str, Any] | None:
    with get_session() as s:
        webhook = s.get(Webhook, webhook_id)
        if not webhook or webhook.org_id != tenant_id:
            return None
        return _webhook_to_dict(webhook)


def get_webhook_by_id_internal(webhook_id: int) -> dict[str, Any] | None:
    with get_session() as s:
        webhook = s.get(Webhook, webhook_id)
        return _webhook_to_dict(webhook) if webhook else None


def update_webhook(
    *,
    webhook_id: int,
    tenant_id: int,
    url: str | None = None,
    events: list[str] | None = None,
    name: str | None = None,
    secret: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    with get_session() as s:
        webhook = s.get(Webhook, webhook_id)
        if not webhook or webhook.org_id != tenant_id:
            raise ValueError("Webhook not found")
        if url is not None:
            webhook.url = url
        if events is not None:
            webhook.events = events
        if name is not None:
            webhook.name = name
        if secret is not None:
            webhook.secret = secret
        if enabled is not None:
            webhook.enabled = enabled
        s.commit()
        return _webhook_to_dict(webhook)


def delete_webhook(*, webhook_id: int, tenant_id: int) -> bool:
    with get_session() as s:
        webhook = s.get(Webhook, webhook_id)
        if not webhook or webhook.org_id != tenant_id:
            return False
        s.delete(webhook)
        s.commit()
        return True


def get_enabled_webhooks_for_event(*, event: str) -> list[dict[str, Any]]:
    with get_session() as s:
        webhooks = s.execute(select(Webhook).where(Webhook.enabled)).scalars().all()
        return [_webhook_to_dict(w) for w in webhooks if event in (w.events or [])]


def update_webhook_delivery_status(
    webhook_id: int,
    delivery_id: str,
    status: str,
    response_code: int | None = None,
    error: str | None = None,
) -> None:
    pass


def create_digital_order(
    *,
    org_id: int,
    product_id: str,
    amount: float,
    currency: str,
    provider: str,
    provider_order_id: str,
) -> str:
    order_id = str(uuid.uuid4())
    with get_session() as s:
        order = DigitalOrder(
            id=order_id,
            org_id=org_id,
            product_id=product_id,
            amount=amount,
            currency=currency,
            provider=provider,
            provider_order_id=provider_order_id,
            status="pending",
        )
        s.add(order)
        s.commit()
    return order_id


def get_digital_order(order_id: str) -> dict[str, Any] | None:
    with get_session() as s:
        order = s.get(DigitalOrder, order_id)
        if not order:
            return None
        return _digital_order_to_dict(order)


def update_digital_order_payment(
    order_id: str,
    provider: str,
    provider_payment_id: str,
    status: str,
) -> None:
    with get_session() as s:
        order = s.get(DigitalOrder, order_id)
        if order:
            order.provider = provider
            order.provider_order_id = provider_payment_id
            order.status = status
            s.commit()


def update_digital_order_delivery(
    order_id: str,
    delivery_status: str,
    delivery_data: dict[str, Any] | None = None,
) -> None:
    with get_session() as s:
        order = s.get(DigitalOrder, order_id)
        if order:
            order.delivery_status = delivery_status
            if delivery_data:
                order.delivery_data = delivery_data
            s.commit()


def mark_digital_order_commission_calculated(order_id: str) -> bool:
    with get_session() as s:
        order = s.get(DigitalOrder, order_id)
        if order:
            order.commission_calculated = True
            s.commit()
            return True
        return False


def get_pending_digital_deliveries(limit: int = 50) -> list[dict[str, Any]]:
    with get_session() as s:
        orders = (
            s.execute(
                select(DigitalOrder)
                .where(DigitalOrder.status == "paid")
                .where(DigitalOrder.delivery_status == "pending")
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_digital_order_to_dict(o) for o in orders]


def create_lead(
    email: str,
    source: str,
    target: str | None = None,
    audit_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    with get_session() as s:
        lead = Lead(
            email=email,
            source=source,
            target=target,
            audit_id=audit_id,
            metadata=metadata or {},
        )
        s.add(lead)
        s.commit()


def get_white_label_config(org_id: int) -> dict[str, Any]:
    with get_session() as s:
        org = s.get(Organization, org_id)
        config = getattr(org, "white_label_config", None) or {}
        return {
            "logo_url": config.get("logo_url"),
            "primary_color": config.get("primary_color"),
            "company_name": config.get("company_name"),
            "custom_domain": config.get("custom_domain"),
            "enabled": bool(config),
        }


def update_white_label_config(
    org_id: int,
    logo_url: str | None = None,
    primary_color: str | None = None,
    company_name: str | None = None,
    custom_domain: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    with get_session() as s:
        org = s.get(Organization, org_id)
        if not org:
            raise ValueError("Organization not found")

        config = getattr(org, "white_label_config", None) or {}
        if logo_url is not None:
            config["logo_url"] = logo_url
        if primary_color is not None:
            config["primary_color"] = primary_color
        if company_name is not None:
            config["company_name"] = company_name
        if custom_domain is not None:
            config["custom_domain"] = custom_domain
        if enabled is not None:
            config["enabled"] = enabled

        org.white_label_config = config
        s.commit()

        return {
            "logo_url": config.get("logo_url"),
            "primary_color": config.get("primary_color"),
            "company_name": config.get("company_name"),
            "custom_domain": config.get("custom_domain"),
            "enabled": config.get("enabled", False),
        }


def _webhook_to_dict(w: Webhook) -> dict[str, Any]:
    return {
        "id": w.id,
        "org_id": w.org_id,
        "url": w.url,
        "events": w.events or [],
        "name": w.name,
        "secret": w.secret,
        "enabled": w.enabled,
        "created_at": w.created_at.isoformat() if w.created_at else "",
    }


def _digital_order_to_dict(o: DigitalOrder) -> dict[str, Any]:
    return {
        "id": o.id,
        "org_id": o.org_id,
        "product_id": o.product_id,
        "amount": o.amount,
        "currency": o.currency,
        "status": o.status,
        "delivery_status": o.delivery_status,
    }
