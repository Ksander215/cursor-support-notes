#!/usr/bin/env bash
set -euo pipefail

# Исправление загрузки static API key
# Использование: ./scripts/vps_fix_static_key.sh

cd /opt/sec-scanner

echo "🔧 Исправление загрузки static API key"
echo "======================================="
echo ""

# Шаг 1: Проверка и очистка ключа в .env.production
echo "📋 Шаг 1: Проверка .env.production"
echo "-----------------------------------"

if [ ! -f .env.production ]; then
    echo "❌ .env.production не найден!"
    exit 1
fi

# Получить ключ и убрать пробелы/кавычки
ENV_KEY_LINE=$(grep "^SEC_SCANNER_API_KEY=" .env.production)
ENV_KEY=$(echo "$ENV_KEY_LINE" | cut -d'=' -f2- | sed "s/^['\"]//;s/['\"]$//" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

if [ -z "$ENV_KEY" ]; then
    echo "❌ SEC_SCANNER_API_KEY не найден или пуст"
    exit 1
fi

echo "✅ Ключ найден: ${ENV_KEY:0:30}..."
echo "   Длина: ${#ENV_KEY} символов"
echo ""

# Шаг 2: Проверить формат строки в файле
echo "📋 Шаг 2: Проверка формата строки"
echo "----------------------------------"
echo "Строка в файле:"
grep "^SEC_SCANNER_API_KEY=" .env.production | head -c 60
echo "..."
echo ""

# Шаг 3: Пересоздать контейнер с явной передачей переменной
echo "📋 Шаг 3: Пересоздание контейнера с явной передачей переменной"
echo "----------------------------------------------------------------"

echo "Останавливаю контейнер..."
docker compose -f docker-compose.prod.yml stop api

echo "Пересоздаю контейнер с явной передачей SEC_SCANNER_API_KEY..."
SEC_SCANNER_API_KEY="$ENV_KEY" docker compose -f docker-compose.prod.yml up -d --force-recreate api

echo "Ожидание запуска (10 секунд)..."
sleep 10

echo "Проверка загрузки переменных..."
CONTAINER_KEY=$(docker compose -f docker-compose.prod.yml exec -T api printenv | grep "^SEC_SCANNER_API_KEY=" | cut -d'=' -f2- || echo "")

if [ -z "$CONTAINER_KEY" ]; then
    echo "❌ Ключ все еще не загружен"
    echo ""
    echo "Попробуем другой способ - проверить логи контейнера..."
    docker compose -f docker-compose.prod.yml logs api | grep -i "SEC_SCANNER_API_KEY" | tail -5 || echo "Логи не найдены"
    echo ""
    echo "Используем ключ из .env.production напрямую для тестирования"
    USE_KEY="$ENV_KEY"
else
    echo "✅ Ключ загружен: ${CONTAINER_KEY:0:30}..."
    USE_KEY="$CONTAINER_KEY"

    # Проверить совпадение
    if [ "$ENV_KEY" != "$CONTAINER_KEY" ]; then
        echo "⚠️  Ключи не совпадают!"
        echo "   ENV: ${ENV_KEY:0:30}..."
        echo "   Container: ${CONTAINER_KEY:0:30}..."
    fi
fi

echo ""

# Шаг 4: Тест аутентификации
echo "📋 Шаг 4: Тест аутентификации"
echo "-----------------------------"
echo "Тестирую ключ: ${USE_KEY:0:20}..."

TEST_RESPONSE=$(curl -s -X GET "https://api.sec-scanner.pro/api/v1/quota" \
    -H "X-API-Key: $USE_KEY" 2>&1 || echo "ERROR")

if [[ "$TEST_RESPONSE" == *"quota"* ]] || [[ "$TEST_RESPONSE" == *"plan_code"* ]]; then
    echo "✅ Ключ работает для обычных запросов!"

    echo ""
    echo "Попытка создать API ключ через admin endpoint..."
    CREATE_RESPONSE=$(curl -s -X POST "https://api.sec-scanner.pro/api/v1/admin/api-keys" \
        -H "X-API-Key: $USE_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"org_name\": \"Test Payment Org $(date +%s)\",
            \"plan_code\": \"free\",
            \"key_name\": \"Test Payment Key\",
            \"is_admin\": false
        }" 2>&1 || echo "ERROR")

    if [[ "$CREATE_RESPONSE" == *"api_key"* ]]; then
        API_KEY=$(echo "$CREATE_RESPONSE" | grep -o '"api_key":"[^"]*' | cut -d'"' -f4)
        echo "✅ API ключ создан успешно!"
        echo ""
        echo "📝 Новый API ключ:"
        echo "   $API_KEY"
        echo ""
        echo "Используйте его для тестирования платежей!"
    else
        echo "❌ Ошибка создания ключа: $CREATE_RESPONSE"
    fi
elif [[ "$TEST_RESPONSE" == *"invalid API key"* ]]; then
    echo "❌ Ключ не принимается: invalid API key"
    echo ""
    echo "Возможные причины:"
    echo "  1. Ключ не загружен в контейнер"
    echo "  2. Формат ключа неверный"
    echo "  3. Используется DB-backed режим, и static key не работает"
    echo ""
    echo "💡 Решение: Создайте API ключ через веб-интерфейс:"
    echo "   https://sec-scanner.pro/app/settings"
else
    echo "⚠️  Неожиданный ответ: $TEST_RESPONSE"
fi
