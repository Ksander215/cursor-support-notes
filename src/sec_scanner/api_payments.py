"""
Payment API endpoints supporting multiple payment providers (Stripe, YooKassa)
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .db import get_org_by_id, get_plan_by_code, update_org_plan
from .payment_providers import PaymentProviderFactory

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/payments", tags=["payments"])


class CheckoutSessionRequest(BaseModel):
    """Request to create a checkout session"""

    plan_code: str = Field(..., description="Plan code: free, starter, professional, enterprise")
    success_url: str = Field(
        default="https://sec-scanner.pro/app/settings?success=true",
        description="URL to redirect after successful payment",
    )
    cancel_url: str = Field(
        default="https://sec-scanner.pro/app/settings?canceled=true",
        description="URL to redirect after cancelled payment",
    )
    country_code: str | None = Field(
        default=None,
        description="ISO 3166-1 alpha-2 country code (e.g., 'RU', 'US'). Auto-detected if not provided.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "plan_code": "starter",
                "success_url": "https://sec-scanner.pro/app/settings?success=true",
                "cancel_url": "https://sec-scanner.pro/app/settings?canceled=true",
                "country_code": "RU",
            }
        }
    }


class CheckoutSessionResponse(BaseModel):
    """Response with checkout session URL"""

    session_id: str
    url: str
    customer_id: str | None = None
    provider: str = Field(..., description="Payment provider used: 'stripe' or 'yookassa'")


@router.post(
    "/checkout",
    response_model=CheckoutSessionResponse,
    summary="Create checkout session",
    description="Create a checkout session for subscribing to a plan. Automatically selects payment provider based on country (YooKassa for Russia, Stripe for others). Requires authentication via API key.",
)
def create_checkout_session(request: CheckoutSessionRequest, request_obj: Request):
    """
    Create a checkout session for subscription.

    Automatically selects payment provider:
    - YooKassa for Russian users (country_code='RU')
    - Stripe for international users

    Requires:
    - Valid API key in X-API-Key header
    - Organization associated with API key

    Returns checkout session URL for redirecting user to payment page.
    """
    # Get organization from API key (set by SaaS middleware)
    tenant_info = getattr(request_obj.state, "tenant_info", None)
    if not tenant_info:
        raise HTTPException(status_code=401, detail="Authentication required")

    org_id = tenant_info.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization not found")
    if org_id == 0:
        raise HTTPException(
            status_code=400,
            detail="Checkout requires an organization API key. Create a key in Settings → API keys.",
        )

    # Validate plan code
    valid_plans = ["free", "starter", "professional", "enterprise"]
    if request.plan_code not in valid_plans:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan code. Must be one of: {', '.join(valid_plans)}",
        )

    # Get payment provider based on country
    provider = PaymentProviderFactory.get_provider(request.country_code)

    if not provider.is_configured():
        raise HTTPException(
            status_code=503,
            detail=f"{provider.get_provider_name().capitalize()} is not configured",
        )

    # Get customer email if available
    customer_email = None
    # TODO: Get email from user profile or organization settings

    try:
        result = provider.create_checkout_session(
            org_id=org_id,
            plan_code=request.plan_code,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            customer_email=customer_email,
        )

        return CheckoutSessionResponse(
            session_id=result["session_id"],
            url=result["url"],
            customer_id=result.get("customer_id"),
            provider=provider.get_provider_name(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.post(
    "/webhook/stripe",
    summary="Stripe webhook endpoint",
    description="Webhook endpoint for Stripe events. Handles subscription updates, payment events, etc.",
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="stripe-signature"),
):
    """Handle Stripe webhook events"""
    provider = PaymentProviderFactory.get_provider_by_name("stripe")

    if not provider.is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    # Get raw request body
    payload = await request.body()

    try:
        # Verify webhook signature
        event = provider.verify_webhook_signature(payload, stripe_signature)

        # Process event
        result = provider.handle_webhook_event(event)

        # Update organization plan if needed
        _update_org_plan_from_result(result)

        return {"status": "success", "result": result}

    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@router.post(
    "/webhook/yookassa",
    summary="YooKassa webhook endpoint",
    description="Webhook endpoint for YooKassa events. Handles payment events, etc.",
)
async def yookassa_webhook(
    request: Request,
    x_request_id: str = Header(..., alias="x-request-id"),
):
    """Handle YooKassa webhook events"""
    provider = PaymentProviderFactory.get_provider_by_name("yookassa")

    if not provider.is_configured():
        raise HTTPException(status_code=503, detail="YooKassa is not configured")

    # Get raw request body
    payload = await request.body()

    # YooKassa uses HMAC-SHA256 signature in Authorization header or body
    # For simplicity, we'll use the payload directly and verify in provider
    try:
        # YooKassa sends signature in different ways, check Authorization header first
        auth_header = request.headers.get("authorization", "")
        signature = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""

        # If no signature in header, YooKassa may send it in the event itself
        # For now, we'll verify using webhook secret
        event = provider.verify_webhook_signature(payload, signature or x_request_id)

        # Process event
        result = provider.handle_webhook_event(event)

        # Update organization plan if needed
        _update_org_plan_from_result(result)

        return {"status": "success", "result": result}

    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


def _update_org_plan_from_result(result: dict):
    """Helper function to update organization plan from webhook result"""
    if result.get("status") == "success" and result.get("org_id"):
        org_id = result["org_id"]
        plan_code = result.get("plan_code")

        if (result.get("action") == "subscription_created" and plan_code) or (
            result.get("action") == "subscription_updated" and plan_code
        ):
            # Update organization plan
            org = get_org_by_id(org_id)
            if org:
                plan = get_plan_by_code(plan_code)
                if plan:
                    update_org_plan(org_id, plan["id"])
                    logger.info(f"Updated org {org_id} to plan {plan_code}")

        elif result.get("action") == "subscription_cancelled":
            # Downgrade to free plan
            free_plan = get_plan_by_code("free")
            if free_plan:
                update_org_plan(org_id, free_plan["id"])
                logger.info(f"Downgraded org {org_id} to free plan")
