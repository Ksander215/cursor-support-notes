import logging
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

logger = logging.getLogger("sec_scanner.notifications")


class NotificationProvider(ABC):
    """Base class for notification providers"""

    @abstractmethod
    def send(self, event: str, data: dict[str, Any], config: dict[str, Any]) -> bool:
        """
        Send notification.
        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate provider configuration.
        Returns (is_valid, error_message).
        """
        pass


class EmailProvider(NotificationProvider):
    """Email notification provider (SMTP)"""

    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        required = ["smtp_host", "smtp_port", "from_email", "to_emails"]
        for key in required:
            if key not in config:
                return False, f"Missing required config key: {key}"

        if not isinstance(config.get("to_emails"), list) or not config["to_emails"]:
            return False, "to_emails must be a non-empty list"

        return True, None

    def send(self, event: str, data: dict[str, Any], config: dict[str, Any]) -> bool:
        try:
            smtp_host = config["smtp_host"]
            smtp_port = int(config.get("smtp_port", 587))
            smtp_user = config.get("smtp_user")
            smtp_password = config.get("smtp_password")
            from_email = config["from_email"]
            to_emails = config["to_emails"]

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = self._get_subject(event, data)
            msg["From"] = from_email
            msg["To"] = ", ".join(to_emails)

            # Create email body
            text_body = self._get_text_body(event, data)
            html_body = self._get_html_body(event, data)

            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if smtp_user and smtp_password:
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)

            logger.info("Email notification sent successfully: event=%s", event)
            return True
        except Exception as e:
            logger.error("Failed to send email notification: %s", e, exc_info=True)
            return False

    def _get_subject(self, event: str, data: dict[str, Any]) -> str:
        if event == "scan_completed":
            target = data.get("target", "Unknown")
            score = data.get("overall_score")
            return f"Security Scan Completed: {target} (Score: {score})"
        elif event == "critical_vulnerability_found":
            return f"Critical Vulnerability Found: {data.get('target', 'Unknown')}"
        elif event == "high_vulnerability_found":
            return f"High Vulnerability Found: {data.get('target', 'Unknown')}"
        elif event == "quota_exceeded":
            return "Quota Exceeded"
        return f"Security Alert: {event}"

    def _get_text_body(self, event: str, data: dict[str, Any]) -> str:
        lines = [f"Event: {event}", ""]

        if event == "scan_completed":
            lines.extend(
                [
                    f"Target: {data.get('target', 'Unknown')}",
                    f"Score: {data.get('overall_score', 'N/A')}",
                    f"Risk Level: {data.get('risk_level', 'N/A')}",
                    f"Audit ID: {data.get('audit_id', 'N/A')}",
                    "",
                    f"View report: {data.get('report_url', 'N/A')}",
                ]
            )
        elif event in ["critical_vulnerability_found", "high_vulnerability_found"]:
            lines.extend(
                [
                    f"Target: {data.get('target', 'Unknown')}",
                    f"Vulnerabilities: {data.get('vulnerability_count', 0)}",
                    f"Audit ID: {data.get('audit_id', 'N/A')}",
                    "",
                    f"View report: {data.get('report_url', 'N/A')}",
                ]
            )
        elif event == "quota_exceeded":
            lines.extend(
                [
                    f"Organization: {data.get('org_name', 'Unknown')}",
                    f"Quota Type: {data.get('quota_type', 'Unknown')}",
                    f"Limit: {data.get('limit', 'N/A')}",
                    f"Used: {data.get('used', 'N/A')}",
                ]
            )

        return "\n".join(lines)

    def _get_html_body(self, event: str, data: dict[str, Any]) -> str:
        text_body = self._get_text_body(event, data)
        # Simple HTML conversion
        html = f"<html><body><pre>{text_body}</pre></body></html>"
        return html


class SlackProvider(NotificationProvider):
    """Slack webhook notification provider"""

    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        if "webhook_url" not in config:
            return False, "Missing required config key: webhook_url"
        return True, None

    def send(self, event: str, data: dict[str, Any], config: dict[str, Any]) -> bool:
        try:
            webhook_url = config["webhook_url"]

            # Build Slack message
            color = self._get_color(event, data)
            text = self._get_slack_text(event, data)

            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": self._get_title(event, data),
                        "text": text,
                        "footer": "sec-scanner.pro",
                        "ts": data.get("timestamp"),
                    }
                ]
            }

            with httpx.Client(timeout=10.0) as client:
                response = client.post(webhook_url, json=payload)
                response.raise_for_status()

            logger.info("Slack notification sent successfully: event=%s", event)
            return True
        except Exception as e:
            logger.error("Failed to send Slack notification: %s", e, exc_info=True)
            return False

    def _get_color(self, event: str, data: dict[str, Any]) -> str:
        if event == "scan_completed":
            score = data.get("overall_score", 0)
            if score >= 80:
                return "good"  # green
            elif score >= 60:
                return "warning"  # yellow
            return "danger"  # red
        elif event in ["critical_vulnerability_found", "quota_exceeded"]:
            return "danger"
        elif event == "high_vulnerability_found":
            return "warning"
        return "#36a64f"

    def _get_title(self, event: str, data: dict[str, Any]) -> str:
        if event == "scan_completed":
            return f"Security Scan Completed: {data.get('target', 'Unknown')}"
        elif event == "critical_vulnerability_found":
            return f"Critical Vulnerability Found: {data.get('target', 'Unknown')}"
        elif event == "high_vulnerability_found":
            return f"High Vulnerability Found: {data.get('target', 'Unknown')}"
        elif event == "quota_exceeded":
            return "Quota Exceeded"
        return f"Security Alert: {event}"

    def _get_slack_text(self, event: str, data: dict[str, Any]) -> str:
        lines = []

        if event == "scan_completed":
            lines.extend(
                [
                    f"*Target:* {data.get('target', 'Unknown')}",
                    f"*Score:* {data.get('overall_score', 'N/A')}",
                    f"*Risk Level:* {data.get('risk_level', 'N/A')}",
                    f"*Audit ID:* {data.get('audit_id', 'N/A')}",
                    f"<{data.get('report_url', '#')}|View Report>",
                ]
            )
        elif event in ["critical_vulnerability_found", "high_vulnerability_found"]:
            lines.extend(
                [
                    f"*Target:* {data.get('target', 'Unknown')}",
                    f"*Vulnerabilities:* {data.get('vulnerability_count', 0)}",
                    f"*Audit ID:* {data.get('audit_id', 'N/A')}",
                    f"<{data.get('report_url', '#')}|View Report>",
                ]
            )
        elif event == "quota_exceeded":
            lines.extend(
                [
                    f"*Organization:* {data.get('org_name', 'Unknown')}",
                    f"*Quota Type:* {data.get('quota_type', 'Unknown')}",
                    f"*Limit:* {data.get('limit', 'N/A')}",
                    f"*Used:* {data.get('used', 'N/A')}",
                ]
            )

        return "\n".join(lines)


class TelegramProvider(NotificationProvider):
    """Telegram bot notification provider"""

    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        required = ["bot_token", "chat_id"]
        for key in required:
            if key not in config:
                return False, f"Missing required config key: {key}"
        return True, None

    def send(self, event: str, data: dict[str, Any], config: dict[str, Any]) -> bool:
        try:
            bot_token = config["bot_token"]
            chat_id = config["chat_id"]

            text = self._get_telegram_text(event, data)
            api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }

            with httpx.Client(timeout=10.0) as client:
                response = client.post(api_url, json=payload)
                response.raise_for_status()

            logger.info("Telegram notification sent successfully: event=%s", event)
            return True
        except Exception as e:
            logger.error("Failed to send Telegram notification: %s", e, exc_info=True)
            return False

    def _get_telegram_text(self, event: str, data: dict[str, Any]) -> str:
        lines = [f"*{self._get_title(event, data)}*", ""]

        if event == "scan_completed":
            lines.extend(
                [
                    f"Target: `{data.get('target', 'Unknown')}`",
                    f"Score: `{data.get('overall_score', 'N/A')}`",
                    f"Risk Level: `{data.get('risk_level', 'N/A')}`",
                    f"Audit ID: `{data.get('audit_id', 'N/A')}`",
                    "",
                    f"[View Report]({data.get('report_url', '#')})",
                ]
            )
        elif event in ["critical_vulnerability_found", "high_vulnerability_found"]:
            lines.extend(
                [
                    f"Target: `{data.get('target', 'Unknown')}`",
                    f"Vulnerabilities: `{data.get('vulnerability_count', 0)}`",
                    f"Audit ID: `{data.get('audit_id', 'N/A')}`",
                    "",
                    f"[View Report]({data.get('report_url', '#')})",
                ]
            )
        elif event == "quota_exceeded":
            lines.extend(
                [
                    f"Organization: `{data.get('org_name', 'Unknown')}`",
                    f"Quota Type: `{data.get('quota_type', 'Unknown')}`",
                    f"Limit: `{data.get('limit', 'N/A')}`",
                    f"Used: `{data.get('used', 'N/A')}`",
                ]
            )

        return "\n".join(lines)

    def _get_title(self, event: str, data: dict[str, Any]) -> str:
        if event == "scan_completed":
            return f"Security Scan Completed: {data.get('target', 'Unknown')}"
        elif event == "critical_vulnerability_found":
            return "🔴 Critical Vulnerability Found"
        elif event == "high_vulnerability_found":
            return "🟠 High Vulnerability Found"
        elif event == "quota_exceeded":
            return "⚠️ Quota Exceeded"
        return f"Security Alert: {event}"


class WebhookProvider(NotificationProvider):
    """Generic webhook notification provider"""

    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        if "webhook_url" not in config:
            return False, "Missing required config key: webhook_url"
        return True, None

    def send(self, event: str, data: dict[str, Any], config: dict[str, Any]) -> bool:
        try:
            webhook_url = config["webhook_url"]
            secret = config.get("secret")

            payload = {
                "event": event,
                "timestamp": data.get("timestamp"),
                "data": data,
            }

            headers = {"Content-Type": "application/json"}
            if secret:
                # Add HMAC signature if secret is provided
                import hashlib
                import hmac
                import json

                payload_str = json.dumps(payload, sort_keys=True)
                signature = hmac.new(
                    secret.encode(), payload_str.encode(), hashlib.sha256
                ).hexdigest()
                headers["X-Signature"] = f"sha256={signature}"

            with httpx.Client(timeout=10.0) as client:
                response = client.post(webhook_url, json=payload, headers=headers)
                response.raise_for_status()

            logger.info("Webhook notification sent successfully: event=%s", event)
            return True
        except Exception as e:
            logger.error("Failed to send webhook notification: %s", e, exc_info=True)
            return False
