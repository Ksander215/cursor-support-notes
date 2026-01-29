#!/bin/bash
# Скрипт для исправления портов Docker контейнеров
# Выполняется в WSL терминале
# Дата: 2026-01-29

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔧 Исправление портов Docker контейнеров"
echo "=========================================="
echo ""

# Шаг 1: Остановка всех контейнеров проекта
echo "📦 Шаг 1: Останавливаем контейнеры..."
docker-compose -f docker-compose.prod.yml down
echo "✅ Контейнеры остановлены"
echo ""

# Шаг 2: Удаление старых сетей
echo "🔧 Шаг 2: Удаляем старые Docker сети..."
docker network rm fastapi-project_data fastapi-project_app 2>/dev/null || true
echo "✅ Старые сети удалены"
echo ""

# Шаг 3: Проверка, что сети удалены
echo "🔍 Проверяем, что сети удалены..."
if docker network ls | grep -q fastapi-project; then
    echo "⚠️  Некоторые сети все еще существуют, удаляем принудительно..."
    docker network ls | grep fastapi-project | awk '{print $1}' | xargs -r docker network rm 2>/dev/null || true
fi
echo "✅ Сети проверены"
echo ""

# Шаг 4: Пересоздание контейнеров с правильными портами
echo "🔄 Шаг 3: Пересоздаем контейнеры с правильными портами..."
docker-compose -f docker-compose.prod.yml up -d --force-recreate db redis
echo "✅ Контейнеры пересозданы"
echo ""

# Шаг 5: Ожидание запуска
echo "⏳ Ожидаем запуск сервисов (15 секунд)..."
sleep 15
echo ""

# Шаг 6: Проверка статуса
echo "📊 Проверяем статус и порты:"
echo ""
docker-compose -f docker-compose.prod.yml ps db redis
echo ""

# Проверка портов
echo "🔍 Проверяем проброс портов:"
DB_PORTS=$(docker-compose -f docker-compose.prod.yml ps db | grep -oP '\d+\.\d+\.\d+\.\d+:\d+->\d+/tcp' || echo "")
REDIS_PORTS=$(docker-compose -f docker-compose.prod.yml ps redis | grep -oP '\d+\.\d+\.\d+\.\d+:\d+->\d+/tcp' || echo "")

if [[ -n "$DB_PORTS" ]] && [[ -n "$REDIS_PORTS" ]]; then
    echo "✅ PostgreSQL порты: $DB_PORTS"
    echo "✅ Redis порты: $REDIS_PORTS"
    echo ""
    echo "=========================================="
    echo "✅ Порты успешно проброшены!"
    echo ""
    echo "💡 Следующие шаги:"
    echo "   1. Проверьте подключения: python3 scripts/test_mcp_connections.py"
    echo "   2. Если все OK, можно добавить PostgreSQL/Docker/Redis MCP в .cursor/mcp.json"
    echo "   3. Перезапустите Cursor IDE"
else
    echo "❌ Порты не проброшены правильно!"
    echo ""
    echo "🔍 Проверяем конфигурацию docker-compose.prod.yml..."
    if grep -q "127.0.0.1:5432:5432" docker-compose.prod.yml && grep -q "127.0.0.1:6379:6379" docker-compose.prod.yml; then
        echo "✅ Конфигурация портов правильная в docker-compose.prod.yml"
        echo "⚠️  Возможно, нужно перезапустить Docker daemon"
        echo ""
        echo "Попробуйте:"
        echo "   sudo service docker restart"
        echo "   Затем запустите этот скрипт снова"
    else
        echo "❌ Проблема в конфигурации docker-compose.prod.yml"
        echo "   Проверьте, что порты указаны как:"
        echo "   - \"127.0.0.1:5432:5432\" для PostgreSQL"
        echo "   - \"127.0.0.1:6379:6379\" для Redis"
    fi
fi

echo ""
