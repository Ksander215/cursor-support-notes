#!/bin/bash
# Скрипт для исправления проблем с MCP зависимостями
# Дата: 2026-01-28

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔧 Исправление проблем с MCP зависимостями"
echo "=========================================="
echo ""

# Проверяем Python окружение
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python3."
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ Найден: $PYTHON_VERSION"
echo ""

# Проверяем, есть ли виртуальное окружение
if [ -d ".venv" ]; then
    echo "📦 Активируем виртуальное окружение..."
    source .venv/bin/activate
    echo "✅ Виртуальное окружение активировано"
else
    echo "📦 Создаём виртуальное окружение..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "✅ Виртуальное окружение создано"
fi
echo ""

# Устанавливаем зависимости из requirements.txt
if [ -f "requirements.txt" ]; then
    echo "📥 Устанавливаем зависимости из requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "✅ Зависимости установлены"
else
    echo "⚠️  Файл requirements.txt не найден, устанавливаем минимальные зависимости..."
    pip install --upgrade pip
    pip install sqlalchemy psycopg[binary] redis requests
    echo "✅ Минимальные зависимости установлены"
fi

# Явно устанавливаем psycopg для PostgreSQL (на случай если requirements.txt не сработал)
echo "📥 Устанавливаем psycopg для PostgreSQL..."
# Устанавливаем psycopg3 (современный)
pip install psycopg[binary] || echo "⚠️  Не удалось установить psycopg3"
# Также устанавливаем psycopg2-binary для совместимости с SQLAlchemy
pip install psycopg2-binary || echo "⚠️  Не удалось установить psycopg2-binary"
echo "✅ psycopg установлен"
echo ""

# Проверяем установку psycopg
echo "🔍 Проверяем установку psycopg..."
python3 -c "import psycopg; print('✅ psycopg3 установлен')" 2>/dev/null || echo "⚠️  psycopg3 не найден"
python3 -c "import psycopg2; print('✅ psycopg2 установлен')" 2>/dev/null || echo "⚠️  psycopg2 не найден"
echo ""

# Проверяем установленные пакеты
echo "🔍 Проверяем установленные пакеты..."
python3 -c "import sqlalchemy; print(f'✅ SQLAlchemy {sqlalchemy.__version__}')" || echo "❌ SQLAlchemy не установлен"
python3 -c "import redis; print(f'✅ Redis {redis.__version__}')" || echo "❌ Redis не установлен"
python3 -c "import requests; print(f'✅ Requests {requests.__version__}')" || echo "❌ Requests не установлен"
echo ""

# Проверяем Docker доступность
echo "🐳 Проверяем Docker..."
if command -v docker &> /dev/null; then
    # Увеличиваем timeout для Docker в WSL
    if timeout 10 docker ps &> /dev/null; then
        echo "✅ Docker доступен"
        docker ps --format "table {{.Names}}\t{{.Status}}" | head -5
    else
        echo "⚠️  Docker не отвечает. Возможные причины:"
        echo "   - Docker daemon не запущен"
        echo "   - Проблемы с доступом к Docker socket в WSL"
        echo "   - Попробуйте: sudo service docker start"
    fi
else
    echo "❌ Docker не установлен или не в PATH"
fi
echo ""

# Проверяем PostgreSQL подключение
echo "🐘 Проверяем PostgreSQL..."
if [ -f ".env.mcp" ]; then
    POSTGRES_URL=$(grep "^POSTGRES_CONNECTION_STRING=" .env.mcp | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    if [ -n "$POSTGRES_URL" ]; then
        echo "   Строка подключения найдена в .env.mcp"
        python3 -c "
import sys
try:
    from sqlalchemy import create_engine, text
    engine = create_engine('$POSTGRES_URL', connect_args={'connect_timeout': 5})
    with engine.connect() as conn:
        result = conn.execute(text('SELECT version()'))
        version = result.fetchone()[0]
    print(f'✅ PostgreSQL подключение успешно')
    print(f'   Версия: {version[:50]}...')
except Exception as e:
    print(f'❌ Ошибка подключения: {str(e)}')
    sys.exit(1)
" || echo "   ⚠️  Не удалось подключиться к PostgreSQL"
    else
        echo "   ⚠️  POSTGRES_CONNECTION_STRING не найден в .env.mcp"
    fi
else
    echo "   ⚠️  Файл .env.mcp не найден"
fi
echo ""

# Проверяем Redis подключение
echo "🔴 Проверяем Redis..."
if [ -f ".env.mcp" ]; then
    REDIS_URL=$(grep "^REDIS_URL=" .env.mcp | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    if [ -n "$REDIS_URL" ]; then
        echo "   URL Redis найден в .env.mcp"
        python3 -c "
import sys
try:
    import redis
    r = redis.from_url('$REDIS_URL', socket_connect_timeout=5)
    r.ping()
    info = r.info()
    print(f'✅ Redis подключение успешно')
    print(f'   Версия: {info.get(\"redis_version\", \"unknown\")}')
except ImportError:
    print('❌ Библиотека redis не установлена')
except Exception as e:
    print(f'⚠️  Не удалось подключиться: {str(e)}')
" || echo "   ⚠️  Redis недоступен (это нормально, если не используется)"
    else
        echo "   ⚠️  REDIS_URL не найден в .env.mcp"
    fi
else
    echo "   ⚠️  Файл .env.mcp не найден"
fi
echo ""

echo "=========================================="
echo "✅ Проверка завершена!"
echo ""
echo "💡 Следующие шаги:"
echo "   1. Запустите тест: python3 scripts/test_mcp_connections.py"
echo "   2. Перезапустите Cursor IDE для применения MCP"
echo ""
