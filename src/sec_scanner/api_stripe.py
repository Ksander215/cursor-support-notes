"""
Stripe API endpoints for payment processing
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .db import get_org_by_id, get_plan_by_code, update_org_plan
from .stripe_service import StripeService

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/stripe", tags=["stripe"])


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "plan_code": "starter",
                "success_url": "https://sec-scanner.pro/app/settings?success=true",
                "cancel_url": "https://sec-scanner.pro/app/settings?canceled=true",
            }
        }
    }


class CheckoutSessionResponse(BaseModel):
    """Response with checkout session URL"""

    session_id: str
    url: str
    customer_id: str | None = None


class PortalSessionRequest(BaseModel):
    """Request to create a customer portal session"""

    return_url: str = Field(
        default="https://sec-scanner.pro/app/settings",
        description="URL to return after portal session",
    )


class PortalSessionResponse(BaseModel):
    """Response with portal session URL"""

    session_id: str
    url: str


@router.post(
    "/checkout",
    response_model=CheckoutSessionResponse,
    summary="Create Stripe checkout session",
    description="Create a Stripe Checkout Session for subscribing to a plan. Requires authentication via API key.",
)
def create_checkout_session(request: CheckoutSessionRequest, request_obj: Request):
    """
    Create a Stripe Checkout Session for subscription.

    Requires:
    - Valid API key in X-API-Key header
    - Organization associated with API key

    Returns checkout session URL for redirecting user to Stripe payment page.
    """
    if not StripeService.is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

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
            status_code=400, detail=f"Invalid plan code. Must be one of: {', '.join(valid_plans)}"
        )

    # Get customer email if available
    customer_email = None
    # TODO: Get email from user profile or organization settings

    try:
        result = StripeService.create_checkout_session(
            org_id=org_id,
            plan_code=request.plan_code,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            customer_email=customer_email,
        )

        return CheckoutSessionResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.post(
    "/portal",
    response_model=PortalSessionResponse,
    summary="Create Stripe customer portal session",
    description="Create a Stripe Customer Portal session for managing subscription. Requires authentication via API key.",
)
def create_portal_session(request: PortalSessionRequest, request_obj: Request):
    """
    Create a Stripe Customer Portal session for managing subscription.

    Requires:
    - Valid API key in X-API-Key header
    - Organization with active Stripe customer ID

    Returns portal session URL for redirecting user to Stripe customer portal.
    """
    if not StripeService.is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    # Get organization from API key
    tenant_info = getattr(request_obj.state, "tenant_info", None)
    if not tenant_info:
        raise HTTPException(status_code=401, detail="Authentication required")

    org_id = tenant_info.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization not found")

    # TODO: Get Stripe customer ID from organization metadata or separate table
    # For now, we'll need to store customer_id in organization metadata
    # customer_id = org.get("stripe_customer_id")
    # if not customer_id:
    #     raise HTTPException(status_code=400, detail="No Stripe customer found for this organization")

    # Temporary: return error until we implement customer_id storage
    raise HTTPException(
        status_code=501,
        detail="Customer portal not yet implemented. Store customer_id in organization metadata first.",
    )


@router.post(
    "/webhook",
    summary="Stripe webhook endpoint",
    description="Webhook endpoint for Stripe events. Handles subscription updates, payment events, etc.",
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="stripe-signature"),
):
    """
    Handle Stripe webhook events.

    This endpoint:
    - Verifies webhook signature
    - Processes subscription events (created, updated, deleted)
    - Processes payment events (succeeded, failed)
    - Updates organization plans in database

    Configure webhook URL in Stripe Dashboard:
    https://api.sec-scanner.pro/stripe/webhook
    """
    if not StripeService.is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    # Get raw request body
    payload = await request.body()

    try:
        # Verify webhook signature
        event = StripeService.verify_webhook_signature(payload, stripe_signature)

        # Process event
        result = StripeService.handle_webhook_event(event)

        # Update organization plan if needed
        if result.get("status") == "success" and result.get("org_id"):
            org_id = result["org_id"]
            plan_code = result.get("plan_code")

            if (
                result.get("action") == "subscription_created"
                and plan_code
                or result.get("action") == "subscription_updated"
                and plan_code
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

        return {"status": "success", "result": result}

    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")
