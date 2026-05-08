#!/bin/bash
# Fix Docker ports (supports WSL mode)
# Usage: ./fix_ports.sh [--wsl]

set -e

WSL_MODE=false
if [[ "$1" == "--wsl" ]]; then
    WSL_MODE=true
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔧 Fixing Docker ports..."
echo "========================"
echo ""

if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found"
    exit 1
fi

echo "📋 Current container status:"
docker-compose -f docker-compose.prod.yml ps db redis 2>/dev/null || echo "  Containers not running"
echo ""

if $WSL_MODE; then
    echo "📦 Step 1: Stopping containers..."
    docker-compose -f docker-compose.prod.yml down
    echo "✅ Containers stopped"

    echo "🔧 Step 2: Removing old networks..."
    docker network rm fastapi-project_data fastapi-project_app 2>/dev/null || true
    echo "✅ Old networks removed"

    echo "🔍 Step 3: Checking networks..."
    if docker network ls | grep -q fastapi-project; then
        echo "⚠️  Some networks still exist, forcing..."
        docker network rm fastapi-project_data fastapi-project_app 2>/dev/null || true
    fi

    echo "🔧 Step 4: Starting containers..."
    docker-compose -f docker-compose.prod.yml up -d db redis
    echo "✅ Containers started"
else
    echo "🛑 Stopping and removing containers..."
    docker-compose -f docker-compose.prod.yml rm -fs db redis
    echo "✅ Containers removed"

    echo "🔧 Starting containers..."
    docker-compose -f docker-compose.prod.yml up -d db redis
    echo "✅ Containers started"
fi

echo ""
echo "📋 Final status:"
docker-compose -f docker-compose.prod.yml ps db redis
docker-compose -f docker-compose.prod.yml stop db redis 2>/dev/null || true
docker-compose -f docker-compose.prod.yml rm -f db redis 2>/dev/null || true
echo "✅ Контейнеры остановлены и удалены"
echo ""

echo "🔄 Пересоздаем контейнеры с правильными портами..."
docker-compose -f docker-compose.prod.yml up -d db redis
echo "✅ Контейнеры пересозданы"
echo ""

echo "⏳ Ожидаем готовность сервисов..."
MAX_WAIT=120
WAITED=0

# Проверяем PostgreSQL
while ! docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U sec_scanner -d sec_scanner &> /dev/null; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "⚠️  PostgreSQL не готов за $MAX_WAIT секунд"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo "   Ожидание PostgreSQL... ($WAITED/$MAX_WAIT сек)"
done

if docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U sec_scanner -d sec_scanner &> /dev/null; then
    echo "✅ PostgreSQL готов"
fi

# Проверяем Redis
WAITED=0
while ! docker-compose -f docker-compose.prod.yml exec -T redis redis-cli ping &> /dev/null; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "⚠️  Redis не готов за $MAX_WAIT секунд"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo "   Ожидание Redis... ($WAITED/$MAX_WAIT сек)"
done

if docker-compose -f docker-compose.prod.yml exec -T redis redis-cli ping &> /dev/null; then
    echo "✅ Redis готов"
fi

echo ""
echo "📊 Статус сервисов после пересоздания:"
docker-compose -f docker-compose.prod.yml ps db redis
echo ""

echo "🔍 Проверяем проброс портов..."
echo ""

# Проверяем порт PostgreSQL
if docker port $(docker-compose -f docker-compose.prod.yml ps -q db) 5432 2>/dev/null | grep -q "127.0.0.1:5432"; then
    echo "✅ PostgreSQL порт проброшен: 127.0.0.1:5432->5432"
else
    echo "❌ PostgreSQL порт НЕ проброшен!"
    echo "   Проверьте docker-compose.prod.yml"
fi

# Проверяем порт Redis
if docker port $(docker-compose -f docker-compose.prod.yml ps -q redis) 6379 2>/dev/null | grep -q "127.0.0.1:6379"; then
    echo "✅ Redis порт проброшен: 127.0.0.1:6379->6379"
else
    echo "❌ Redis порт НЕ проброшен!"
    echo "   Проверьте docker-compose.prod.yml"
fi

echo ""
echo "======================================================"
echo "✅ Готово!"
echo ""
echo "💡 Следующие шаги:"
echo "   1. Проверьте подключения: python3 scripts/test_mcp_connections.py"
echo "   2. Перезапустите Cursor IDE для применения MCP"
echo ""
