"""
Audit Logging Service for security event tracking.

This module provides functions to log security-relevant events for
compliance and investigation purposes.

Usage:
    from src.sec_scanner.audit_log import log_event, AuditAction

    # Log an API key creation
    log_event(
        request=request,
        action=AuditAction.API_KEY_CREATED,
        resource_type="api_key",
        resource_id=api_key_id,
        org_id=org_id,
        details={"name": key_name, "is_admin": False},
        status="success",
    )
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import Request

from . import db

logger = logging.getLogger("sec_scanner.audit")


class AuditAction(str, Enum):
    """Enumeration of auditable security events."""

    # API Key events
    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"
    API_KEY_ROTATED = "api_key.rotated"
    API_KEY_USED = "api_key.used"  # Optional: high-volume, use sparingly

    # Authentication events
    AUTH_SUCCESS = "auth.success"
    AUTH_FAILURE = "auth.failure"
    AUTH_RATE_LIMITED = "auth.rate_limited"

    # Organization events
    ORG_CREATED = "organization.created"
    ORG_UPDATED = "organization.updated"
    ORG_DELETED = "organization.deleted"

    # Plan events
    PLAN_CHANGED = "plan.changed"
    PLAN_CREATED = "plan.created"
    PLAN_UPDATED = "plan.updated"

    # Settings events
    SETTINGS_UPDATED = "settings.updated"
    NOTIFICATION_CREATED = "notification.created"
    NOTIFICATION_UPDATED = "notification.updated"
    NOTIFICATION_DELETED = "notification.deleted"

    # Payment events
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"

    # Admin events
    ADMIN_ACCESS = "admin.access"
    ADMIN_ACTION = "admin.action"

    # Data access events
    DATA_EXPORT = "data.export"
    SENSITIVE_DATA_ACCESS = "data.sensitive_access"


class ActorType(str, Enum):
    """Type of actor performing the action."""

    USER = "user"
    API_KEY = "api_key"
    SYSTEM = "system"
    ANONYMOUS = "anonymous"
    WEBHOOK = "webhook"


class AuditStatus(str, Enum):
    """Result status of the audited action."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    PENDING = "pending"


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP from request, considering proxies."""
    # Check X-Forwarded-For (when behind proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP (original client)
        return forwarded.split(",")[0].strip()

    # Check X-Real-IP (alternative header)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client
    if request.client:
        return request.client.host

    return None


def _get_request_id(request: Request) -> str | None:
    """Get request ID from request state or headers."""
    # Try request state first (set by middleware)
    if hasattr(request.state, "request_id"):
        return request.state.request_id

    # Fall back to header
    return request.headers.get("X-Request-ID")


def _get_actor_info(request: Request) -> tuple[ActorType, str | None]:
    """Extract actor information from request."""
    # Check if we have auth context
    if hasattr(request.state, "auth") and request.state.auth:
        auth = request.state.auth
        if auth.api_key_id == "static":
            return ActorType.API_KEY, "static"
        return ActorType.API_KEY, auth.api_key_id

    # Check for API key in request
    if hasattr(request.state, "api_key_id") and request.state.api_key_id:
        return ActorType.API_KEY, request.state.api_key_id

    # Anonymous request
    return ActorType.ANONYMOUS, None


def log_event(
    request: Request | None,
    action: AuditAction | str,
    resource_type: str,
    resource_id: str | None = None,
    org_id: int | None = None,
    details: dict[str, Any] | None = None,
    status: AuditStatus | str = AuditStatus.SUCCESS,
    error_message: str | None = None,
    actor_type: ActorType | str | None = None,
    actor_id: str | None = None,
) -> int | None:
    """
    Log a security event to the audit log.

    Args:
        request: FastAPI Request object (optional, for extracting context)
        action: The action being logged (use AuditAction enum)
        resource_type: Type of resource affected (e.g., "api_key", "organization")
        resource_id: ID of the affected resource
        org_id: Organization ID context
        details: Additional action-specific details (JSON-serializable)
        status: Result status (success, failure, denied)
        error_message: Error message if status is failure
        actor_type: Override actor type detection
        actor_id: Override actor ID detection

    Returns:
        The ID of the created audit log entry, or None if logging failed

    Example:
        log_event(
            request=request,
            action=AuditAction.API_KEY_CREATED,
            resource_type="api_key",
            resource_id="ak_123",
            org_id=1,
            details={"name": "Production Key", "is_admin": False},
            status=AuditStatus.SUCCESS,
        )
    """
    try:
        # Convert enums to strings
        action_str = action.value if isinstance(action, AuditAction) else str(action)
        status_str = status.value if isinstance(status, AuditStatus) else str(status)

        # Extract request context
        client_ip: str | None = None
        user_agent: str | None = None
        request_id: str | None = None
        request_path: str | None = None
        request_method: str | None = None

        if request:
            client_ip = _get_client_ip(request)
            user_agent = request.headers.get("User-Agent")
            request_id = _get_request_id(request)
            request_path = str(request.url.path)
            request_method = request.method

            # Auto-detect actor if not provided
            if actor_type is None:
                detected_type, detected_id = _get_actor_info(request)
                actor_type = detected_type
                if actor_id is None:
                    actor_id = detected_id

        # Convert actor_type enum to string
        actor_type_str = (
            actor_type.value if isinstance(actor_type, ActorType) else str(actor_type or "system")
        )

        # Prepare log entry data
        log_data = {
            "timestamp": datetime.now(UTC),
            "action": action_str,
            "actor_type": actor_type_str,
            "actor_id": actor_id,
            "actor_ip": client_ip,
            "actor_user_agent": user_agent,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "org_id": org_id,
            "details": details,
            "status": status_str,
            "error_message": error_message,
            "request_id": request_id,
            "request_path": request_path,
            "request_method": request_method,
        }

        # Insert into database
        log_id = db.insert_audit_log(log_data)

        # Also log to standard logger for immediate visibility
        log_level = logging.WARNING if status_str in ("failure", "denied") else logging.INFO
        logger.log(
            log_level,
            f"AUDIT: {action_str} on {resource_type}/{resource_id or 'N/A'} "
            f"by {actor_type_str}/{actor_id or 'N/A'} - {status_str}",
            extra={
                "audit_action": action_str,
                "audit_resource": f"{resource_type}/{resource_id}",
                "audit_actor": f"{actor_type_str}/{actor_id}",
                "audit_status": status_str,
                "audit_ip": client_ip,
            },
        )

        return log_id

    except Exception as e:
        # Audit logging should never break the main flow
        logger.error(f"Failed to write audit log: {e}", exc_info=True)
        return None


def log_auth_success(request: Request, api_key_id: str, org_id: int | None = None) -> None:
    """Convenience function to log successful authentication."""
    log_event(
        request=request,
        action=AuditAction.AUTH_SUCCESS,
        resource_type="auth",
        resource_id=api_key_id,
        org_id=org_id,
        actor_type=ActorType.API_KEY,
        actor_id=api_key_id,
        status=AuditStatus.SUCCESS,
    )


def log_auth_failure(
    request: Request,
    reason: str,
    api_key_prefix: str | None = None,
) -> None:
    """Convenience function to log failed authentication."""
    log_event(
        request=request,
        action=AuditAction.AUTH_FAILURE,
        resource_type="auth",
        details={"reason": reason, "key_prefix": api_key_prefix},
        actor_type=ActorType.ANONYMOUS,
        status=AuditStatus.DENIED,
        error_message=reason,
    )


def log_api_key_created(
    request: Request,
    api_key_id: str,
    org_id: int,
    key_name: str | None = None,
    is_admin: bool = False,
) -> None:
    """Convenience function to log API key creation."""
    log_event(
        request=request,
        action=AuditAction.API_KEY_CREATED,
        resource_type="api_key",
        resource_id=api_key_id,
        org_id=org_id,
        details={"name": key_name, "is_admin": is_admin},
        status=AuditStatus.SUCCESS,
    )


def log_api_key_revoked(
    request: Request,
    api_key_id: str,
    org_id: int,
    reason: str | None = None,
) -> None:
    """Convenience function to log API key revocation."""
    log_event(
        request=request,
        action=AuditAction.API_KEY_REVOKED,
        resource_type="api_key",
        resource_id=api_key_id,
        org_id=org_id,
        details={"reason": reason},
        status=AuditStatus.SUCCESS,
    )


def log_settings_changed(
    request: Request,
    settings_type: str,
    settings_id: str,
    org_id: int,
    changes: dict[str, Any],
) -> None:
    """Convenience function to log settings changes."""
    log_event(
        request=request,
        action=AuditAction.SETTINGS_UPDATED,
        resource_type=settings_type,
        resource_id=settings_id,
        org_id=org_id,
        details={"changes": changes},
        status=AuditStatus.SUCCESS,
    )


def log_data_export(
    request: Request,
    export_type: str,
    export_format: str,
    resource_id: str,
    org_id: int | None = None,
) -> None:
    """Convenience function to log data exports."""
    log_event(
        request=request,
        action=AuditAction.DATA_EXPORT,
        resource_type=export_type,
        resource_id=resource_id,
        org_id=org_id,
        details={"format": export_format},
        status=AuditStatus.SUCCESS,
    )
