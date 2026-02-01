"""
Stripe integration service for handling payments and subscriptions
"""

import logging
import os
from typing import Any

import stripe

logger = logging.getLogger("sec_scanner")

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Plan mapping: our plan codes to Stripe price IDs
PLAN_TO_STRIPE_PRICE: dict[str, str] = {
    "free": os.getenv("STRIPE_PRICE_FREE", ""),
    "starter": os.getenv("STRIPE_PRICE_STARTER", ""),
    "professional": os.getenv("STRIPE_PRICE_PROFESSIONAL", ""),
    "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE", ""),
}


class StripeService:
    """Service for handling Stripe payments and subscriptions"""

    @staticmethod
    def is_configured() -> bool:
        """Check if Stripe is properly configured"""
        return bool(stripe.api_key) and bool(STRIPE_WEBHOOK_SECRET)

    @staticmethod
    def create_checkout_session(
        org_id: int,
        plan_code: str,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a Stripe Checkout Session for subscription

        Args:
            org_id: Organization ID
            plan_code: Plan code (free, starter, professional, enterprise)
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect after cancelled payment
            customer_email: Optional customer email

        Returns:
            Checkout session object
        """
        if not StripeService.is_configured():
            raise ValueError(
                "Stripe is not configured. Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET"
            )

        stripe_price_id = PLAN_TO_STRIPE_PRICE.get(plan_code)
        if not stripe_price_id:
            raise ValueError(f"Stripe price ID not found for plan: {plan_code}")

        try:
            # Create or retrieve customer
            customer = None
            if customer_email:
                # Try to find existing customer
                customers = stripe.Customer.list(email=customer_email, limit=1)
                if customers.data:
                    customer = customers.data[0]
                else:
                    # Create new customer
                    customer = stripe.Customer.create(
                        email=customer_email, metadata={"org_id": str(org_id)}
                    )

            # Create checkout session
            session = stripe.checkout.Session.create(
                customer=customer.id if customer else None,
                customer_email=customer_email if not customer else None,
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": stripe_price_id,
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "org_id": str(org_id),
                    "plan_code": plan_code,
                },
                subscription_data={
                    "metadata": {
                        "org_id": str(org_id),
                        "plan_code": plan_code,
                    }
                },
            )

            logger.info(
                f"Created Stripe checkout session: {session.id} for org_id={org_id}, plan={plan_code}"
            )
            return {
                "session_id": session.id,
                "url": session.url,
                "customer_id": customer.id if customer else None,
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating checkout session: {e}")
            raise

    @staticmethod
    def create_portal_session(customer_id: str, return_url: str) -> dict[str, Any]:
        """
        Create a Stripe Customer Portal session for managing subscription

        Args:
            customer_id: Stripe customer ID
            return_url: URL to return after portal session

        Returns:
            Portal session object
        """
        if not StripeService.is_configured():
            raise ValueError("Stripe is not configured")

        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )

            logger.info(f"Created Stripe portal session: {session.id} for customer={customer_id}")
            return {
                "session_id": session.id,
                "url": session.url,
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating portal session: {e}")
            raise

    @staticmethod
    def handle_webhook_event(event: dict[str, Any]) -> dict[str, Any]:
        """
        Handle Stripe webhook event

        Args:
            event: Stripe event object

        Returns:
            Result dictionary with status and message
        """
        event_type = event.get("type")
        data = event.get("data", {}).get("object", {})

        logger.info(f"Processing Stripe webhook event: {event_type}")

        try:
            if event_type == "checkout.session.completed":
                # Subscription created
                subscription_id = data.get("subscription")
                customer_id = data.get("customer")
                metadata = data.get("metadata", {})
                org_id = metadata.get("org_id")
                plan_code = metadata.get("plan_code")

                if org_id and plan_code:
                    return {
                        "status": "success",
                        "action": "subscription_created",
                        "org_id": int(org_id),
                        "plan_code": plan_code,
                        "subscription_id": subscription_id,
                        "customer_id": customer_id,
                    }

            elif event_type == "customer.subscription.updated":
                # Subscription updated (plan changed, etc.)
                subscription_id = data.get("id")
                customer_id = data.get("customer")
                metadata = data.get("metadata", {})
                org_id = metadata.get("org_id")
                plan_code = metadata.get("plan_code")
                status = data.get("status")

                if org_id and plan_code:
                    return {
                        "status": "success",
                        "action": "subscription_updated",
                        "org_id": int(org_id),
                        "plan_code": plan_code,
                        "subscription_id": subscription_id,
                        "customer_id": customer_id,
                        "subscription_status": status,
                    }

            elif event_type == "customer.subscription.deleted":
                # Subscription cancelled
                subscription_id = data.get("id")
                customer_id = data.get("customer")
                metadata = data.get("metadata", {})
                org_id = metadata.get("org_id")

                if org_id:
                    return {
                        "status": "success",
                        "action": "subscription_cancelled",
                        "org_id": int(org_id),
                        "subscription_id": subscription_id,
                        "customer_id": customer_id,
                    }

            elif event_type == "invoice.payment_succeeded":
                # Payment succeeded
                subscription_id = data.get("subscription")
                customer_id = data.get("customer")
                amount_paid = data.get("amount_paid")

                return {
                    "status": "success",
                    "action": "payment_succeeded",
                    "subscription_id": subscription_id,
                    "customer_id": customer_id,
                    "amount_paid": amount_paid,
                }

            elif event_type == "invoice.payment_failed":
                # Payment failed
                subscription_id = data.get("subscription")
                customer_id = data.get("customer")

                return {
                    "status": "success",
                    "action": "payment_failed",
                    "subscription_id": subscription_id,
                    "customer_id": customer_id,
                }

            else:
                logger.info(f"Unhandled Stripe event type: {event_type}")
                return {
                    "status": "ignored",
                    "action": "unhandled_event",
                    "event_type": event_type,
                }

        except Exception as e:
            logger.error(f"Error processing Stripe webhook event: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

        return {
            "status": "ignored",
            "action": "no_action",
        }

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> dict[str, Any]:
        """
        Verify Stripe webhook signature

        Args:
            payload: Raw request body
            signature: Stripe signature header

        Returns:
            Event object if valid, raises exception if invalid
        """
        if not STRIPE_WEBHOOK_SECRET:
            raise ValueError("STRIPE_WEBHOOK_SECRET is not set")

        try:
            event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
            return event
        except ValueError as e:
            logger.error(f"Invalid payload in Stripe webhook: {e}")
            raise
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid signature in Stripe webhook: {e}")
            raise
