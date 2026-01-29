#!/bin/bash
# Скрипт для исправления портов Docker контейнеров
# Дата: 2026-01-29
# Использование: bash scripts/fix_ports_now.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔧 Исправление портов Docker контейнеров"
echo "=========================================="
echo ""

# Шаг 1: Остановка контейнеров
echo "📦 Шаг 1: Останавливаем контейнеры..."
docker-compose -f docker-compose.prod.yml down
echo "✅ Контейнеры остановлены"
echo ""

# Шаг 2: Удаление старых сетей
echo "🔧 Шаг 2: Удаляем старые сети..."
docker network rm fastapi-project_data fastapi-project_app 2>/dev/null || true
echo "✅ Старые сети удалены"
echo ""

# Шаг 3: Проверка конфигурации портов
echo "🔍 Шаг 3: Проверяем конфигурацию портов..."
if grep -q '127.0.0.1:5432:5432' docker-compose.prod.yml && grep -q '127.0.0.1:6379:6379' docker-compose.prod.yml; then
    echo "✅ Порты указаны правильно в docker-compose.prod.yml"
else
    echo "❌ ОШИБКА: Порты не указаны правильно в docker-compose.prod.yml"
    echo "   Ожидается: 127.0.0.1:5432:5432 и 127.0.0.1:6379:6379"
    exit 1
fi
echo ""

# Шаг 4: Пересоздание контейнеров
echo "🔄 Шаг 4: Пересоздаем контейнеры с правильными портами..."
docker-compose -f docker-compose.prod.yml up -d --force-recreate db redis
echo "✅ Контейнеры пересозданы"
echo ""

# Шаг 5: Ожидание готовности
echo "⏳ Шаг 5: Ожидаем готовность сервисов (15 секунд)..."
sleep 15
echo ""

# Шаг 6: Проверка статуса
echo "📊 Шаг 6: Проверяем статус контейнеров..."
docker-compose -f docker-compose.prod.yml ps db redis
echo ""

# Проверка портов
echo "🔍 Проверяем маппинг портов..."
PORTS_OUTPUT=$(docker-compose -f docker-compose.prod.yml ps db redis | grep -E "(5432|6379)" || true)

if echo "$PORTS_OUTPUT" | grep -q "127.0.0.1:5432->5432/tcp" && echo "$PORTS_OUTPUT" | grep -q "127.0.0.1:6379->6379/tcp"; then
    echo "✅ Порты проброшены правильно!"
    echo ""
    echo "📋 Статус портов:"
    echo "$PORTS_OUTPUT" | grep -E "(5432|6379)"
    echo ""
    echo "✅ УСПЕХ: Порты исправлены!"
    echo ""
    echo "💡 Следующие шаги:"
    echo "   1. Запустите тест: python3 scripts/test_mcp_connections.py"
    echo "   2. Перезапустите Cursor IDE для применения MCP"
else
    echo "❌ ОШИБКА: Порты все еще не проброшены правильно"
    echo ""
    echo "Текущий вывод:"
    echo "$PORTS_OUTPUT"
    echo ""
    echo "💡 Попробуйте альтернативный метод из FINAL_FIX_PORTS.md"
    exit 1
fi
