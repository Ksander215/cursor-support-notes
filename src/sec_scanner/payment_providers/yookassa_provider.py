"""
YooKassa payment provider implementation for Russian market
"""

import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx

from .base import PaymentProvider

logger = logging.getLogger("sec_scanner")

# YooKassa configuration
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_WEBHOOK_SECRET = os.getenv("YOOKASSA_WEBHOOK_SECRET", "")

# Plan mapping: our plan codes to YooKassa prices (in rubles)
PLAN_TO_YOOKASSA_PRICE: dict[str, float] = {
    "free": 0.0,
    "starter": 2900.0,  # ~$29 converted to RUB
    "professional": 9900.0,  # ~$99 converted to RUB
    "enterprise": 0.0,  # Custom pricing
}

# YooKassa API base URL
YOOKASSA_API_URL = "https://api.yookassa.ru/v3"


class YooKassaProvider(PaymentProvider):
    """YooKassa payment provider implementation for Russian market"""

    def __init__(self):
        """Initialize YooKassa provider"""
        self.shop_id = YOOKASSA_SHOP_ID
        self.secret_key = YOOKASSA_SECRET_KEY
        self.webhook_secret = YOOKASSA_WEBHOOK_SECRET
        self.api_url = YOOKASSA_API_URL

    def is_configured(self) -> bool:
        """Check if YooKassa is properly configured"""
        return bool(self.shop_id) and bool(self.secret_key) and bool(self.webhook_secret)

    def _get_auth_header(self) -> str:
        """Get Basic Auth header for YooKassa API"""
        credentials = f"{self.shop_id}:{self.secret_key}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _make_request(
        self, method: str, endpoint: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make HTTP request to YooKassa API"""
        url = f"{self.api_url}/{endpoint}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/json",
            "Idempotence-Key": hashlib.md5(
                json.dumps(data or {}, sort_keys=True).encode(),
                usedforsecurity=False,
            ).hexdigest(),
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                if method == "POST":
                    response = client.post(url, json=data, headers=headers)
                elif method == "GET":
                    response = client.get(url, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as e:
            logger.error(f"YooKassa API error: {e}")
            raise

    def create_checkout_session(
        self,
        org_id: int,
        plan_code: str,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a YooKassa payment for subscription

        Note: YooKassa doesn't have native subscriptions like Stripe,
        so we create a recurring payment that can be repeated monthly.
        """
        if not self.is_configured():
            raise ValueError(
                "YooKassa is not configured. Set YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, and YOOKASSA_WEBHOOK_SECRET"
            )

        price = PLAN_TO_YOOKASSA_PRICE.get(plan_code)
        if price is None:
            raise ValueError(f"YooKassa price not found for plan: {plan_code}")

        # For free plan, return success immediately
        if plan_code == "free":
            return {
                "session_id": f"free_{org_id}",
                "url": success_url,
                "customer_id": None,
            }

        # Create payment
        payment_data = {
            "amount": {
                "value": f"{price:.2f}",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": success_url,
            },
            "capture": True,
            "description": f"Подписка {plan_code} для организации {org_id}",
            "metadata": {
                "org_id": str(org_id),
                "plan_code": plan_code,
            },
        }

        if customer_email:
            payment_data["receipt"] = {
                "customer": {"email": customer_email},
                "items": [
                    {
                        "description": f"План {plan_code}",
                        "quantity": "1",
                        "amount": {"value": f"{price:.2f}", "currency": "RUB"},
                        "vat_code": 1,  # НДС не облагается
                    }
                ],
            }

        try:
            payment = self._make_request("POST", "payments", payment_data)

            logger.info(
                f"Created YooKassa payment: {payment.get('id')} for org_id={org_id}, plan={plan_code}"
            )

            confirmation_url = payment.get("confirmation", {}).get("confirmation_url")
            if not confirmation_url:
                raise ValueError("YooKassa payment created but no confirmation URL")

            return {
                "session_id": payment.get("id"),
                "url": confirmation_url,
                "customer_id": None,  # YooKassa doesn't use customer IDs like Stripe
            }

        except Exception as e:
            logger.error(f"Error creating YooKassa payment: {e}")
            raise

    def verify_webhook_signature(self, payload: bytes, signature: str) -> dict[str, Any]:
        """
        Verify YooKassa webhook signature

        YooKassa uses HMAC-SHA256 for webhook verification
        """
        if not self.webhook_secret:
            raise ValueError("YOOKASSA_WEBHOOK_SECRET is not set")

        try:
            # Calculate expected signature
            expected_signature = hmac.new(
                self.webhook_secret.encode(), payload, hashlib.sha256
            ).hexdigest()

            # Compare signatures
            if not hmac.compare_digest(signature, expected_signature):
                raise ValueError("Invalid YooKassa webhook signature")

            # Parse event data
            event = json.loads(payload.decode())
            return event

        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Invalid YooKassa webhook payload: {e}")
            raise

    def handle_webhook_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Handle YooKassa webhook event

        YooKassa sends payment events: payment.succeeded, payment.canceled, etc.
        """
        event_type = event.get("event")
        payment = event.get("object", {})

        logger.info(f"Processing YooKassa webhook event: {event_type}")

        try:
            if event_type == "payment.succeeded":
                # Payment succeeded
                payment_id = payment.get("id")
                metadata = payment.get("metadata", {})
                org_id = metadata.get("org_id")
                plan_code = metadata.get("plan_code")
                amount = payment.get("amount", {}).get("value")

                if org_id and plan_code:
                    return {
                        "status": "success",
                        "action": "subscription_created",  # Treat as subscription created
                        "org_id": int(org_id),
                        "plan_code": plan_code,
                        "subscription_id": payment_id,  # Use payment_id as subscription_id
                        "customer_id": None,
                        "amount_paid": float(amount) if amount else None,
                    }

            elif event_type == "payment.canceled":
                # Payment canceled
                payment_id = payment.get("id")
                metadata = payment.get("metadata", {})
                org_id = metadata.get("org_id")

                if org_id:
                    return {
                        "status": "success",
                        "action": "subscription_cancelled",
                        "org_id": int(org_id),
                        "subscription_id": payment_id,
                        "customer_id": None,
                    }

            else:
                logger.info(f"Unhandled YooKassa event type: {event_type}")
                return {
                    "status": "ignored",
                    "action": "unhandled_event",
                    "event_type": event_type,
                }

        except Exception as e:
            logger.error(f"Error processing YooKassa webhook event: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

        return {
            "status": "ignored",
            "action": "no_action",
        }

    def get_provider_name(self) -> str:
        """Get provider name"""
        return "yookassa"
