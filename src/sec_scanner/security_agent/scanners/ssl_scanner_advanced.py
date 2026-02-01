"""Расширенная проверка SSL (без shell-инъекций)."""

import re
import subprocess
from datetime import UTC, datetime

from ...targets import ensure_public_target_or_raise

_NOT_AFTER_RE = re.compile(r"notAfter=(.+)")


class AdvancedSSLScanner:
    """Проверка SSL через openssl без shell=True."""

    def scan(self, domain: str):
        try:
            ensure_public_target_or_raise(domain)
            checks = [
                self.check_expiration(domain),
            ]

            return {
                "grade": self.calculate_grade(checks),
                "checks": checks,
                "recommendations": self.generate_recommendations(checks),
            }
        except Exception as e:
            return {
                "error": str(e),
                "grade": "F",
                "checks": [],
                "recommendations": ["Проверьте доступность сайта"],
            }

    def _openssl_s_client(self, domain: str) -> str:
        # stdin: newline to make s_client exit after handshake
        proc = subprocess.run(
            ["openssl", "s_client", "-servername", domain, "-connect", f"{domain}:443"],
            input="\n",
            capture_output=True,
            text=True,
            timeout=20,
        )
        return proc.stdout

    def _openssl_x509_dates(self, pem_or_output: str) -> str:
        proc = subprocess.run(
            ["openssl", "x509", "-noout", "-dates"],
            input=pem_or_output,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return proc.stdout

    def check_expiration(self, domain: str):
        """Проверка срока действия SSL"""
        try:
            sclient_out = self._openssl_s_client(domain)
            dates_out = self._openssl_x509_dates(sclient_out)

            m = _NOT_AFTER_RE.search(dates_out)
            if not m:
                return {
                    "name": "SSL Expiry",
                    "status": "ERROR",
                    "details": "Не удалось извлечь notAfter из сертификата",
                }

            expiry_raw = m.group(1).strip()
            # openssl обычно: "Jun 12 12:00:00 2026 GMT"
            expiry_dt = datetime.strptime(expiry_raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
            days_left = (expiry_dt - datetime.now(UTC)).days

            status = "OK" if days_left >= 30 else "WARN" if days_left >= 7 else "ERROR"
            return {
                "name": "SSL Expiry",
                "status": status,
                "details": f"Действует до: {expiry_raw} (осталось дней: {days_left})",
                "days_left": days_left,
            }
        except Exception as e:
            return {"name": "SSL Expiry", "status": "ERROR", "details": f"Ошибка: {e}"}

    def calculate_grade(self, checks):
        # Простая шкала на базе срока действия
        exp = next((c for c in checks if c.get("name") == "SSL Expiry"), None)
        if not exp or exp.get("status") == "ERROR":
            return "F"
        days_left = int(exp.get("days_left", 0))
        if days_left >= 180:
            return "A"
        if days_left >= 30:
            return "B"
        if days_left >= 7:
            return "C"
        return "D"

    def generate_recommendations(self, checks):
        exp = next((c for c in checks if c.get("name") == "SSL Expiry"), None)
        if not exp:
            return ["Проверьте SSL сертификат"]
        if exp.get("status") == "WARN":
            return ["Обновите SSL сертификат в ближайшее время"]
        if exp.get("status") == "ERROR":
            return ["Срочно проверьте SSL сертификат (ошибка или скоро истекает)"]
        return ["Регулярно обновляйте SSL сертификат и мониторьте срок действия"]
