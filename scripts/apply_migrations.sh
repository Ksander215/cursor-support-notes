#!/bin/bash
# Скрипт для применения миграций БД
# Дата: 2026-01-29

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🗄️  Применение миграций БД"
echo "=========================="
echo ""

# Проверяем виртуальное окружение
if [ ! -d ".venv" ]; then
    echo "❌ Виртуальное окружение не найдено!"
    echo "   Запустите сначала: bash scripts/install_dependencies.sh"
    exit 1
fi

# Активируем виртуальное окружение
echo "📦 Активируем виртуальное окружение..."
source .venv/bin/activate
echo "✅ Виртуальное окружение активировано"
echo ""

# Проверяем подключение к БД
echo "🔍 Проверяем подключение к БД..."
python3 << 'EOF'
import sys
import os
sys.path.insert(0, os.path.abspath("."))
from src.sec_scanner.db import get_database_url, get_db
from sqlalchemy import text

try:
    url, is_sqlite = get_database_url()
    if is_sqlite:
        print("✅ Используется SQLite база данных")
    else:
        print(f"✅ Используется PostgreSQL: {url.split('@')[1] if '@' in url else 'localhost'}")

    # Проверяем подключение
    db = next(get_db())
    db.execute(text("SELECT 1"))
    db.close()
    print("✅ Подключение к БД успешно")
except Exception as e:
    print(f"❌ Ошибка подключения к БД: {e}")
    print("   Убедитесь, что PostgreSQL запущен:")
    print("   docker-compose -f docker-compose.prod.yml up -d db")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    exit 1
fi

echo ""

# Показываем текущую версию миграций
echo "📋 Текущая версия миграций:"
alembic current || echo "   (миграции еще не применены)"
echo ""

# Применяем миграции
echo "🚀 Применяем миграции..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Миграции успешно применены!"
    echo ""
    echo "📋 Текущая версия:"
    alembic current
else
    echo ""
    echo "❌ Ошибка при применении миграций!"
    exit 1
fi
