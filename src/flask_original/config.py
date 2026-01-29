"""Конфигурация безопасности."""

import os
import secrets
import warnings


def get_secret_key():
    """Получить секретный ключ безопасным способом."""
    # Пробуем получить из переменных окружения
    secret_key = os.environ.get("SECRET_KEY")

    if secret_key:
        return secret_key

    # Для production требуем явную установку
    if os.environ.get("FLASK_ENV") == "production":
        raise ValueError(
            "SECRET_KEY must be set in environment variables for production. "
            "Set FLASK_SECRET_KEY environment variable."
        )

    # Для разработки генерируем с предупреждением
    warnings.warn(
        "SECRET_KEY not set in environment variables. "
        "Using temporary key for development only. "
        "For production, set FLASK_SECRET_KEY environment variable.",
        UserWarning,
        stacklevel=2,
    )

    return secrets.token_hex(32)


class Config:
    """Базовая конфигурация."""

    # Секретный ключ
    SECRET_KEY = get_secret_key()

    # База данных
    DATABASE = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        "instance",
        "security_dashboard.db",
    )
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE}"

    # Безопасность
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    PERMANENT_SESSION_LIFETIME = 3600  # 1 час

    # CSRF защита
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = (
        secrets.token_hex(32)
        if not os.environ.get("FLASK_ENV") == "production"
        else get_secret_key()
    )


class DevelopmentConfig(Config):
    """Конфигурация разработки."""

    DEBUG = True
    TESTING = True


class ProductionConfig(Config):
    """Конфигурация продакшена."""

    DEBUG = False
    TESTING = False
    PREFERRED_URL_SCHEME = "https"


# Выбор конфигурации
FLASK_ENV = os.environ.get("FLASK_ENV", "development").lower()

if FLASK_ENV == "production":
    config = ProductionConfig()
else:
    config = DevelopmentConfig()
