#!/bin/bash
# Скрипт для копирования файлов миграций на VPS
# Использование: bash scripts/copy_migrations_to_vps.sh [VPS_IP]

set -e

VPS_IP="${1:-}"
VPS_USER="${VPS_USER:-root}"
VPS_PATH="${VPS_PATH:-/opt/sec-scanner}"
SSH_KEY="${SSH_KEY:-~/.ssh/id_rsa}"

if [ -z "$VPS_IP" ]; then
    echo "❌ Укажите IP адрес VPS"
    echo ""
    echo "Использование:"
    echo "  bash scripts/copy_migrations_to_vps.sh YOUR_VPS_IP"
    echo ""
    echo "Или установите переменные окружения:"
    echo "  export VPS_IP=your-vps-ip"
    echo "  bash scripts/copy_migrations_to_vps.sh"
    exit 1
fi

echo "📦 Копирование файлов миграций на VPS..."
echo "   VPS: $VPS_USER@$VPS_IP:$VPS_PATH"
echo ""

# Файлы миграций для копирования
MIGRATION_FILES=(
    "alembic/versions/20260129_0003_notification_settings.py"
    "alembic/versions/20260129_0004_scan_progress.py"
    "alembic/versions/20260129_0005_default_pricing_plans.py"
)

# Проверка наличия файлов локально
for file in "${MIGRATION_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Файл не найден: $file"
        exit 1
    fi
    echo "✅ Найден: $file"
done

echo ""
echo "📤 Копирование файлов..."

# Копирование каждого файла
for file in "${MIGRATION_FILES[@]}"; do
    echo "   → $file"
    scp -i "$SSH_KEY" "$file" "$VPS_USER@$VPS_IP:$VPS_PATH/$file" || {
        echo "❌ Ошибка при копировании $file"
        exit 1
    }
done

echo ""
echo "✅ Файлы миграций скопированы!"
echo ""
echo "📋 Следующие шаги на VPS:"
echo ""
echo "1. Пересоберите контейнер API:"
echo "   docker compose -f docker-compose.prod.yml build api"
echo ""
echo "2. Перезапустите контейнер:"
echo "   docker compose -f docker-compose.prod.yml up -d api"
echo ""
echo "3. Проверьте файлы в контейнере:"
echo "   docker compose -f docker-compose.prod.yml exec api ls -la /app/alembic/versions/20260129_*.py"
echo ""
echo "4. Примените миграции:"
echo "   docker compose -f docker-compose.prod.yml exec api alembic upgrade head"
echo ""
