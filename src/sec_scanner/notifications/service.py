import logging
from datetime import UTC, datetime
from typing import Any

from .. import db
from .providers import (
    EmailProvider,
    NotificationProvider,
    SlackProvider,
    TelegramProvider,
    WebhookProvider,
)

logger = logging.getLogger("sec_scanner.notifications")

_PROVIDERS: dict[str, NotificationProvider] = {
    "email": EmailProvider(),
    "slack": SlackProvider(),
    "telegram": TelegramProvider(),
    "webhook": WebhookProvider(),
}


class NotificationService:
    """Service for sending notifications"""

    @staticmethod
    def get_provider(channel: str) -> NotificationProvider | None:
        return _PROVIDERS.get(channel)

    @staticmethod
    def send_notification(
        org_id: int,
        event: str,
        data: dict[str, Any],
    ) -> int:
        """
        Send notification for an event to all enabled channels for the organization.
        Returns number of successful notifications sent.
        """
        # Get notification settings for organization
        settings_list = db.get_notification_settings(org_id=org_id)
        if not settings_list:
            logger.debug("No notification settings found for org_id=%s", org_id)
            return 0

        # Add timestamp to data
        data_with_timestamp = {
            **data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        success_count = 0
        for settings in settings_list:
            if not settings.get("enabled"):
                continue

            if event not in settings.get("events", []):
                continue

            channel = settings.get("channel")
            config = settings.get("config", {})

            provider = NotificationService.get_provider(channel)
            if not provider:
                logger.warning("Unknown notification channel: %s", channel)
                continue

            # Validate config
            is_valid, error = provider.validate_config(config)
            if not is_valid:
                logger.warning("Invalid config for channel %s: %s", channel, error)
                continue

            # Send notification
            try:
                success = provider.send(event, data_with_timestamp, config)
                if success:
                    success_count += 1
                    logger.info(
                        "Notification sent: org_id=%s channel=%s event=%s",
                        org_id,
                        channel,
                        event,
                    )
                else:
                    logger.warning(
                        "Failed to send notification: org_id=%s channel=%s event=%s",
                        org_id,
                        channel,
                        event,
                    )
            except Exception as e:
                logger.error(
                    "Error sending notification: org_id=%s channel=%s event=%s error=%s",
                    org_id,
                    channel,
                    event,
                    e,
                    exc_info=True,
                )

        return success_count


def send_notification(org_id: int, event: str, data: dict[str, Any]) -> int:
    """Convenience function to send notification"""
    return NotificationService.send_notification(org_id, event, data)
