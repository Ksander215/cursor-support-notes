#!/usr/bin/env bash
set -euo pipefail

# Исправление и тестирование Stripe на VPS
# Использование: ./scripts/vps_fix_and_test_stripe.sh

cd /opt/sec-scanner

echo "🔧 Исправление конфигурации и тестирование Stripe"
echo "=================================================="
echo ""

# Шаг 1: Проверка и перезапуск API
echo "📋 Шаг 1: Проверка конфигурации"
echo "--------------------------------"

echo "Проверяю .env.production..."
if grep -q "^SEC_SCANNER_API_KEY=" .env.production; then
    STATIC_KEY=$(grep "^SEC_SCANNER_API_KEY=" .env.production | cut -d'=' -f2-)
    echo "✅ Static key найден в .env.production: ${STATIC_KEY:0:20}..."
else
    echo "❌ SEC_SCANNER_API_KEY не найден в .env.production"
    exit 1
fi

echo ""
echo "Перезапускаю API контейнер для загрузки переменных..."
docker compose -f docker-compose.prod.yml restart api
sleep 5

echo "Проверяю загрузку переменных в контейнер..."
CONTAINER_KEY=$(docker compose -f docker-compose.prod.yml exec -T api printenv | grep "^SEC_SCANNER_API_KEY=" | cut -d'=' -f2- || echo "")

if [ -z "$CONTAINER_KEY" ]; then
    echo "⚠️  Ключ все еще не загружен в контейнер"
    echo "Использую ключ из .env.production напрямую"
    USE_KEY="$STATIC_KEY"
else
    echo "✅ Ключ загружен в контейнер: ${CONTAINER_KEY:0:20}..."
    USE_KEY="$CONTAINER_KEY"
fi

echo ""

# Шаг 2: Проверка режима работы
echo "📋 Шаг 2: Проверка режима аутентификации"
echo "----------------------------------------"

REQUIRE_API_KEY=$(grep "^SEC_SCANNER_REQUIRE_API_KEY=" .env.production | cut -d'=' -f2- | tr -d ' ' || echo "false")

if [ "$REQUIRE_API_KEY" = "true" ]; then
    echo "⚠️  DB-backed режим включен (SEC_SCANNER_REQUIRE_API_KEY=true)"
    echo "   Static key может не работать для создания новых ключей"
    echo ""
    echo "Попробуем создать ключ через static key (должен быть admin)..."
else
    echo "✅ Static key режим (SEC_SCANNER_REQUIRE_API_KEY=false)"
    echo "   Static key должен работать как admin"
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
    echo ""
    echo "Попробуем использовать существующий API ключ из БД..."
    echo "Или создайте admin ключ вручную через веб-интерфейс"
    echo ""
    read -r -p "Введите существующий API ключ для тестирования: " API_KEY
    if [ -z "$API_KEY" ]; then
        echo "❌ Необходим API ключ для тестирования"
        exit 1
    fi
else
    echo "❌ Ошибка создания API ключа"
    echo "Ответ: $CREATE_RESPONSE"
    echo ""
    read -r -p "Введите существующий API ключ для тестирования: " API_KEY
    if [ -z "$API_KEY" ]; then
        exit 1
    fi
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
    echo "Ответ: $CHECKOUT_RESPONSE"
    echo ""
    echo "Возможные причины:"
    echo "  - Неверный API ключ"
    echo "  - Stripe не настроен (проверьте .env.production)"
    echo "  - Проблемы с сетью"
    exit 1
fi
