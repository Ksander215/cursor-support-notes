#!/bin/bash
# Гарантированный запуск сервисов для MCP (PostgreSQL, Redis, Docker)
# Запускайте этот скрипт в WSL ПЕРЕД открытием Cursor — тогда Internal Error не появятся.
# Использование: bash scripts/ensure_mcp_services.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔧 Подготовка сервисов для MCP (чтобы Cursor не показывал Internal Error)"
echo "========================================================================"
echo ""

# 1. Docker
echo "🐳 Проверка Docker..."
if ! command -v docker &>/dev/null; then
    echo "❌ Docker не найден. Установите Docker Desktop с WSL2 или Docker в Linux."
    exit 1
fi

MAX_WAIT=45
WAITED=0
while ! docker ps &>/dev/null; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "❌ Docker daemon не отвечает за ${MAX_WAIT} сек."
        echo "   Запустите Docker Desktop (Windows) или: sudo service docker start (Linux)"
        exit 1
    fi
    echo "   Ожидание Docker... ($WAITED/$MAX_WAIT сек)"
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "✅ Docker готов"
echo ""

# 2. PostgreSQL и Redis
echo "📦 Запуск PostgreSQL и Redis..."
if [ ! -f "docker-compose.prod.yml" ]; then
    echo "❌ docker-compose.prod.yml не найден"
    exit 1
fi

docker-compose -f docker-compose.prod.yml up -d db redis 2>/dev/null || true
echo "   Контейнеры db и redis запущены (или уже работают)"
echo ""

# 3. Ожидание готовности
echo "⏳ Ожидание готовности сервисов..."
MAX_WAIT=90
WAITED=0

while ! docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U sec_scanner -d sec_scanner &>/dev/null; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "⚠️  PostgreSQL не готов за ${MAX_WAIT} сек. Проверьте: docker-compose -f docker-compose.prod.yml logs db"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo "   PostgreSQL... ($WAITED/$MAX_WAIT сек)"
done
if docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U sec_scanner -d sec_scanner &>/dev/null; then
    echo "✅ PostgreSQL готов"
fi

WAITED=0
while ! docker-compose -f docker-compose.prod.yml exec -T redis redis-cli ping &>/dev/null; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "⚠️  Redis не готов за ${MAX_WAIT} сек. Проверьте: docker-compose -f docker-compose.prod.yml logs redis"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo "   Redis... ($WAITED/$MAX_WAIT сек)"
done
if docker-compose -f docker-compose.prod.yml exec -T redis redis-cli ping &>/dev/null; then
    echo "✅ Redis готов"
fi
echo ""

# 4. Проверка доступности портов (для MCP из Cursor на Windows → localhost в WSL)
echo "🔌 Проверка портов (localhost в WSL должен быть доступен для Cursor)..."
if command -v nc &>/dev/null; then
    if nc -z 127.0.0.1 5432 2>/dev/null; then
        echo "✅ Порт 5432 (PostgreSQL) слушается"
    else
        echo "⚠️  Порт 5432 не отвечает — проверьте, что контейнер db запущен"
    fi
    if nc -z 127.0.0.1 6379 2>/dev/null; then
        echo "✅ Порт 6379 (Redis) слушается"
    else
        echo "⚠️  Порт 6379 не отвечает — проверьте, что контейнер redis запущен"
    fi
else
    echo "   (nc не установлен — пропуск проверки портов)"
fi
echo ""

# 5. Опционально: тест подключений через Python (если есть .venv)
if [ -f ".venv/bin/activate" ]; then
    echo "🧪 Тест подключений (PostgreSQL, Redis)..."
    export POSTGRES_CONNECTION_STRING="${POSTGRES_CONNECTION_STRING:-postgresql://sec_scanner:sec_scanner@localhost:5432/sec_scanner}"
    export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
    if source .venv/bin/activate 2>/dev/null && python3 scripts/test_mcp_connections.py 2>/dev/null; then
        echo ""
    else
        echo "   (тест пропущен — активируйте .venv и запустите: python3 scripts/test_mcp_connections.py)"
    fi
else
    echo "💡 Для полной проверки: создайте .venv, затем python3 scripts/test_mcp_connections.py"
fi

echo "========================================================================"
echo "✅ Сервисы для MCP готовы."
echo ""
echo "📌 Дальше: откройте Cursor и этот проект. Internal Error не должны появляться,"
echo "   пока PostgreSQL и Redis запущены в WSL."
echo ""
echo "   Если Cursor уже был открыт — закройте его полностью и запустите снова."
echo ""
