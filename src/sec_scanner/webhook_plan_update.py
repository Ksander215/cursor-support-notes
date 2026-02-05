"""
Общий хелпер обновления плана организации по результату платёжного webhook.

Используется из api_payments (YooKassa, универсальный /payments/webhook/*)
и api_stripe (Stripe /stripe/webhook), чтобы не дублировать логику.
"""

import logging

from .db import get_org_by_id, get_plan_by_code, update_org_plan

logger = logging.getLogger("sec_scanner")


def apply_webhook_plan_update(result: dict) -> None:
    """
    Обновить план организации по результату обработки webhook (Stripe или YooKassa).

    Ожидаемые ключи в result:
    - status: "success"
    - org_id: int
    - action: "subscription_created" | "subscription_updated" | "subscription_cancelled"
    - plan_code: str (для created/updated)
    - _idempotent: bool (опционально, флаг идемпотентного запроса)

    Ничего не делает, если status != "success" или нет org_id.
    Для идемпотентных запросов (_idempotent=True) пропускает обновление плана.
    """
    if result.get("status") != "success" or not result.get("org_id"):
        return

    # Skip plan update for idempotent requests (already processed)
    if result.get("_idempotent"):
        logger.info(
            "Skipping plan update for idempotent webhook (org_id=%s, action=%s)",
            result.get("org_id"),
            result.get("action"),
        )
        return

    org_id = result["org_id"]
    plan_code = result.get("plan_code")
    action = result.get("action")

    if action in ("subscription_created", "subscription_updated") and plan_code:
        org = get_org_by_id(org_id)
        if org:
            plan = get_plan_by_code(plan_code)
            if plan:
                # Skip if plan is already set to the same plan
                if org.get("plan_id") == plan["id"]:
                    logger.debug("Org %s already has plan %s, skipping update", org_id, plan_code)
                    return
                update_org_plan(org_id, plan["id"])
                logger.info("Updated org %s to plan %s", org_id, plan_code)
    elif action == "subscription_cancelled":
        free_plan = get_plan_by_code("free")
        if free_plan:
            org = get_org_by_id(org_id)
            if org:
                # Skip if plan is already set to free
                if org.get("plan_id") == free_plan["id"]:
                    logger.debug("Org %s already has free plan, skipping update", org_id)
                    return
            update_org_plan(org_id, free_plan["id"])
            logger.info("Downgraded org %s to free plan", org_id)
