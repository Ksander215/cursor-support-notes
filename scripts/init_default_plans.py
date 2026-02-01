#!/usr/bin/env python3
"""
Скрипт для инициализации планов по умолчанию в БД
Можно запустить вручную если миграция не была применена
"""

import os
import sys

# Добавляем путь к проекту
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from src.sec_scanner.db import upsert_plan


def init_default_plans():
    """Инициализирует планы по умолчанию"""

    print("Инициализация планов по умолчанию...")

    # Free Plan
    free_id = upsert_plan(
        code="free",
        name="Free",
        requests_per_minute=10,
        monthly_audits_quota=10,
        concurrency_limit=1,
    )
    print(f"✅ Free Plan создан (ID: {free_id})")

    # Starter Plan ($29/месяц)
    starter_id = upsert_plan(
        code="starter",
        name="Starter",
        requests_per_minute=60,
        monthly_audits_quota=100,
        concurrency_limit=3,
    )
    print(f"✅ Starter Plan создан (ID: {starter_id})")

    # Professional Plan ($99/месяц)
    professional_id = upsert_plan(
        code="professional",
        name="Professional",
        requests_per_minute=120,
        monthly_audits_quota=500,
        concurrency_limit=10,
    )
    print(f"✅ Professional Plan создан (ID: {professional_id})")

    # Enterprise Plan (custom pricing)
    enterprise_id = upsert_plan(
        code="enterprise",
        name="Enterprise",
        requests_per_minute=None,  # unlimited
        monthly_audits_quota=None,  # unlimited
        concurrency_limit=None,  # unlimited
    )
    print(f"✅ Enterprise Plan создан (ID: {enterprise_id})")

    print("\n🎉 Все планы успешно инициализированы!")


if __name__ == "__main__":
    try:
        init_default_plans()
    except Exception as e:
        print(f"❌ Ошибка при инициализации планов: {e}")
        sys.exit(1)
