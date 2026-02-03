#!/usr/bin/env bash
set -euo pipefail

# Скрипт для тестирования Stripe на VPS
# Использование: ./scripts/vps_test_stripe.sh

cd /opt/sec-scanner

echo "🧪 Тестирование Stripe платежной системы"
echo "=========================================="
echo ""

# Шаг 1: Получить static key
echo "📋 Шаг 1: Проверка конфигурации"
echo "--------------------------------"

STATIC_KEY=$(docker compose -f docker-compose.prod.yml exec -T api printenv | grep "^SEC_SCANNER_API_KEY=" | cut -d'=' -f2- || echo "")

if [ -z "$STATIC_KEY" ]; then
    echo "⚠️  SEC_SCANNER_API_KEY не найден в переменных окружения контейнера"
    echo ""
    echo "Проверяю .env.production..."
    ENV_KEY=$(grep "^SEC_SCANNER_API_KEY=" .env.production | cut -d'=' -f2- || echo "")

    if [ -n "$ENV_KEY" ]; then
        echo "✅ Ключ найден в .env.production"
        echo "   Использую ключ из файла..."
        STATIC_KEY="$ENV_KEY"
        echo ""
        echo "💡 Совет: Перезапустите API для загрузки переменных:"
        echo "   docker compose -f docker-compose.prod.yml restart api"
    else
        echo "❌ Ключ не найден ни в контейнере, ни в .env.production"
        echo ""
        read -r -p "Введите ваш API ключ (или нажмите Enter для выхода): " STATIC_KEY
        if [ -z "$STATIC_KEY" ]; then
            exit 1
        fi
    fi
else
    echo "✅ Static API key найден в контейнере: ${STATIC_KEY:0:20}..."
fi

echo ""

# Шаг 2: Создать тестовый API ключ
echo "📋 Шаг 2: Создание тестового API ключа"
echo "--------------------------------------"

echo "Создание тестовой организации..."
CREATE_RESPONSE=$(curl -s -X POST "https://api.sec-scanner.pro/api/v1/admin/api-keys" \
    -H "X-API-Key: $STATIC_KEY" \
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
else
    echo "❌ Ошибка создания API ключа"
    echo "Ответ: $CREATE_RESPONSE"
    echo ""
    echo "Возможные причины:"
    echo "  - Static key неверный или не admin"
    echo "  - Проблемы с БД"
    echo ""
    read -r -p "Введите существующий API ключ для тестирования: " API_KEY
    if [ -z "$API_KEY" ]; then
        exit 1
    fi
fi

echo ""

# Шаг 3: Создать checkout session
echo "📋 Шаг 3: Создание Checkout Session"
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
