"""
Configuration module — application settings and constants.
Extracts hardcoded values for easier configuration and maintenance.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Config:
    """Application configuration with sensible defaults."""

    COMMISSION_PERCENT: float = 20.0

    DEFAULT_SCAN_TIMEOUT: int = 300

    MAX_TARGETS_PER_REQUEST: int = 10

    DEFAULT_AUDIT_LIMIT: int = 50
    MAX_AUDIT_LIMIT: int = 500

    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    CACHE_TTL_AUDIT_RESULT: int = 86400
    CACHE_TTL_QUOTA: int = 300
    CACHE_TTL_AUDIT_LIST: int = 30
    CACHE_TTL_AUDIT_HISTORY: int = 600

    RATE_LIMIT_WINDOW: int = 60
    RATE_LIMIT_TTL: int = 70

    MAX_CONCURRENT_SCANS: int = 10

    BACKUP_RETENTION_DAYS: int = 30

    DIGEST_DELIVERY_HOUR: int = 9

    N8N_TIMEOUT_SECONDS: int = 30

    WEBHOOK_RETRY_ATTEMPTS: int = 3
    WEBHOOK_RETRY_DELAY_SECONDS: int = 60


config = Config()


DIGITAL_PRODUCTS = {
    "pdf_guide": {
        "name": "Безопасность API за 2 часа",
        "description": "PDF-гайд с практическими советами по защите API",
        "price_rub": 1500.0,
        "price_usd": 15.0,
        "file_name": "Безопасность_API_за_2_часа.pdf",
    },
    "ci_templates": {
        "name": "CI/CD шаблоны безопасности",
        "description": "Готовые шаблоны для GitHub Actions и GitLab CI",
        "price_rub": 2000.0,
        "price_usd": 20.0,
        "file_name": "ci-cd-security-templates.zip",
    },
    "audit": {
        "name": "Экспресс-аудит безопасности",
        "description": "Ручной аудит вашего API экспертом (до 2 часов)",
        "price_rub": 3000.0,
        "price_usd": 30.0,
        "file_name": None,
    },
}


def get_digital_product(product_id: str) -> dict[str, Any] | None:
    """Get digital product by ID."""
    return DIGITAL_PRODUCTS.get(product_id)


def get_all_digital_products() -> dict[str, dict[str, Any]]:
    """Get all digital products."""
    return DIGITAL_PRODUCTS.copy()
