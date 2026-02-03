#!/usr/bin/env bash
set -euo pipefail

# Быстрый скрипт для тестирования Stripe на VPS
# Использование: ./scripts/quick_test_stripe.sh

API_BASE_URL="${API_BASE_URL:-https://api.sec-scanner.pro}"

echo "🧪 Быстрый тест Stripe платежной системы"
echo "=========================================="
echo ""

# Шаг 1: Создать или использовать API ключ
echo "📋 Шаг 1: Получение API ключа"
echo "------------------------------"

# Попробуем создать API ключ через BOOTSTRAP_KEY
echo "Попытка создать тестовый API ключ..."
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE_URL/api/v1/admin/api-keys" \
    -H "X-API-Key: BOOTSTRAP_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "org_name": "Test Payment Org '"$(date +%s)"'",
        "plan_code": "free",
        "key_name": "Test Payment Key",
        "is_admin": false
    }' 2>&1 || echo "ERROR")

if [[ "$CREATE_RESPONSE" == *"api_key"* ]]; then
    API_KEY=$(echo "$CREATE_RESPONSE" | grep -o '"api_key":"[^"]*' | cut -d'"' -f4)
    ORG_ID=$(echo "$CREATE_RESPONSE" | grep -o '"org_id":[0-9]*' | cut -d':' -f2)
    echo "✅ API ключ создан успешно!"
    echo "   Org ID: $ORG_ID"
    echo "   API Key: ${API_KEY:0:30}..."
    echo ""
else
    echo "❌ Не удалось создать API ключ через BOOTSTRAP_KEY"
    echo "Ответ: $CREATE_RESPONSE"
    echo ""
    echo "Попробуйте использовать существующий API ключ:"
    read -r -p "Введите ваш API ключ: " API_KEY
    if [[ -z "$API_KEY" ]]; then
        echo "❌ API ключ обязателен для тестирования"
        exit 1
    fi
fi

# Шаг 2: Создать checkout session
echo "📋 Шаг 2: Создание Checkout Session"
echo "-----------------------------------"

echo "Создание checkout session для плана 'starter'..."
CHECKOUT_RESPONSE=$(curl -s -X POST "$API_BASE_URL/payments/checkout" \
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
    echo "   4. После платежа проверьте план через:"
    echo "      curl -X GET '$API_BASE_URL/api/v1/quota' -H 'X-API-Key: $API_KEY'"
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

echo ""
echo "✅ Готово! Откройте URL выше для тестового платежа."
