"""
YooKassa payment provider implementation for Russian market.

Webhook verification: YooKassa does not send HMAC in headers for HTTP notifications.
Official docs recommend verifying by IP allowlist and/or by fetching payment status via API.
See: https://yookassa.ru/developers/using-api/webhooks#notifications-authenticity-verify
"""

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import uuid
from typing import Any

import httpx

from ..db import create_payment_record, get_payment_by_provider_id
from .base import PaymentProvider

logger = logging.getLogger("sec_scanner")

# YooKassa configuration
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_WEBHOOK_SECRET = os.getenv("YOOKASSA_WEBHOOK_SECRET", "")

# Official YooKassa notification IP ranges (Notification authentication)
# https://yookassa.ru/developers/using-api/webhooks#notifications-authenticity-verify
YOOKASSA_NOTIFICATION_IP_NETWORKS = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.154.128/25"),
    ipaddress.ip_network("2a02:5180::/32"),
]
YOOKASSA_NOTIFICATION_IP_HOSTS = [
    "77.75.156.11",
    "77.75.156.35",
]

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
        """Check if YooKassa is properly configured (shop_id and secret_key; webhook_secret optional for IP-based webhook verification)."""
        return bool(self.shop_id) and bool(self.secret_key)

    def _get_auth_header(self) -> str:
        """Get Basic Auth header for YooKassa API"""
        credentials = f"{self.shop_id}:{self.secret_key}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Make HTTP request to YooKassa API.

        Args:
            method: HTTP method (POST, GET, etc.)
            endpoint: API endpoint (e.g., "payments")
            data: Request body data (for POST requests)
            idempotency_key: Optional UUID for idempotency (if not provided, generates MD5 hash from data)
        """
        url = f"{self.api_url}/{endpoint}"
        # Use provided idempotency_key or generate MD5 hash from data (fallback for backward compatibility)
        if idempotency_key:
            idempotence_key_value = idempotency_key
        else:
            idempotence_key_value = hashlib.md5(
                json.dumps(data or {}, sort_keys=True).encode(),
                usedforsecurity=False,
            ).hexdigest()

        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/json",
            "Idempotence-Key": idempotence_key_value,
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

        # Generate UUID for idempotency key
        idempotency_key = str(uuid.uuid4())

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
            payment = self._make_request(
                "POST", "payments", payment_data, idempotency_key=idempotency_key
            )

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

    def _is_yookassa_ip(self, client_ip: str) -> bool:
        """Check if the given IP is from official YooKassa notification servers."""
        if not client_ip:
            return False
        try:
            ip = ipaddress.ip_address(client_ip.strip())
        except ValueError:
            return False
        for net in YOOKASSA_NOTIFICATION_IP_NETWORKS:
            if ip in net:
                return True
        if ip.compressed in YOOKASSA_NOTIFICATION_IP_HOSTS:
            return True
        return False

    def verify_webhook_signature(
        self, payload: bytes, signature: str, *, client_ip: str | None = None
    ) -> dict[str, Any]:
        """
        Verify YooKassa webhook request.

        YooKassa does not send HMAC in headers. Official docs recommend verifying
        by IP allowlist (see Notification authentication). Optionally, if
        YOOKASSA_WEBHOOK_SECRET is set and a custom signature is sent (e.g. in a
        header), HMAC is checked; otherwise client_ip is required and must be in
        the official YooKassa IP list.
        """
        try:
            # If caller provided a non-empty signature (e.g. from a custom header),
            # verify HMAC. Otherwise require client_ip for IP allowlist check.
            if signature and self.webhook_secret:
                expected = hmac.new(
                    self.webhook_secret.encode(), payload, hashlib.sha256
                ).hexdigest()
                if hmac.compare_digest(signature, expected):
                    event = json.loads(payload.decode())
                    if (
                        event.get("type") == "notification"
                        and "event" in event
                        and "object" in event
                    ):
                        return event
                    raise ValueError("Invalid YooKassa notification body")
                raise ValueError("Invalid YooKassa webhook signature")

            if not client_ip:
                raise ValueError(
                    "YooKassa webhook verification requires client IP (or signature). "
                    "Ensure the request is sent from YooKassa servers or provide signature."
                )
            if not self._is_yookassa_ip(client_ip):
                logger.warning(f"YooKassa webhook from non-allowlisted IP: {client_ip}")
                raise ValueError("Notification must be sent from YooKassa IP range")

            event = json.loads(payload.decode())
            if event.get("type") != "notification" or "event" not in event or "object" not in event:
                raise ValueError("Invalid YooKassa notification body")
            return event

        except (ValueError, json.JSONDecodeError) as e:
            logger.error("Invalid YooKassa webhook: %s", e)
            raise

    def handle_webhook_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Handle YooKassa webhook event with idempotency check.

        YooKassa sends payment events: payment.succeeded, payment.canceled, etc.
        If a payment with the same payment_id was already processed, returns
        the previous result without processing again (idempotency).
        """
        event_type = event.get("event")
        payment = event.get("object", {})
        payment_id = payment.get("id")

        logger.info(f"Processing YooKassa webhook event: {event_type}, payment_id={payment_id}")

        # Idempotency check: if payment was already processed, return previous result
        if payment_id:
            existing_payment = get_payment_by_provider_id("yookassa", payment_id)
            if existing_payment:
                logger.info(
                    f"Payment {payment_id} already processed (idempotency), returning previous result"
                )
                payment_metadata = existing_payment.get("payment_metadata", {})
                return {
                    "status": "success",
                    "action": (
                        "subscription_created"
                        if existing_payment["status"] == "succeeded"
                        else "subscription_cancelled"
                        if existing_payment["status"] == "canceled"
                        else "no_action"
                    ),
                    "org_id": existing_payment["org_id"],
                    "plan_code": existing_payment.get("plan_code"),
                    "subscription_id": payment_id,
                    "customer_id": None,
                    "amount_paid": existing_payment.get("amount"),
                    "_idempotent": True,  # Flag to indicate this is a duplicate
                }

        try:
            if event_type == "payment.succeeded":
                # Payment succeeded
                metadata = payment.get("metadata", {})
                org_id = metadata.get("org_id")
                plan_code = metadata.get("plan_code")
                amount = payment.get("amount", {}).get("value")
                currency = payment.get("amount", {}).get("currency", "RUB")

                if org_id and plan_code:
                    # Save payment record for idempotency
                    create_payment_record(
                        provider="yookassa",
                        payment_id=payment_id,
                        org_id=int(org_id),
                        plan_code=plan_code,
                        amount=float(amount) if amount else None,
                        currency=currency,
                        status="succeeded",
                        event_type=event_type,
                        payment_metadata=payment,
                    )

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
                metadata = payment.get("metadata", {})
                org_id = metadata.get("org_id")
                amount = payment.get("amount", {}).get("value")
                currency = payment.get("amount", {}).get("currency", "RUB")

                if org_id:
                    # Save payment record for idempotency
                    create_payment_record(
                        provider="yookassa",
                        payment_id=payment_id,
                        org_id=int(org_id),
                        plan_code=metadata.get("plan_code"),
                        amount=float(amount) if amount else None,
                        currency=currency,
                        status="canceled",
                        event_type=event_type,
                        payment_metadata=payment,
                    )

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
