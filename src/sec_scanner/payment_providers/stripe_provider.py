"""
Stripe payment provider implementation
"""

import logging
from typing import Any

from ..stripe_service import StripeService
from .base import PaymentProvider

logger = logging.getLogger("sec_scanner")


class StripeProvider(PaymentProvider):
    """Stripe payment provider implementation"""

    def is_configured(self) -> bool:
        """Check if Stripe is properly configured"""
        return StripeService.is_configured()

    def create_checkout_session(
        self,
        org_id: int,
        plan_code: str,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe Checkout Session for subscription"""
        return StripeService.create_checkout_session(
            org_id=org_id,
            plan_code=plan_code,
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=customer_email,
        )

    def verify_webhook_signature(self, payload: bytes, signature: str) -> dict[str, Any]:
        """Verify Stripe webhook signature"""
        return StripeService.verify_webhook_signature(payload, signature)

    def handle_webhook_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Handle Stripe webhook event"""
        return StripeService.handle_webhook_event(event)

    def get_provider_name(self) -> str:
        """Get provider name"""
        return "stripe"
