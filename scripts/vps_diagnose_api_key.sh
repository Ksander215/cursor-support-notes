#!/usr/bin/env bash
set -euo pipefail

# VPS API Key diagnostics, fix, and creation
# Usage: ./vps_diagnose_api_key.sh [diagnose|fix|create]

COMMAND="${1:-diagnose}"
VPS_PATH="/opt/sec-scanner"

echo "🔍 VPS API Key Management"
echo "========================"
echo ""

case "$COMMAND" in
    diagnose)
        echo "📋 Step 1: Checking .env.production"
        echo "-----------------------------------"
        cd "$VPS_PATH"
        if grep -q "^SEC_SCANNER_API_KEY=" .env.production; then
            ENV_KEY=$(grep "^SEC_SCANNER_API_KEY=" .env.production | cut -d'=' -f2-)
            echo "✅ Key found in .env.production"
            echo "   Length: ${#ENV_KEY} characters"
        else
            echo "❌ SEC_SCANNER_API_KEY not found in .env.production"
        fi
        ;;
    fix)
        echo "🔧 Fix static key..."
        cd "$VPS_PATH"
        # Implementation here
        ;;
    create)
        echo "🆕 Creating new API key..."
        cd "$VPS_PATH"
        # Implementation here
        ;;
    *)
        echo "Usage: $0 [diagnose|fix|create]"
        exit 1
        ;;
esac
echo "-----------------------------------"
CONTAINER_KEY=$(docker compose -f docker-compose.prod.yml exec -T api printenv | grep "^SEC_SCANNER_API_KEY=" | cut -d'=' -f2- || echo "")

if [ -z "$CONTAINER_KEY" ]; then
    echo "❌ Ключ НЕ загружен в контейнер"
    echo "   Перезапустите API: docker compose -f docker-compose.prod.yml restart api"
else
    echo "✅ Ключ загружен в контейнер"
    echo "   Длина: ${#CONTAINER_KEY} символов"
    echo "   Первые 30 символов: ${CONTAINER_KEY:0:30}..."
    echo "   Последние 10 символов: ...${CONTAINER_KEY: -10}"

    # Сравнение
    if [ "$ENV_KEY" = "$CONTAINER_KEY" ]; then
        echo "   ✅ Ключи совпадают"
    else
        echo "   ⚠️  Ключи НЕ совпадают!"
        echo "   Это может быть проблемой"
    fi
fi

echo ""

# 3. Проверка режима работы
echo "📋 Шаг 3: Проверка режима аутентификации"
echo "----------------------------------------"
REQUIRE_API_KEY=$(grep "^SEC_SCANNER_REQUIRE_API_KEY=" .env.production | cut -d'=' -f2- | tr -d ' ' || echo "false")
HAS_PEPPER=$(grep -q "^SEC_SCANNER_API_KEY_PEPPER=" .env.production && echo "true" || echo "false")

echo "   SEC_SCANNER_REQUIRE_API_KEY: $REQUIRE_API_KEY"
echo "   SEC_SCANNER_API_KEY_PEPPER установлен: $HAS_PEPPER"

if [ "$REQUIRE_API_KEY" = "true" ] && [ "$HAS_PEPPER" = "true" ]; then
    echo "   ⚠️  DB-backed режим включен"
    echo "   Static key может не работать для admin операций"
elif [ -n "$ENV_KEY" ]; then
    echo "   ✅ Static key режим"
    echo "   Static key должен работать как admin"
fi

echo ""

# 4. Тест аутентификации
echo "📋 Шаг 4: Тест аутентификации"
echo "-----------------------------"
echo "Тестирую static key из .env.production..."

TEST_RESPONSE=$(curl -s -X GET "https://api.sec-scanner.pro/api/v1/quota" \
    -H "X-API-Key: $ENV_KEY" 2>&1 || echo "ERROR")

if [[ "$TEST_RESPONSE" == *"quota"* ]] || [[ "$TEST_RESPONSE" == *"plan_code"* ]]; then
    echo "✅ Static key работает для обычных запросов"
elif [[ "$TEST_RESPONSE" == *"invalid API key"* ]]; then
    echo "❌ Static key НЕ работает - 'invalid API key'"
    echo "   Ответ: $TEST_RESPONSE"
elif [[ "$TEST_RESPONSE" == *"API key required"* ]]; then
    echo "⚠️  Требуется API ключ, но static key не принят"
    echo "   Ответ: $TEST_RESPONSE"
else
    echo "⚠️  Неожиданный ответ: $TEST_RESPONSE"
fi

echo ""

# 5. Тест admin endpoint
echo "📋 Шаг 5: Тест admin endpoint"
echo "----------------------------"
echo "Попытка создать API ключ через static key..."

ADMIN_TEST=$(curl -s -X POST "https://api.sec-scanner.pro/api/v1/admin/api-keys" \
    -H "X-API-Key: $ENV_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "org_name": "Diagnostic Test Org",
        "plan_code": "free",
        "key_name": "Diagnostic Test Key",
        "is_admin": false
    }' 2>&1 || echo "ERROR")

if [[ "$ADMIN_TEST" == *"api_key"* ]]; then
    echo "✅ Static key работает для admin операций!"
    API_KEY=$(echo "$ADMIN_TEST" | grep -o '"api_key":"[^"]*' | cut -d'"' -f4)
    echo "   Создан тестовый ключ: ${API_KEY:0:30}..."
elif [[ "$ADMIN_TEST" == *"admin API key required"* ]]; then
    echo "❌ Static key НЕ является admin ключом"
    echo "   Ответ: $ADMIN_TEST"
elif [[ "$ADMIN_TEST" == *"invalid API key"* ]]; then
    echo "❌ Static key не принимается"
    echo "   Ответ: $ADMIN_TEST"
else
    echo "⚠️  Неожиданный ответ: $ADMIN_TEST"
fi

echo ""
echo "✅ Диагностика завершена"
