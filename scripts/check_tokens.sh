#!/bin/bash
# Скрипт для проверки токенов из .env.mcp
# Использование: bash scripts/check_tokens.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env.mcp"

echo "🔍 Проверка токенов из .env.mcp"
echo "================================"
echo ""

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Файл .env.mcp не найден!"
    echo "Создайте файл: bash scripts/setup_mcp.sh"
    exit 1
fi

# Загружаем переменные
set -a
source "$ENV_FILE" 2>/dev/null
set +a

# Проверка GitHub
echo "1️⃣  GitHub Token"
if [ -z "$GITHUB_TOKEN" ]; then
    echo "   ⚠️  Токен не установлен"
elif [[ "$GITHUB_TOKEN" != ghp_* ]]; then
    echo "   ❌ Неверный формат токена (должен начинаться с ghp_)"
else
    echo "   ✅ Формат токена правильный"
    echo "   🔗 Проверка через API..."
    RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user 2>/dev/null)
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | head -n-1)

    if [ "$HTTP_CODE" = "200" ]; then
        USERNAME=$(echo "$BODY" | grep -o '"login":"[^"]*' | cut -d'"' -f4)
        echo "   ✅ Токен работает! Пользователь: $USERNAME"
    elif [ "$HTTP_CODE" = "401" ]; then
        echo "   ❌ Токен недействителен или истек"
    else
        echo "   ⚠️  Ошибка проверки (HTTP $HTTP_CODE)"
    fi
fi
echo ""

# Проверка GitLab
echo "2️⃣  GitLab Token"
if [ -z "$GITLAB_TOKEN" ]; then
    echo "   ⏭️  Токен не установлен (опционально)"
elif [[ "$GITLAB_TOKEN" != glpat-* ]]; then
    echo "   ❌ Неверный формат токена (должен начинаться с glpat-)"
else
    echo "   ✅ Формат токена правильный"
    echo "   🔗 Проверка через API..."
    RESPONSE=$(curl -s -w "\n%{http_code}" -H "PRIVATE-TOKEN: $GITLAB_TOKEN" https://gitlab.com/api/v4/user 2>/dev/null)
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | head -n-1)

    if [ "$HTTP_CODE" = "200" ]; then
        USERNAME=$(echo "$BODY" | grep -o '"username":"[^"]*' | cut -d'"' -f4)
        echo "   ✅ Токен работает! Пользователь: $USERNAME"
    elif [ "$HTTP_CODE" = "401" ]; then
        echo "   ❌ Токен недействителен или истек"
    else
        echo "   ⚠️  Ошибка проверки (HTTP $HTTP_CODE)"
    fi
fi
echo ""

# Проверка Slack
echo "3️⃣  Slack Bot Token"
if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "   ⏭️  Токен не установлен (опционально)"
    echo "   💡 Если Slack недоступен, используйте Telegram (см. SLACK_ALTERNATIVES.md)"
elif [[ "$SLACK_BOT_TOKEN" != xoxb-* ]]; then
    echo "   ❌ Неверный формат токена (должен начинаться с xoxb-)"
else
    echo "   ✅ Формат токена правильный"
    echo "   🔗 Проверка через API..."
    RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $SLACK_BOT_TOKEN" https://slack.com/api/auth.test 2>/dev/null)
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | head -n-1)

    if echo "$BODY" | grep -q '"ok":true'; then
        echo "   ✅ Токен работает!"
    elif [ "$HTTP_CODE" = "200" ] && echo "$BODY" | grep -q '"ok":false'; then
        ERROR=$(echo "$BODY" | grep -o '"error":"[^"]*' | cut -d'"' -f4)
        echo "   ❌ Ошибка: $ERROR"
    else
        echo "   ⚠️  Ошибка проверки (HTTP $HTTP_CODE)"
        echo "   💡 Если Slack недоступен в вашей стране, используйте Telegram"
    fi
fi
echo ""

# Проверка Telegram
echo "3.1️⃣  Telegram Bot Token (альтернатива Slack)"
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "   ⏭️  Токен не установлен (опционально)"
    echo "   💡 Рекомендуется как альтернатива Slack (см. SLACK_ALTERNATIVES.md)"
elif [[ "$TELEGRAM_BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
    echo "   ✅ Формат токена правильный"
    echo "   🔗 Проверка через API..."
    RESPONSE=$(curl -s -w "\n%{http_code}" "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe" 2>/dev/null)
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | head -n-1)

    if echo "$BODY" | grep -q '"ok":true'; then
        BOT_NAME=$(echo "$BODY" | grep -o '"username":"[^"]*' | cut -d'"' -f4)
        echo "   ✅ Токен работает! Бот: @$BOT_NAME"
        if [ -n "$TELEGRAM_CHAT_ID" ]; then
            echo "   ✅ Chat ID установлен: $TELEGRAM_CHAT_ID"
        else
            echo "   ⚠️  Chat ID не установлен (нужен для отправки сообщений)"
        fi
    else
        echo "   ❌ Токен недействителен"
    fi
else
    echo "   ❌ Неверный формат токена (формат: 123456789:ABCdef...)"
fi
echo ""

# Проверка PostgreSQL/SQLite
echo "4️⃣  PostgreSQL/SQLite Connection"
if [ -z "$POSTGRES_CONNECTION_STRING" ]; then
    echo "   ⚠️  Строка подключения не установлена"
elif [[ "$POSTGRES_CONNECTION_STRING" == sqlite* ]]; then
    DB_PATH="${POSTGRES_CONNECTION_STRING#sqlite:///}"
    if [ -f "$DB_PATH" ]; then
        echo "   ✅ SQLite файл существует: $DB_PATH"
        sqlite3 "$DB_PATH" "SELECT 1;" 2>/dev/null && echo "   ✅ Подключение работает" || echo "   ❌ Ошибка подключения"
    else
        echo "   ⚠️  SQLite файл не найден: $DB_PATH"
        echo "   ℹ️  Файл будет создан при первом использовании"
    fi
else
    echo "   🔗 Проверка PostgreSQL подключения..."
    if command -v psql &> /dev/null; then
        psql "$POSTGRES_CONNECTION_STRING" -c "SELECT 1;" 2>/dev/null && echo "   ✅ Подключение работает" || echo "   ❌ Ошибка подключения"
    else
        echo "   ⚠️  psql не установлен, проверка невозможна"
    fi
fi
echo ""

# Проверка Redis
echo "5️⃣  Redis Connection"
if [ -z "$REDIS_URL" ]; then
    echo "   ⏭️  URL не установлен (опционально)"
elif command -v redis-cli &> /dev/null; then
    echo "   🔗 Проверка подключения..."
    redis-cli -u "$REDIS_URL" ping 2>/dev/null | grep -q "PONG" && echo "   ✅ Подключение работает" || echo "   ❌ Ошибка подключения"
else
    echo "   ⚠️  redis-cli не установлен, проверка невозможна"
fi
echo ""

echo "================================"
echo "✅ Проверка завершена!"
echo ""
echo "📖 Подробные инструкции:"
echo "   - Получение токенов: HOW_TO_GET_TOKENS.md"
echo "   - Альтернативы Slack: SLACK_ALTERNATIVES.md"
