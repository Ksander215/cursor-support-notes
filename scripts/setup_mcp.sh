#!/bin/bash
# Скрипт автоматической настройки MCP серверов для sec-scanner.pro
# Дата: 2026-01-28

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CURSOR_DIR="$PROJECT_ROOT/.cursor"
ENV_FILE="$PROJECT_ROOT/.env.mcp"

echo "🚀 Настройка MCP серверов для sec-scanner.pro"
echo "=============================================="
echo ""

# Проверка Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js не установлен!"
    echo "Установите Node.js: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node --version)
echo "✅ Node.js установлен: $NODE_VERSION"

# Проверка npm
if ! command -v npm &> /dev/null; then
    echo "❌ npm не установлен!"
    exit 1
fi

NPM_VERSION=$(npm --version)
echo "✅ npm установлен: $NPM_VERSION"
echo ""

# Создание директории .cursor
mkdir -p "$CURSOR_DIR"
echo "✅ Создана директория .cursor"

# Создание .env.mcp если не существует
if [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo "📝 Создание файла .env.mcp"
    echo "Введите значения для переменных окружения (или нажмите Enter для пропуска):"
    echo ""
    
    read -p "GitHub Token (ghp_...): " GITHUB_TOKEN_INPUT
    # Валидация: если введен текст подсказки или пусто, очищаем
    if [[ "$GITHUB_TOKEN_INPUT" == *"Token"* ]] || [[ "$GITHUB_TOKEN_INPUT" == *"github"* ]] || [ -z "$GITHUB_TOKEN_INPUT" ]; then
        GITHUB_TOKEN=""
    else
        GITHUB_TOKEN="$GITHUB_TOKEN_INPUT"
    fi
    
    read -p "PostgreSQL Connection String (Enter для SQLite: sqlite:///data/sec_scanner.db): " POSTGRES_INPUT
    # Валидация: если введен текст подсказки, используем значение по умолчанию
    if [[ "$POSTGRES_INPUT" == *"Connection String"* ]] || [[ "$POSTGRES_INPUT" == *"PostgreSQL"* ]] || [ -z "$POSTGRES_INPUT" ]; then
        POSTGRES_CONNECTION_STRING="sqlite:///data/sec_scanner.db"
    else
        POSTGRES_CONNECTION_STRING="$POSTGRES_INPUT"
    fi
    
    read -p "GitLab Token (опционально, glpat-...): " GITLAB_TOKEN_INPUT
    if [[ "$GITLAB_TOKEN_INPUT" == *"Token"* ]] || [[ "$GITLAB_TOKEN_INPUT" == *"опционально"* ]] || [ -z "$GITLAB_TOKEN_INPUT" ]; then
        GITLAB_TOKEN=""
    else
        GITLAB_TOKEN="$GITLAB_TOKEN_INPUT"
    fi
    
    read -p "Slack Bot Token (опционально, xoxb-...): " SLACK_INPUT
    if [[ "$SLACK_INPUT" == *"Token"* ]] || [[ "$SLACK_INPUT" == *"опционально"* ]] || [ -z "$SLACK_INPUT" ]; then
        SLACK_BOT_TOKEN=""
    else
        SLACK_BOT_TOKEN="$SLACK_INPUT"
    fi
    
    read -p "Redis URL (Enter для значения по умолчанию: redis://localhost:6379/0): " REDIS_INPUT
    if [[ "$REDIS_INPUT" == *"URL"* ]] || [[ "$REDIS_INPUT" == *"опционально"* ]] || [ -z "$REDIS_INPUT" ]; then
        REDIS_URL="redis://localhost:6379/0"
    else
        REDIS_URL="$REDIS_INPUT"
    fi
    
    # Экранируем специальные символы для безопасной записи
    cat > "$ENV_FILE" << 'ENVEOF'
# MCP Environment Variables
# Generated: 
# ВАЖНО: Замените значения ниже на реальные токены!

# GitHub
GITHUB_TOKEN=

# PostgreSQL (для dev можно использовать SQLite: sqlite:///data/sec_scanner.db)
# Для prod: postgresql://user:password@host:5432/sec_scanner
POSTGRES_CONNECTION_STRING=sqlite:///data/sec_scanner.db

# GitLab (опционально)
GITLAB_TOKEN=

# Slack (опционально)
SLACK_BOT_TOKEN=

# Redis (опционально)
REDIS_URL=redis://localhost:6379/0
ENVEOF
    
    # Записываем реальные значения (если были введены)
    if [ -n "$GITHUB_TOKEN" ]; then
        sed -i "s|^GITHUB_TOKEN=$|GITHUB_TOKEN=$GITHUB_TOKEN|" "$ENV_FILE"
    fi
    if [ -n "$POSTGRES_CONNECTION_STRING" ] && [ "$POSTGRES_CONNECTION_STRING" != "sqlite:///data/sec_scanner.db" ]; then
        sed -i "s|^POSTGRES_CONNECTION_STRING=.*|POSTGRES_CONNECTION_STRING=$POSTGRES_CONNECTION_STRING|" "$ENV_FILE"
    fi
    if [ -n "$GITLAB_TOKEN" ]; then
        sed -i "s|^GITLAB_TOKEN=$|GITLAB_TOKEN=$GITLAB_TOKEN|" "$ENV_FILE"
    fi
    if [ -n "$SLACK_BOT_TOKEN" ]; then
        sed -i "s|^SLACK_BOT_TOKEN=$|SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN|" "$ENV_FILE"
    fi
    
    echo "✅ Создан файл .env.mcp"
    echo "⚠️  ВАЖНО: Отредактируйте .env.mcp и добавьте реальные токены!"
    echo "⚠️  Не забудьте добавить .env.mcp в .gitignore!"
else
    echo "✅ Файл .env.mcp уже существует"
    echo "ℹ️  Если нужно обновить значения, отредактируйте файл вручную"
fi

# Загрузка переменных из .env.mcp
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# Создание конфигурации MCP
echo ""
echo "📝 Создание конфигурации MCP..."

# Определение строки подключения PostgreSQL
if [ -z "$POSTGRES_CONNECTION_STRING" ]; then
    # Проверяем, запущен ли Docker Compose с PostgreSQL
    if docker-compose -f "$PROJECT_ROOT/docker-compose.prod.yml" ps db 2>/dev/null | grep -q "Up"; then
        POSTGRES_CONNECTION_STRING="postgresql://sec_scanner:sec_scanner@localhost:5432/sec_scanner"
        echo "✅ Обнаружен запущенный PostgreSQL контейнер"
    else
        POSTGRES_CONNECTION_STRING="sqlite:///data/sec_scanner.db"
        echo "ℹ️  Используется SQLite (PostgreSQL не запущен)"
    fi
fi

# Создание mcp.json
cat > "$CURSOR_DIR/mcp.json" << EOF
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN:-}"
      }
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "POSTGRES_CONNECTION_STRING": "${POSTGRES_CONNECTION_STRING}"
      }
    },
    "docker": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-docker"]
    }
EOF

# Добавление опциональных серверов
if [ -n "$GITLAB_TOKEN" ]; then
    cat >> "$CURSOR_DIR/mcp.json" << EOF
    ,
    "gitlab": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-gitlab"],
      "env": {
        "GITLAB_TOKEN": "${GITLAB_TOKEN}"
      }
    }
EOF
fi

if [ -n "$SLACK_BOT_TOKEN" ]; then
    cat >> "$CURSOR_DIR/mcp.json" << EOF
    ,
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}"
      }
    }
EOF
fi

if [ -n "$REDIS_URL" ] && [ "$REDIS_URL" != "redis://localhost:6379/0" ]; then
    cat >> "$CURSOR_DIR/mcp.json" << EOF
    ,
    "redis": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-redis"],
      "env": {
        "REDIS_URL": "${REDIS_URL}"
      }
    }
EOF
fi

cat >> "$CURSOR_DIR/mcp.json" << EOF
  }
}
EOF

echo "✅ Создан файл .cursor/mcp.json"
echo ""

# Проверка доступности MCP серверов
echo "🔍 Проверка доступности MCP серверов..."
echo ""

# GitHub
if [ -n "$GITHUB_TOKEN" ]; then
    echo -n "Проверка GitHub MCP... "
    if npx -y @modelcontextprotocol/server-github --help &>/dev/null; then
        echo "✅"
    else
        echo "⚠️  (может потребоваться установка)"
    fi
else
    echo "⚠️  GitHub MCP пропущен (нет токена)"
fi

# PostgreSQL
echo -n "Проверка PostgreSQL MCP... "
if npx -y @modelcontextprotocol/server-postgres --help &>/dev/null; then
    echo "✅"
else
    echo "⚠️  (может потребоваться установка)"
fi

# Docker
echo -n "Проверка Docker MCP... "
if command -v docker &> /dev/null; then
    if npx -y @modelcontextprotocol/server-docker --help &>/dev/null; then
        echo "✅"
    else
        echo "⚠️  (может потребоваться установка)"
    fi
else
    echo "⚠️  Docker не установлен"
fi

echo ""
echo "✅ Настройка завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Проверьте файл .cursor/mcp.json"
echo "2. Убедитесь, что .env.mcp добавлен в .gitignore"
echo "3. Перезапустите Cursor IDE для загрузки конфигурации"
echo "4. Протестируйте подключения через AI агента"
echo ""
echo "Для создания GitHub issues из roadmap запустите:"
echo "  python scripts/create_github_issues.py"
