#!/bin/bash
# Скрипт для исправления .env.mcp файла
# Использование: bash scripts/fix_env_mcp.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env.mcp"

echo "🔧 Исправление файла .env.mcp"
echo "=============================="
echo ""

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Файл .env.mcp не найден!"
    exit 1
fi

echo "Текущее содержимое файла:"
echo "-------------------------"
cat "$ENV_FILE"
echo ""
echo "-------------------------"
echo ""

read -p "Хотите очистить файл и создать заново? (y/n): " CONFIRM

if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Отменено."
    exit 0
fi

# Создаем чистый шаблон
cat > "$ENV_FILE" << 'EOF'
# MCP Environment Variables
# Generated: 2026-01-28
# ВАЖНО: Замените значения ниже на реальные токены!

# GitHub
# Получите токен: https://github.com/settings/tokens
GITHUB_TOKEN=

# PostgreSQL (для dev можно использовать SQLite: sqlite:///data/sec_scanner.db)
# Для prod: postgresql://user:password@host:5432/sec_scanner
POSTGRES_CONNECTION_STRING=sqlite:///data/sec_scanner.db

# GitLab (опционально)
# Получите токен: https://gitlab.com/-/user_settings/personal_access_tokens
GITLAB_TOKEN=

# Slack (опционально)
# Получите токен: https://api.slack.com/apps
SLACK_BOT_TOKEN=

# Redis (опционально)
REDIS_URL=redis://localhost:6379/0
EOF

echo "✅ Файл .env.mcp очищен и создан заново"
echo ""
echo "📝 Следующие шаги:"
echo "1. Откройте файл .env.mcp в редакторе"
echo "2. Добавьте реальные токены (GitHub, GitLab, Slack)"
echo "3. Проверьте строку подключения PostgreSQL"
echo ""
echo "Для редактирования:"
echo "  nano .env.mcp"
echo "  # или"
echo "  code .env.mcp"
