#!/bin/bash
# Скрипт для установки всех зависимостей проекта
# Дата: 2026-01-29

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "📦 Установка зависимостей проекта"
echo "=================================="
echo ""

# Проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python3."
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ Найден: $PYTHON_VERSION"
echo ""

# Проверяем/создаем виртуальное окружение
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

# Обновляем pip
echo "📥 Обновляем pip..."
pip install --upgrade pip --quiet
echo "✅ pip обновлен"
echo ""

# Устанавливаем Python зависимости
if [ -f "requirements.txt" ]; then
    echo "📥 Устанавливаем Python зависимости из requirements.txt..."
    pip install -r requirements.txt
    echo "✅ Python зависимости установлены"
else
    echo "⚠️  Файл requirements.txt не найден"
fi
echo ""

# Проверяем Node.js
if ! command -v node &> /dev/null; then
    echo "⚠️  Node.js не найден. Установите Node.js для работы с frontend."
    echo "   Рекомендуемая версия: Node.js 20.x или 22.x"
else
    NODE_VERSION=$(node --version)
    echo "✅ Найден Node.js: $NODE_VERSION"

    # Проверяем версию Node.js
    NODE_MAJOR=$(echo $NODE_VERSION | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "$NODE_MAJOR" -lt 18 ] || ([ "$NODE_MAJOR" -eq 21 ]); then
        echo "⚠️  Предупреждение: Node.js $NODE_VERSION может иметь проблемы совместимости"
        echo "   Рекомендуется использовать Node.js 18.20.8+, 20.x или 22.x"
        echo "   Но установка продолжится..."
    fi
    echo ""

    # Устанавливаем frontend зависимости
    if [ -d "services/frontend" ]; then
        echo "📥 Устанавливаем frontend зависимости..."
        cd services/frontend
        npm install
        cd "$PROJECT_ROOT"
        echo "✅ Frontend зависимости установлены"
    else
        echo "⚠️  Директория services/frontend не найдена"
    fi
fi
echo ""

echo "✅ Все зависимости установлены!"
echo ""
echo "📋 Следующие шаги:"
echo "   1. Активируйте виртуальное окружение: source .venv/bin/activate"
echo "   2. Примените миграции БД: alembic upgrade head"
echo "   3. Запустите сервисы: docker-compose -f docker-compose.prod.yml up -d"
