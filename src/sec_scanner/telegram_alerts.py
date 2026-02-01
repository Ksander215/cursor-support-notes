"""
Telegram Alerts Module
Отправка real-time уведомлений в Telegram
"""

import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramAlerts:
    """Класс для отправки уведомлений в Telegram"""

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = os.getenv("TELEGRAM_ALERTS_ENABLED", "false").lower() == "true"
        self.alert_level = os.getenv("TELEGRAM_ALERT_LEVEL", "WARNING").upper()

        if self.bot_token:
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        else:
            self.base_url = None

        # Уровни важности (для фильтрации)
        self.levels = {"DEBUG": 0, "INFO": 1, "SUCCESS": 2, "WARNING": 3, "ERROR": 4, "CRITICAL": 5}

    def _should_send(self, level: str) -> bool:
        """Проверить, нужно ли отправлять сообщение с данным уровнем"""
        if not self.enabled:
            return False

        message_level = self.levels.get(level.upper(), 0)
        threshold_level = self.levels.get(self.alert_level, 3)

        return message_level >= threshold_level

    async def send_message(
        self, message: str, parse_mode: str = "HTML", disable_notification: bool = False
    ) -> bool:
        """Отправить сообщение в Telegram"""
        if not self.enabled:
            logger.debug("Telegram alerts disabled, skipping")
            return False

        if not self.bot_token or not self.chat_id:
            logger.debug("Telegram bot token or chat_id not configured")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message[:4096],  # Telegram limit
                        "parse_mode": parse_mode,
                        "disable_notification": disable_notification,
                    },
                    timeout=10.0,
                )

                if response.status_code == 200:
                    logger.info("Telegram alert sent successfully")
                    return True
                else:
                    logger.error(f"Failed to send Telegram alert: {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e!s}")
            return False

    async def send_error(
        self, error: str, details: dict[str, Any] | None = None, critical: bool = False
    ):
        """Отправить уведомление об ошибке"""
        level = "CRITICAL" if critical else "ERROR"

        if not self._should_send(level):
            return

        icon = "🔴" if critical else "🟠"
        severity = "CRITICAL ERROR" if critical else "ERROR"

        message = f"{icon} <b>{severity}</b>\n\n"
        message += f"<b>Error:</b> {error}\n"
        message += f"<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"

        if details:
            message += "\n<b>Details:</b>\n"
            for key, value in details.items():
                message += f"• {key}: {value}\n"

        await self.send_message(message, disable_notification=not critical)

    async def send_warning(self, warning: str, details: dict[str, Any] | None = None):
        """Отправить предупреждение"""
        if not self._should_send("WARNING"):
            return

        message = "⚠️ <b>WARNING</b>\n\n"
        message += f"<b>Warning:</b> {warning}\n"
        message += f"<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"

        if details:
            message += "\n<b>Details:</b>\n"
            for key, value in details.items():
                message += f"• {key}: {value}\n"

        await self.send_message(message, disable_notification=True)

    async def send_success(self, message: str, details: dict[str, Any] | None = None):
        """Отправить уведомление об успешной операции"""
        if not self._should_send("SUCCESS"):
            return

        msg = "✅ <b>SUCCESS</b>\n\n"
        msg += f"<b>Message:</b> {message}\n"
        msg += f"<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"

        if details:
            msg += "\n<b>Details:</b>\n"
            for key, value in details.items():
                msg += f"• {key}: {value}\n"

        await self.send_message(msg, disable_notification=True)

    async def send_info(self, info: str, details: dict[str, Any] | None = None):
        """Отправить информационное сообщение"""
        if not self._should_send("INFO"):
            return

        message = "ℹ️ <b>INFO</b>\n\n"
        message += f"<b>Message:</b> {info}\n"
        message += f"<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"

        if details:
            message += "\n<b>Details:</b>\n"
            for key, value in details.items():
                message += f"• {key}: {value}\n"

        await self.send_message(message, disable_notification=True)

    async def send_metrics(self, metrics: dict[str, Any], title: str = "Metrics Report"):
        """Отправить метрики"""
        if not self._should_send("INFO"):
            return

        message = f"📊 <b>{title}</b>\n\n"
        message += f"<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"

        for key, value in metrics.items():
            message += f"• <b>{key}:</b> {value}\n"

        await self.send_message(message, disable_notification=True)

    async def send_security_alert(self, alert_type: str, severity: str, details: dict[str, Any]):
        """Отправить security alert"""
        # Проверка уровня по severity
        level_map = {
            "CRITICAL": "CRITICAL",
            "HIGH": "ERROR",
            "MEDIUM": "WARNING",
            "LOW": "INFO",
            "INFO": "INFO",
        }

        check_level = level_map.get(severity, "WARNING")
        if not self._should_send(check_level):
            return

        severity_icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵", "INFO": "ℹ️"}

        icon = severity_icons.get(severity, "⚠️")

        message = f"{icon} <b>SECURITY ALERT</b>\n\n"
        message += f"<b>Type:</b> {alert_type}\n"
        message += f"<b>Severity:</b> {severity}\n"
        message += f"<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"

        message += "<b>Details:</b>\n"
        for key, value in details.items():
            message += f"• {key}: {value}\n"

        # Для критичных алертов - со звуком
        critical = severity in ["CRITICAL", "HIGH"]
        await self.send_message(message, disable_notification=not critical)

    async def send_startup(self, environment: str = "production"):
        """Отправить уведомление о запуске приложения"""
        if not self._should_send("INFO"):
            return

        await self.send_success(
            message="🚀 SecScanner API Started",
            details={
                "environment": environment,
                "version": "1.0.0",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    async def send_shutdown(self, environment: str = "production"):
        """Отправить уведомление об остановке приложения"""
        if not self._should_send("WARNING"):
            return

        await self.send_warning(
            warning="⏹️ SecScanner API Shutting Down",
            details={"environment": environment, "timestamp": datetime.utcnow().isoformat()},
        )

    async def send_scan_complete(
        self, audit_id: str, target: str, risk_level: str, score: float | None = None
    ):
        """Отправить уведомление о завершении сканирования"""
        if not self._should_send("INFO"):
            return

        risk_icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "INFO": "ℹ️"}

        icon = risk_icons.get(risk_level, "🔍")

        message = f"{icon} <b>Scan Completed</b>\n\n"
        message += f"<b>Target:</b> {target}\n"
        message += f"<b>Audit ID:</b> {audit_id}\n"
        message += f"<b>Risk Level:</b> {risk_level}\n"

        if score is not None:
            message += f"<b>Score:</b> {score}/100\n"

        message += f"<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"

        # Для критичных и высоких рисков - со звуком
        critical = risk_level in ["CRITICAL", "HIGH"]
        await self.send_message(message, disable_notification=not critical)


@lru_cache
def get_telegram_alerts() -> TelegramAlerts:
    """Singleton instance для Telegram alerts"""
    return TelegramAlerts()


# Экспорт для удобного импорта
telegram_alerts = get_telegram_alerts()
