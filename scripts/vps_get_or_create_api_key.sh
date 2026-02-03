#!/usr/bin/env bash
set -euo pipefail

# Получение или создание API ключа для тестирования
# Использование: ./scripts/vps_get_or_create_api_key.sh

cd /opt/sec-scanner

echo "🔑 Получение API ключа для тестирования"
echo "======================================="
echo ""

# Вариант 1: Попробовать получить существующий ключ из БД
echo "📋 Вариант 1: Поиск существующих API ключей в БД"
echo "------------------------------------------------"

EXISTING_KEYS=$(docker compose -f docker-compose.prod.yml exec -T db psql -U sec_scanner -d sec_scanner -t -c "SELECT id, name, prefix, last4, is_admin FROM api_keys WHERE is_active = true LIMIT 5;" 2>/dev/null || echo "")

if [ -n "$EXISTING_KEYS" ] && [ "$EXISTING_KEYS" != "" ]; then
    echo "✅ Найдены существующие API ключи в БД:"
    echo "$EXISTING_KEYS"
    echo ""
    echo "💡 Используйте один из этих ключей из веб-интерфейса"
    echo "   или создайте новый через https://sec-scanner.pro/app/settings"
else
    echo "⚠️  API ключи в БД не найдены"
fi

echo ""

# Вариант 2: Попробовать создать через static key (если загружен)
echo "📋 Вариант 2: Попытка создать через static key"
echo "----------------------------------------------"

# Проверить ключ в контейнере
CONTAINER_KEY=$(docker compose -f docker-compose.prod.yml exec -T api printenv | grep "^SEC_SCANNER_API_KEY=" | cut -d'=' -f2- || echo "")

# Если не загружен, попробовать из .env.production
if [ -z "$CONTAINER_KEY" ]; then
    ENV_KEY=$(grep "^SEC_SCANNER_API_KEY=" .env.production | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || echo "")
    if [ -n "$ENV_KEY" ]; then
        echo "Используем ключ из .env.production..."
        STATIC_KEY="$ENV_KEY"
    else
        echo "❌ Static key не найден"
        STATIC_KEY=""
    fi
else
    echo "Используем ключ из контейнера..."
    STATIC_KEY="$CONTAINER_KEY"
fi

if [ -n "$STATIC_KEY" ]; then
    echo "Тестирую static key: ${STATIC_KEY:0:20}..."

    # Тест простого запроса
    TEST_RESPONSE=$(curl -s -X GET "https://api.sec-scanner.pro/api/v1/quota" \
        -H "X-API-Key: $STATIC_KEY" 2>&1 || echo "ERROR")

    if [[ "$TEST_RESPONSE" == *"quota"* ]] || [[ "$TEST_RESPONSE" == *"plan_code"* ]]; then
        echo "✅ Static key работает для обычных запросов"

        # Попробовать создать API ключ
        echo "Попытка создать новый API ключ..."
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
            echo "✅ API ключ создан успешно!"
            echo "   API Key: ${API_KEY:0:30}..."
            echo ""
            echo "📝 Используйте этот ключ для тестирования:"
            echo "   $API_KEY"
        else
            echo "❌ Не удалось создать ключ: $CREATE_RESPONSE"
        fi
    else
        echo "❌ Static key не работает: $TEST_RESPONSE"
    fi
else
    echo "❌ Static key недоступен"
fi

echo ""
echo "📋 Вариант 3: Рекомендации"
echo "--------------------------"
echo "1. Откройте https://sec-scanner.pro/app/settings"
echo "2. Перейдите в раздел 'API Keys'"
echo "3. Создайте новый API ключ или используйте существующий"
echo "4. Скопируйте ключ и используйте его для тестирования:"
echo ""
echo "   curl -X POST 'https://api.sec-scanner.pro/payments/checkout' \\"
echo "     -H 'X-API-Key: ВАШ_КЛЮЧ' \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"plan_code\": \"starter\", \"country_code\": \"US\", ...}'"
