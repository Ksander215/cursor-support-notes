"""
Leads router — lead capture, scoring, and attribution endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..schemas import (
    AttributionReportResponse,
    AuditRequestCreate,
    LeadChecklistRequest,
    LeadChecklistResponse,
    LeadCreateRequest,
    LeadEventRequest,
    LeadEventResponse,
    LeadFreeScanRequest,
    LeadFreeScanResponse,
    LeadFreeScanStatusResponse,
    LeadScoreResponse,
    LeadSegmentResponse,
    ScoringSummaryResponse,
)
from ..service import enqueue_audit
from ..services.attribution_service import AttributionService
from ..services.email_sequence_service import EmailSequenceService
from ..services.hot_lead_service import HotLeadService
from ..services.lead_scoring_service import LeadScoringService
from ..targets import normalize_target

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/api/v1", tags=["leads"])

scoring_service = LeadScoringService()
attribution_service = AttributionService()
email_sequence_service = EmailSequenceService()
hot_lead_service = HotLeadService()


@router.post("/leads/free-scan", response_model=LeadFreeScanResponse)
def lead_free_scan(req: LeadFreeScanRequest, request: Request):
    try:
        normalize_target(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_id = enqueue_audit(req.url, "safe", tenant_id=None, created_by_api_key_id=None)

    utm_params = {
        "utm_source": req.utm_source,
        "utm_medium": req.utm_medium,
        "utm_campaign": req.utm_campaign,
        "utm_content": req.utm_content,
        "utm_term": req.utm_term,
    }

    lead_id = db.create_lead(
        email=req.email,
        source="free_scan",
        utm_source=req.utm_source,
        utm_medium=req.utm_medium,
        utm_campaign=req.utm_campaign,
        extra_data={"url": req.url, "audit_id": audit_id},
    )

    attribution_service.record_touch(
        lead_id=lead_id,
        utm_params=utm_params if any(utm_params.values()) else None,
        referrer_url=req.referrer_url,
        landing_page=req.landing_page,
    )

    scoring_service.record_event(
        lead_id=lead_id,
        event_type="started_free_scan",
        event_source="free_scan_page",
    )

    logger.info(f"Free scan started: lead_id={lead_id}, audit_id={audit_id}, email={req.email}")

    return LeadFreeScanResponse(
        scan_id=audit_id,
        status="queued",
    )


@router.get("/leads/free-scan/{audit_id}/status", response_model=LeadFreeScanStatusResponse)
def lead_free_scan_status(audit_id: str, request: Request):
    audit = db.get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    return LeadFreeScanStatusResponse(
        scan_id=audit_id,
        status=audit["status"],
        overall_score=audit.get("overall_score"),
        risk_level=audit.get("risk_level"),
        error=audit.get("error"),
    )


@router.post("/leads/checklist", response_model=LeadChecklistResponse)
def lead_checklist(req: LeadChecklistRequest, request: Request):
    utm_params = {
        "utm_source": req.utm_source,
        "utm_medium": req.utm_medium,
        "utm_campaign": req.utm_campaign,
    }

    lead_id = db.create_lead(
        email=req.email,
        source="checklist",
        name=req.name,
        utm_source=req.utm_source,
        utm_medium=req.utm_medium,
        utm_campaign=req.utm_campaign,
    )

    attribution_service.record_touch(
        lead_id=lead_id,
        utm_params=utm_params if any(utm_params.values()) else None,
        referrer_url=req.referrer_url,
        landing_page=req.landing_page,
    )

    scoring_service.record_event(
        lead_id=lead_id,
        event_type="downloaded_checklist",
        event_source="checklist_page",
    )

    logger.info(f"Checklist downloaded: lead_id={lead_id}, email={req.email}")

    return LeadChecklistResponse(
        download_url="/api/v1/lead/checklist/download",
        message="Thank you! Check your email for the security checklist PDF.",
    )


@router.post("/leads", response_model=LeadScoreResponse)
def create_lead(req: LeadCreateRequest, request: Request):
    """Создать новый лид с UTM параметрами"""
    lead_id = db.create_lead(
        email=req.email,
        source=req.source,
        name=req.name,
        utm_source=req.utm_source,
        utm_medium=req.utm_medium,
        utm_campaign=req.utm_campaign,
        extra_data={"company": req.company, "role": req.role},
    )

    utm_params = {
        "utm_source": req.utm_source,
        "utm_medium": req.utm_medium,
        "utm_campaign": req.utm_campaign,
        "utm_content": req.utm_content,
        "utm_term": req.utm_term,
    }

    attribution_service.record_touch(
        lead_id=lead_id,
        utm_params=utm_params if any(utm_params.values()) else None,
        referrer_url=req.referrer_url,
        landing_page=req.landing_page,
    )

    event_type = "downloaded_checklist" if req.source == "checklist" else "started_free_scan"
    scoring_service.record_event(
        lead_id=lead_id,
        event_type=event_type,
        event_source=f"{req.source}_page",
    )

    return scoring_service.get_lead_score(lead_id)


@router.post("/leads/{lead_id}/event", response_model=LeadEventResponse)
async def record_lead_event(lead_id: int, req: LeadEventRequest, request: Request):
    """Записать событие лида и обновить scoring"""
    try:
        new_score = scoring_service.record_event(
            lead_id=lead_id,
            event_type=req.event_type,
            event_source=req.event_source,
            event_data=req.event_data,
        )

        lead = db.get_lead(lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        if lead.get("segment") == "hot" and not lead.get("pipedrive_deal_id"):
            deal_id = await hot_lead_service.on_hot_lead(
                lead_id=lead_id,
                email=lead["email"],
                name=lead.get("name"),
                company=lead.get("extra_data", {}).get("company"),
                source=lead.get("source"),
                score=new_score,
                utm_source=lead.get("utm_source"),
                utm_medium=lead.get("utm_medium"),
                utm_campaign=lead.get("utm_campaign"),
            )

            if deal_id:
                db.update_lead_pipedrive_deal_id(lead_id, deal_id)

        score_delta = scoring_service.get_score_delta(req.event_type)

        return LeadEventResponse(
            lead_id=lead_id,
            event_type=req.event_type,
            score=new_score,
            segment=lead.get("segment"),
            score_delta=score_delta,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/leads/{lead_id}/score", response_model=LeadScoreResponse)
def get_lead_score(lead_id: int, request: Request):
    """Получить информацию о score лида"""
    score_info = scoring_service.get_lead_score(lead_id)
    if not score_info:
        raise HTTPException(status_code=404, detail="Lead not found")
    return score_info


@router.get("/leads/segment/{segment}", response_model=LeadSegmentResponse)
def get_leads_by_segment(segment: str, request: Request):
    """Получить лиды по сегменту"""
    leads = scoring_service.get_leads_by_segment(segment)
    return LeadSegmentResponse(
        segment=segment,
        leads=leads,
        total=len(leads),
    )


@router.get("/leads/scoring/summary", response_model=ScoringSummaryResponse)
def get_scoring_summary(request: Request):
    """Получить сводку по scoring"""
    return scoring_service.get_scoring_summary()


@router.get("/leads/attribution/report", response_model=AttributionReportResponse)
def get_attribution_report(request: Request):
    """Получить отчёт по attribution"""
    return attribution_service.get_attribution_report()


@router.post("/leads/webhook/email-opened")
async def email_opened_webhook(request: Request):
    """Webhook от SendPulse при открытии email"""
    data = await request.json()

    email = data.get("email")
    campaign_id = data.get("campaign_id")

    if not email:
        return {"ok": False, "error": "Email required"}

    lead = scoring_service.get_lead_by_email(email)
    if lead:
        scoring_service.record_event(
            lead_id=lead["id"],
            event_type="email_opened",
            event_source=f"email_campaign_{campaign_id}",
        )

    return {"ok": True}


@router.post("/leads/webhook/email-clicked")
async def email_clicked_webhook(request: Request):
    """Webhook при клике по ссылке в email"""
    data = await request.json()

    email = data.get("email")
    link_url = data.get("link_url")

    if not email:
        return {"ok": False, "error": "Email required"}

    lead = scoring_service.get_lead_by_email(email)
    if lead:
        scoring_service.record_event(
            lead_id=lead["id"],
            event_type="email_clicked",
            event_source="email_sequence",
            event_data={"link_url": link_url},
        )

    return {"ok": True}


# ── n8n Integration Webhooks ───────────────────────────────────────────────────


@router.post("/leads/webhook/n8n/payment-completed")
async def n8n_payment_completed_webhook(request: Request):
    """
    Webhook от n8n после успешной оплаты YooKassa.

    n8n workflow: payment-processor-agent.json
    После обработки платежа отправляет сюда данные.
    """
    data = await request.json()

    lead_id = data.get("lead_id")
    email = data.get("email")
    amount = data.get("amount", 0)
    plan = data.get("plan", "")
    payment_id = data.get("payment_id")

    if not lead_id and email:
        lead = scoring_service.get_lead_by_email(email)
        lead_id = lead.get("id") if lead else None

    if lead_id:
        scoring_service.record_event(
            lead_id=lead_id,
            event_type="payment_completed",
            event_source="yookassa_webhook",
            event_data={
                "amount": amount,
                "plan": plan,
                "payment_id": payment_id,
            },
        )

        attribution_service.mark_conversion(
            lead_id=lead_id,
            conversion_value=amount,
        )

        logger.info(f"Payment completed for lead {lead_id}: {amount} RUB, plan={plan}")

    return {"ok": True, "lead_id": lead_id}


@router.post("/leads/webhook/n8n/checkout-started")
async def n8n_checkout_started_webhook(request: Request):
    """
    Webhook от n8n когда пользователь начинает checkout.

    n8n workflow: checkout flow tracking
    """
    data = await request.json()

    lead_id = data.get("lead_id")
    email = data.get("email")
    plan = data.get("plan", "")

    if not lead_id and email:
        lead = scoring_service.get_lead_by_email(email)
        lead_id = lead.get("id") if lead else None

    if lead_id:
        scoring_service.record_event(
            lead_id=lead_id,
            event_type="checkout_started",
            event_source="checkout_page",
            event_data={"plan": plan},
        )

    return {"ok": True, "lead_id": lead_id}


@router.post("/leads/webhook/n8n/checkout-abandoned")
async def n8n_checkout_abandoned_webhook(request: Request):
    """
    Webhook от n8n когда пользователь бросил checkout.

    n8n workflow: abandoned cart tracking
    """
    data = await request.json()

    lead_id = data.get("lead_id")
    email = data.get("email")
    plan = data.get("plan", "")
    step = data.get("step", "")

    if not lead_id and email:
        lead = scoring_service.get_lead_by_email(email)
        lead_id = lead.get("id") if lead else None

    if lead_id:
        scoring_service.record_event(
            lead_id=lead_id,
            event_type="checkout_abandoned",
            event_source="checkout_flow",
            event_data={"plan": plan, "step": step},
        )

    return {"ok": True, "lead_id": lead_id}


@router.post("/leads/webhook/n8n/digital-delivered")
async def n8n_digital_delivered_webhook(request: Request):
    """
    Webhook от n8n после доставки цифрового продукта (PDF/ZIP).

    n8n workflow: digital-delivery-agent.json
    """
    data = await request.json()

    lead_id = data.get("lead_id")
    email = data.get("email")
    product_type = data.get("product_type", "")
    order_id = data.get("order_id")

    if not lead_id and email:
        lead = scoring_service.get_lead_by_email(email)
        lead_id = lead.get("id") if lead else None

    if lead_id:
        scoring_service.record_event(
            lead_id=lead_id,
            event_type="digital_product_delivered",
            event_source="n8n_delivery_agent",
            event_data={
                "product_type": product_type,
                "order_id": order_id,
            },
        )

    return {"ok": True, "lead_id": lead_id}


@router.post("/leads/webhook/n8n/scan-completed")
async def n8n_scan_completed_webhook(request: Request):
    """
    Webhook от n8n после завершения сканирования.

    n8n workflow: crm-webhook-scan-completed.json
    """
    data = await request.json()

    lead_id = data.get("lead_id")
    email = data.get("email")
    audit_id = data.get("audit_id")
    score = data.get("score", 0)
    risk_level = data.get("risk_level", "")

    if not lead_id and email:
        lead = scoring_service.get_lead_by_email(email)
        lead_id = lead.get("id") if lead else None

    if lead_id:
        scoring_service.record_event(
            lead_id=lead_id,
            event_type="completed_free_scan",
            event_source="audit_engine",
            event_data={
                "audit_id": audit_id,
                "score": score,
                "risk_level": risk_level,
            },
        )

    return {"ok": True, "lead_id": lead_id}


@router.post("/leads/webhook/n8n/referral-made")
async def n8n_referral_made_webhook(request: Request):
    """
    Webhook от n8n когда пользователь пригласил друга.

    n8n workflow: referral tracking
    """
    data = await request.json()

    lead_id = data.get("lead_id")
    email = data.get("email")
    referral_code = data.get("referral_code", "")

    if not lead_id and email:
        lead = scoring_service.get_lead_by_email(email)
        lead_id = lead.get("id") if lead else None

    if lead_id:
        scoring_service.record_event(
            lead_id=lead_id,
            event_type="referral_made",
            event_source="referral_system",
            event_data={"referral_code": referral_code},
        )

    return {"ok": True, "lead_id": lead_id}


@router.post("/leads/webhook/n8n/trial-started")
async def n8n_trial_started_webhook(request: Request):
    """
    Webhook от n8n когда пользователь начал пробный период.
    """
    data = await request.json()

    lead_id = data.get("lead_id")
    email = data.get("email")
    plan = data.get("plan", "")

    if not lead_id and email:
        lead = scoring_service.get_lead_by_email(email)
        lead_id = lead.get("id") if lead else None

    if lead_id:
        scoring_service.record_event(
            lead_id=lead_id,
            event_type="trial_started",
            event_source="checkout_flow",
            event_data={"plan": plan},
        )

    return {"ok": True, "lead_id": lead_id}


@router.get("/lead/checklist/download")
def lead_checklist_download():
    """Redirect to the static PDF guide."""
    import os
    from pathlib import Path

    from fastapi.responses import FileResponse, RedirectResponse

    pdf_path = Path(
        os.getenv(
            "CHECKLIST_PDF_PATH",
            "/data/pdf-guide/Безопасность_API_за_2_часа.pdf",
        )
    )
    if pdf_path.exists():
        return FileResponse(
            str(pdf_path),
            media_type="application/pdf",
            filename="Безопасность_API_за_2_часа.pdf",
        )
    return RedirectResponse(
        url="https://sec-scanner.pro/pdf/Безопасность_API_за_2_часа.pdf",
        status_code=302,
    )


@router.post("/audit-request")
async def submit_audit_request(req: "AuditRequestCreate"):
    """Submit audit request - sends notification to admin."""
    from ..telegram_alerts import telegram_alerts

    message = f"""
🔍 <b>Новая заявка на экспресс-аудит</b>

📧 <b>Email:</b> {req.email}
🔗 <b>API URL:</b> {req.api_url}
📝 <b>Описание:</b>
{req.project_description}
"""

    if req.deadline:
        message += f"\n⏰ <b>Дедлайн:</b> {req.deadline}"

    if req.contact_telegram:
        message += f"\n💬 <b>Telegram:</b> {req.contact_telegram}"

    message += "\n\n💰 <b>Цена:</b> от 3 000 ₽"
    message += "\n⏱ <b>Время:</b> 2 часа"

    try:
        await telegram_alerts.send_info(
            message=message,
            details={
                "type": "audit_request",
                "email": req.email,
                "api_url": req.api_url,
                "deadline": req.deadline,
                "telegram": req.contact_telegram,
            },
        )
        logger.info(f"Audit request submitted: email={req.email}, api_url={req.api_url}")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification for audit request: {e}")

    return {
        "status": "success",
        "message": "Заявка принята. Я свяжусь с вами в течение 24 часов.",
    }
