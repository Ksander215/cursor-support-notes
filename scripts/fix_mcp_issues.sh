#!/bin/bash
# Скрипт для исправления проблем с MCP серверами
# Дата: 2026-01-28

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔧 Исправление проблем с MCP серверами"
echo "========================================"
echo ""

# 1. Проверка и установка Python зависимостей
echo "1️⃣  Проверка Python зависимостей..."
if [ -f "requirements.txt" ]; then
    # Проверяем наличие виртуального окружения
    if [ -d ".venv" ]; then
        echo "   ✅ Найдено виртуальное окружение .venv"
        source .venv/bin/activate
    elif [ -d "venv" ]; then
        echo "   ✅ Найдено виртуальное окружение venv"
        source venv/bin/activate
    else
        echo "   ⚠️  Виртуальное окружение не найдено, создаю..."
        python3 -m venv .venv
        source .venv/bin/activate
    fi

    echo "   📦 Установка зависимостей из requirements.txt..."
    pip install -q -r requirements.txt
    echo "   ✅ Зависимости установлены"
else
    echo "   ⚠️  requirements.txt не найден"
fi
echo ""

# 2. Проверка SQLAlchemy
echo "2️⃣  Проверка SQLAlchemy..."
if python3 -c "import sqlalchemy" 2>/dev/null; then
    echo "   ✅ SQLAlchemy установлен"
    python3 -c "import sqlalchemy; print(f'      Версия: {sqlalchemy.__version__}')"
else
    echo "   ❌ SQLAlchemy не установлен, устанавливаю..."
    pip install sqlalchemy psycopg[binary]
    echo "   ✅ SQLAlchemy установлен"
fi
echo ""

# 3. Проверка Redis библиотеки
echo "3️⃣  Проверка Redis библиотеки..."
if python3 -c "import redis" 2>/dev/null; then
    echo "   ✅ Redis библиотека установлена"
    python3 -c "import redis; print(f'      Версия: {redis.__version__}')"
else
    echo "   ⚠️  Redis библиотека не установлена, устанавливаю..."
    pip install redis
    echo "   ✅ Redis библиотека установлена"
fi
echo ""

# 4. Проверка Docker
echo "4️⃣  Проверка Docker..."
if command -v docker &> /dev/null; then
    echo "   ✅ Docker найден в PATH"
    docker --version

    # Проверка доступности Docker daemon
    if docker ps &> /dev/null; then
        echo "   ✅ Docker daemon доступен"
        CONTAINER_COUNT=$(docker ps -q | wc -l)
        echo "      Запущено контейнеров: $CONTAINER_COUNT"
    else
        echo "   ⚠️  Docker daemon недоступен"
        echo "      💡 Убедитесь что Docker Desktop запущен или Docker daemon работает"
        echo "      💡 В WSL: возможно нужно запустить Docker Desktop на Windows"
    fi
else
    echo "   ❌ Docker не найден в PATH"
    echo "      💡 Установите Docker Desktop или Docker Engine"
fi
echo ""

# 5. Проверка PostgreSQL подключения
echo "5️⃣  Проверка PostgreSQL подключения..."
if [ -f ".env.mcp" ]; then
    POSTGRES_URL=$(grep "^POSTGRES_CONNECTION_STRING=" .env.mcp | cut -d'=' -f2- | tr -d '"' | tr -d "'")

    if [ -n "$POSTGRES_URL" ]; then
        echo "   📝 Найдена строка подключения в .env.mcp"

        if [[ "$POSTGRES_URL" == sqlite* ]]; then
            echo "   ℹ️  Используется SQLite (не требует отдельного сервера)"
        else
            echo "   🔍 Проверка подключения к PostgreSQL..."
            if python3 -c "
import sys
try:
    from sqlalchemy import create_engine, text
    engine = create_engine('$POSTGRES_URL', connect_args={'connect_timeout': 3})
    with engine.connect() as conn:
        result = conn.execute(text('SELECT version()'))
        version = result.fetchone()[0]
    print(f'   ✅ PostgreSQL подключение успешно')
    print(f'      Версия: {version[:50]}...')
    sys.exit(0)
except Exception as e:
    print(f'   ❌ Ошибка подключения: {str(e)}')
    print(f'      💡 Проверьте что PostgreSQL запущен и доступен')
    print(f'      💡 Проверьте строку подключения в .env.mcp')
    sys.exit(1)
" 2>&1; then
                echo ""
            else
                echo ""
            fi
        fi
    else
        echo "   ⚠️  POSTGRES_CONNECTION_STRING не найден в .env.mcp"
    fi
else
    echo "   ⚠️  Файл .env.mcp не найден"
fi
echo ""

# 6. Проверка Redis подключения
echo "6️⃣  Проверка Redis подключения..."
if [ -f ".env.mcp" ]; then
    REDIS_URL=$(grep "^REDIS_URL=" .env.mcp | cut -d'=' -f2- | tr -d '"' | tr -d "'")

    if [ -n "$REDIS_URL" ]; then
        echo "   📝 Найден REDIS_URL в .env.mcp"
        if python3 -c "
import sys
try:
    import redis
    r = redis.from_url('$REDIS_URL', socket_connect_timeout=3)
    r.ping()
    info = r.info()
    print(f'   ✅ Redis подключение успешно')
    print(f'      Версия: {info.get(\"redis_version\", \"unknown\")}')
    sys.exit(0)
except ImportError:
    print(f'   ⚠️  Библиотека redis не установлена')
    sys.exit(1)
except Exception as e:
    print(f'   ❌ Ошибка подключения: {str(e)}')
    print(f'      💡 Проверьте что Redis запущен и доступен')
    sys.exit(1)
" 2>&1; then
            echo ""
        else
            echo ""
        fi
    else
        echo "   ⏭️  REDIS_URL не указан в .env.mcp (опционально)"
    fi
else
    echo "   ⚠️  Файл .env.mcp не найден"
fi
echo ""

# Итоги
echo "========================================"
echo "✅ Проверка завершена"
echo ""
echo "💡 Следующие шаги:"
echo "   1. Если все проверки прошли успешно, перезапустите Cursor IDE"
echo "   2. Запустите тест: python3 scripts/test_mcp_connections.py"
echo "   3. Проверьте MCP серверы в Cursor IDE"
echo ""
