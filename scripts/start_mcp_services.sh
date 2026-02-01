#!/bin/bash
# Скрипт для запуска сервисов, необходимых для MCP
# Дата: 2026-01-28

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🚀 Запуск сервисов для MCP подключений"
echo "=========================================="
echo ""

# Проверяем Docker
echo "🐳 Проверяем Docker..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не найден. Установите Docker."
    exit 1
fi

# Ждем, пока Docker daemon полностью запустится
echo "⏳ Ожидаем запуск Docker daemon..."
MAX_WAIT=60
WAITED=0
while ! docker ps &> /dev/null; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "❌ Docker daemon не запустился за $MAX_WAIT секунд"
        echo "💡 Попробуйте: sudo service docker start"
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo "   Ожидание... ($WAITED/$MAX_WAIT сек)"
done
echo "✅ Docker daemon готов"
echo ""

# Проверяем docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose не найден. Установите docker-compose."
    exit 1
fi

# Запускаем PostgreSQL и Redis
echo "📦 Запускаем PostgreSQL и Redis..."
if [ -f "docker-compose.prod.yml" ]; then
    # Останавливаем ВСЕ сервисы проекта для освобождения сетей
    echo "🔧 Останавливаем все сервисы проекта..."
    docker-compose -f docker-compose.prod.yml down --remove-orphans 2>/dev/null || true

    # Ждем немного, чтобы Docker освободил ресурсы
    sleep 2

    # Удаляем контейнеры вручную, если они еще существуют
    echo "🔧 Удаляем контейнеры вручную..."
    docker rm -f fastapi-project_db_1 fastapi-project_redis_1 2>/dev/null || true

    # Удаляем старые сети проекта
    echo "🔧 Удаляем старые сети проекта..."
    # Удаляем сети, игнорируя ошибки (они могут не существовать или использоваться)
    docker network rm fastapi-project_data 2>/dev/null && echo "   ✅ Сеть fastapi-project_data удалена" || echo "   ⚠️  Сеть fastapi-project_data не удалена (будет пересоздана)"
    docker network rm fastapi-project_app 2>/dev/null && echo "   ✅ Сеть fastapi-project_app удалена" || echo "   ⚠️  Сеть fastapi-project_app не удалена (будет пересоздана)"
    echo ""

    # Запускаем сервисы с принудительным пересозданием для применения портов
    echo "🔄 Запускаем PostgreSQL и Redis с правильными портами..."
    # Используем --remove-orphans для удаления старых контейнеров
    docker-compose -f docker-compose.prod.yml up -d --force-recreate --remove-orphans db redis
    echo "✅ Сервисы запущены"
    echo ""

    # Ждем, пока сервисы станут здоровыми
    echo "⏳ Ожидаем готовность сервисов..."
    MAX_WAIT=120
    WAITED=0

    # Проверяем PostgreSQL
    while ! docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U sec_scanner -d sec_scanner &> /dev/null; do
        if [ $WAITED -ge $MAX_WAIT ]; then
            echo "⚠️  PostgreSQL не готов за $MAX_WAIT секунд (проверьте логи: docker-compose -f docker-compose.prod.yml logs db)"
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
            echo "⚠️  Redis не готов за $MAX_WAIT секунд (проверьте логи: docker-compose -f docker-compose.prod.yml logs redis)"
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
    echo "📊 Статус сервисов:"
    docker-compose -f docker-compose.prod.yml ps db redis
else
    echo "❌ Файл docker-compose.prod.yml не найден"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ Сервисы запущены!"
echo ""
echo "💡 Следующие шаги:"
echo "   1. Запустите тест: python3 scripts/test_mcp_connections.py"
echo "   2. Перезапустите Cursor IDE для применения MCP"
echo ""
