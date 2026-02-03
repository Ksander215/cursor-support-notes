#!/usr/bin/env bash
set -euo pipefail

# Исправление загрузки переменных окружения и тестирование Stripe
# Использование: ./scripts/vps_fix_env_and_test.sh

cd /opt/sec-scanner

echo "🔧 Исправление загрузки переменных окружения"
echo "============================================="
echo ""

# Шаг 1: Проверка .env.production
echo "📋 Шаг 1: Проверка .env.production"
echo "-----------------------------------"
if [ ! -f .env.production ]; then
    echo "❌ .env.production не найден!"
    exit 1
fi

ENV_KEY=$(grep "^SEC_SCANNER_API_KEY=" .env.production | cut -d'=' -f2-)
if [ -z "$ENV_KEY" ]; then
    echo "❌ SEC_SCANNER_API_KEY не найден в .env.production"
    exit 1
fi

echo "✅ Ключ найден в .env.production: ${ENV_KEY:0:30}..."
echo ""

# Шаг 2: Пересоздание контейнера API для загрузки переменных
echo "📋 Шаг 2: Пересоздание контейнера API"
echo "-------------------------------------"
echo "Останавливаю контейнер API..."
docker compose -f docker-compose.prod.yml stop api

echo "Пересоздаю контейнер с переменными из .env.production..."
docker compose -f docker-compose.prod.yml up -d --force-recreate api

echo "Ожидание запуска (10 секунд)..."
sleep 10

echo "Проверка загрузки переменных..."
CONTAINER_KEY=$(docker compose -f docker-compose.prod.yml exec -T api printenv | grep "^SEC_SCANNER_API_KEY=" | cut -d'=' -f2- || echo "")

if [ -z "$CONTAINER_KEY" ]; then
    echo "❌ Ключ все еще не загружен в контейнер"
    echo ""
    echo "Попробуем другой способ - пересоздать через down/up..."
    docker compose -f docker-compose.prod.yml stop api
    docker compose -f docker-compose.prod.yml rm -f api
    docker compose -f docker-compose.prod.yml up -d api
    sleep 10

    CONTAINER_KEY=$(docker compose -f docker-compose.prod.yml exec -T api printenv | grep "^SEC_SCANNER_API_KEY=" | cut -d'=' -f2- || echo "")

    if [ -z "$CONTAINER_KEY" ]; then
        echo "❌ Ключ не загружается. Используем ключ из .env.production напрямую"
        USE_KEY="$ENV_KEY"
    else
        echo "✅ Ключ загружен после пересоздания: ${CONTAINER_KEY:0:30}..."
        USE_KEY="$CONTAINER_KEY"
    fi
else
    echo "✅ Ключ загружен в контейнер: ${CONTAINER_KEY:0:30}..."
    USE_KEY="$CONTAINER_KEY"
fi

echo ""

# Шаг 3: Создать тестовый API ключ
echo "📋 Шаг 3: Создание тестового API ключа"
echo "--------------------------------------"
echo "Создание тестовой организации..."
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
    ORG_ID=$(echo "$CREATE_RESPONSE" | grep -o '"org_id":[0-9]*' | cut -d':' -f2)
    echo "✅ API ключ создан успешно!"
    echo "   Org ID: $ORG_ID"
    echo "   API Key: ${API_KEY:0:30}..."
elif [[ "$CREATE_RESPONSE" == *"admin API key required"* ]]; then
    echo "❌ Static key не является admin ключом"
    echo "   Ответ: $CREATE_RESPONSE"
    echo ""
    echo "💡 Решение: Используйте существующий API ключ из веб-интерфейса"
    echo "   или создайте admin ключ через БД"
    exit 1
else
    echo "❌ Ошибка создания API ключа"
    echo "   Ответ: $CREATE_RESPONSE"
    exit 1
fi

echo ""

# Шаг 4: Создать checkout session
echo "📋 Шаг 4: Создание Checkout Session"
echo "-----------------------------------"
echo "Создание checkout session для плана 'starter'..."
CHECKOUT_RESPONSE=$(curl -s -X POST "https://api.sec-scanner.pro/payments/checkout" \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "plan_code": "starter",
        "country_code": "US",
        "success_url": "https://sec-scanner.pro/app/settings?success=true",
        "cancel_url": "https://sec-scanner.pro/app/settings?canceled=true"
    }' 2>&1 || echo "ERROR")

if [[ "$CHECKOUT_RESPONSE" == *"url"* ]]; then
    CHECKOUT_URL=$(echo "$CHECKOUT_RESPONSE" | grep -o '"url":"[^"]*' | cut -d'"' -f4)
    SESSION_ID=$(echo "$CHECKOUT_RESPONSE" | grep -o '"session_id":"[^"]*' | cut -d'"' -f4)
    PROVIDER=$(echo "$CHECKOUT_RESPONSE" | grep -o '"provider":"[^"]*' | cut -d'"' -f4)

    echo "✅ Checkout session создан!"
    echo ""
    echo "📊 Информация:"
    echo "   Session ID: $SESSION_ID"
    echo "   Provider: $PROVIDER"
    echo ""
    echo "🌐 URL для оплаты:"
    echo "   $CHECKOUT_URL"
    echo ""
    echo "💳 Тестовая карта Stripe:"
    echo "   Номер: 4242 4242 4242 4242"
    echo "   Срок: 12/25 (любая будущая дата)"
    echo "   CVC: 123"
    echo "   ZIP: 12345"
    echo ""
    echo "📝 Инструкции:"
    echo "   1. Откройте URL выше в браузере"
    echo "   2. Заполните форму тестовой картой"
    echo "   3. Нажмите 'Pay'"
    echo "   4. После платежа проверьте план:"
    echo "      curl -X GET 'https://api.sec-scanner.pro/api/v1/quota' -H 'X-API-Key: $API_KEY'"
    echo ""
    echo "✅ Готово! Откройте URL выше для тестового платежа."
else
    echo "❌ Ошибка создания checkout session"
    echo "   Ответ: $CHECKOUT_RESPONSE"
    exit 1
fi
