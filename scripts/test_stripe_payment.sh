#!/usr/bin/env bash
set -euo pipefail

# Скрипт для тестирования Stripe платежной системы
# Использование: ./scripts/test_stripe_payment.sh

API_BASE_URL="${API_BASE_URL:-https://api.sec-scanner.pro}"
ADMIN_API_KEY="${ADMIN_API_KEY:-}"

echo "🧪 Тестирование Stripe платежной системы"
echo "=========================================="
echo ""

# Проверка переменных
if [[ -z "$ADMIN_API_KEY" ]]; then
    echo "⚠️  ADMIN_API_KEY не установлен"
    echo ""
    echo "Создайте admin API ключ через:"
    echo "  curl -X POST $API_BASE_URL/api/v1/admin/api-keys \\"
    echo "    -H 'X-API-Key: BOOTSTRAP_KEY' \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{\"org_name\": \"Test Org\", \"plan_code\": \"free\", \"is_admin\": true}'"
    echo ""
    read -r -p "Введите ADMIN_API_KEY (или нажмите Enter для создания нового): " ADMIN_API_KEY

    if [[ -z "$ADMIN_API_KEY" ]]; then
        echo "❌ Необходим ADMIN_API_KEY для тестирования"
        exit 1
    fi
fi

echo "📋 Шаг 1: Проверка Stripe конфигурации"
echo "----------------------------------------"

# Проверка health endpoint
echo "Проверка API health..."
HEALTH_RESPONSE=$(curl -s "$API_BASE_URL/healthz" || echo "ERROR")
if [[ "$HEALTH_RESPONSE" == *"ok"* ]] || [[ "$HEALTH_RESPONSE" == *"true"* ]]; then
    echo "✅ API доступен"
else
    echo "❌ API недоступен: $HEALTH_RESPONSE"
    exit 1
fi

echo ""

echo "📋 Шаг 2: Создание тестовой организации и API ключа"
echo "----------------------------------------------------"

# Создать тестовую организацию с API ключом
echo "Создание тестовой организации..."
CREATE_KEY_RESPONSE=$(curl -s -X POST "$API_BASE_URL/api/v1/admin/api-keys" \
    -H "X-API-Key: $ADMIN_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "org_name": "Test Payment Org",
        "plan_code": "free",
        "key_name": "Test Payment Key",
        "is_admin": false
    }' || echo "ERROR")

if [[ "$CREATE_KEY_RESPONSE" == *"api_key"* ]]; then
    TEST_API_KEY=$(echo "$CREATE_KEY_RESPONSE" | grep -o '"api_key":"[^"]*' | cut -d'"' -f4)
    ORG_ID=$(echo "$CREATE_KEY_RESPONSE" | grep -o '"org_id":[0-9]*' | cut -d':' -f2)
    echo "✅ Организация создана (org_id: $ORG_ID)"
    echo "✅ API ключ получен: ${TEST_API_KEY:0:20}..."
else
    echo "❌ Ошибка создания организации: $CREATE_KEY_RESPONSE"
    echo ""
    echo "Попробуйте использовать существующий API ключ:"
    read -r -p "Введите API ключ: " TEST_API_KEY
    if [[ -z "$TEST_API_KEY" ]]; then
        exit 1
    fi
fi

echo ""

echo "📋 Шаг 3: Создание Stripe Checkout Session"
echo "------------------------------------------"

# Создать checkout session
echo "Создание checkout session для плана 'starter'..."
CHECKOUT_RESPONSE=$(curl -s -X POST "$API_BASE_URL/payments/checkout" \
    -H "X-API-Key: $TEST_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "plan_code": "starter",
        "country_code": "US",
        "success_url": "https://sec-scanner.pro/app/settings?success=true",
        "cancel_url": "https://sec-scanner.pro/app/settings?canceled=true"
    }' || echo "ERROR")

if [[ "$CHECKOUT_RESPONSE" == *"url"* ]]; then
    CHECKOUT_URL=$(echo "$CHECKOUT_RESPONSE" | grep -o '"url":"[^"]*' | cut -d'"' -f4)
    SESSION_ID=$(echo "$CHECKOUT_RESPONSE" | grep -o '"session_id":"[^"]*' | cut -d'"' -f4)
    PROVIDER=$(echo "$CHECKOUT_RESPONSE" | grep -o '"provider":"[^"]*' | cut -d'"' -f4)

    echo "✅ Checkout session создан!"
    echo "   Session ID: $SESSION_ID"
    echo "   Provider: $PROVIDER"
    echo "   URL: $CHECKOUT_URL"
    echo ""
    echo "🌐 Откройте URL в браузере для тестового платежа:"
    echo "   $CHECKOUT_URL"
    echo ""
    echo "💳 Используйте тестовую карту Stripe:"
    echo "   Номер: 4242 4242 4242 4242"
    echo "   Срок: 12/25 (любая будущая дата)"
    echo "   CVC: 123 (любые 3 цифры)"
    echo "   ZIP: 12345 (любые 5 цифр)"
else
    echo "❌ Ошибка создания checkout session: $CHECKOUT_RESPONSE"
    exit 1
fi

echo ""
echo "📋 Шаг 4: Инструкции для тестового платежа"
echo "--------------------------------------------"
echo ""
echo "1. Откройте URL в браузере: $CHECKOUT_URL"
echo "2. Заполните форму тестовой картой:"
echo "   - Номер: 4242 4242 4242 4242"
echo "   - Срок: 12/25"
echo "   - CVC: 123"
echo "   - ZIP: 12345"
echo "3. Нажмите 'Pay'"
echo "4. После платежа вернитесь сюда и нажмите Enter"
echo ""
read -r -p "Нажмите Enter после завершения платежа..."

echo ""
echo "📋 Шаг 5: Проверка webhook и обновления плана"
echo "----------------------------------------------"

# Проверка плана организации
echo "Проверка плана организации..."
QUOTA_RESPONSE=$(curl -s -X GET "$API_BASE_URL/api/v1/quota" \
    -H "X-API-Key: $TEST_API_KEY" || echo "ERROR")

if [[ "$QUOTA_RESPONSE" == *"plan_code"* ]]; then
    PLAN_CODE=$(echo "$QUOTA_RESPONSE" | grep -o '"plan_code":"[^"]*' | cut -d'"' -f4)
    echo "✅ Текущий план организации: $PLAN_CODE"

    if [[ "$PLAN_CODE" == "starter" ]]; then
        echo "✅ План успешно обновлен на 'starter'!"
    else
        echo "⚠️  План еще не обновлен (текущий: $PLAN_CODE)"
        echo "   Возможно, webhook еще не обработан"
    fi
else
    echo "⚠️  Не удалось получить информацию о плане: $QUOTA_RESPONSE"
fi

echo ""
echo "📋 Шаг 6: Проверка логов"
echo "------------------------"
echo ""
echo "Проверьте логи API на VPS:"
echo "  docker logs sec-scanner-api-1 | grep -i stripe"
echo ""
echo "Проверьте Stripe Dashboard → Webhooks:"
echo "  https://dashboard.stripe.com/test/webhooks"
echo "  Найдите ваш endpoint и проверьте события"
echo ""

echo "✅ Тестирование завершено!"
echo ""
echo "📝 Следующие шаги:"
echo "   1. Проверьте логи API на наличие webhook событий"
echo "   2. Проверьте Stripe Dashboard → Payments для подтверждения платежа"
echo "   3. Проверьте Stripe Dashboard → Webhooks для проверки доставки событий"
echo "   4. Убедитесь, что план организации обновился в БД"
