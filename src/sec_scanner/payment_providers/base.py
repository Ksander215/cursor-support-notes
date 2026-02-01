"""
Base payment provider abstraction
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("sec_scanner")


class PaymentProvider(ABC):
    """Abstract base class for payment providers"""

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if payment provider is properly configured"""
        pass

    @abstractmethod
    def create_checkout_session(
        self,
        org_id: int,
        plan_code: str,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a checkout session for subscription

        Args:
            org_id: Organization ID
            plan_code: Plan code (free, starter, professional, enterprise)
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect after cancelled payment
            customer_email: Optional customer email

        Returns:
            Dict with session_id, url, and optional customer_id
        """
        pass

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> dict[str, Any]:
        """
        Verify webhook signature and return event data

        Args:
            payload: Raw webhook payload
            signature: Webhook signature from headers

        Returns:
            Event data dictionary
        """
        pass

    @abstractmethod
    def handle_webhook_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Handle webhook event and return action result

        Args:
            event: Event data from verify_webhook_signature

        Returns:
            Dict with status, action, org_id, plan_code, etc.
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get provider name (e.g., 'stripe', 'yookassa')"""
        pass


class PaymentProviderFactory:
    """Factory for creating payment providers based on country or configuration"""

    @staticmethod
    def get_provider(country_code: str | None = None) -> PaymentProvider:
        """
        Get appropriate payment provider based on country code

        Args:
            country_code: ISO 3166-1 alpha-2 country code (e.g., 'RU', 'US')

        Returns:
            PaymentProvider instance
        """
        # Import here to avoid circular imports
        from .stripe_provider import StripeProvider
        from .yookassa_provider import YooKassaProvider

        # Default to Stripe for international
        # Use YooKassa for Russia
        if country_code and country_code.upper() == "RU":
            provider = YooKassaProvider()
            if provider.is_configured():
                logger.info("Using YooKassa provider for Russian market")
                return provider
            else:
                logger.warning("YooKassa not configured, falling back to Stripe")

        # Default to Stripe
        provider = StripeProvider()
        if not provider.is_configured():
            logger.warning("Stripe not configured")
        return provider

    @staticmethod
    def get_provider_by_name(provider_name: str) -> PaymentProvider:
        """
        Get payment provider by name

        Args:
            provider_name: Provider name ('stripe' or 'yookassa')

        Returns:
            PaymentProvider instance
        """
        # Import here to avoid circular imports
        from .stripe_provider import StripeProvider
        from .yookassa_provider import YooKassaProvider

        if provider_name.lower() == "yookassa":
            return YooKassaProvider()
        elif provider_name.lower() == "stripe":
            return StripeProvider()
        else:
            raise ValueError(f"Unknown payment provider: {provider_name}")
