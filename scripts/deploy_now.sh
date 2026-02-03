#!/usr/bin/env bash
set -euo pipefail

# =====================================================
# Скрипт деплоя sec-scanner.pro на VPS
# Дата: 2026-02-01
# =====================================================

echo "🚀 Деплой sec-scanner.pro на VPS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Конфигурация
VPS_HOST="85.239.38.163"
VPS_USER="root"
VPS_PATH="/opt/sec-scanner"
SSH_KEY="$HOME/.ssh/id_ed25519"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =====================================================
# Шаг 1: Настройка SSH Agent
# =====================================================
echo ""
log_info "Шаг 1/6: Настройка SSH agent..."

# Запустить ssh-agent если не запущен
if [ -z "${SSH_AUTH_SOCK:-}" ]; then
    log_info "Запуск ssh-agent..."
    eval "$(ssh-agent -s)"
fi

# Добавить ключ если не добавлен
if ! ssh-add -l 2>/dev/null | grep -q "ed25519"; then
    log_info "Добавление SSH ключа (введите парольную фразу)..."
    ssh-add "$SSH_KEY"
fi

# =====================================================
# Шаг 2: Проверка SSH подключения
# =====================================================
echo ""
log_info "Шаг 2/6: Проверка SSH подключения..."

if ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" "echo 'SSH OK'"; then
    log_info "✅ SSH подключение работает"
else
    log_error "❌ Не удалось подключиться к VPS"
    exit 1
fi

# =====================================================
# Шаг 3: Синхронизация кода
# =====================================================
echo ""
log_info "Шаг 3/6: Синхронизация кода на VPS..."

rsync -avz --progress \
    -e "ssh -o StrictHostKeyChecking=no" \
    --exclude-from=".rsync-exclude" \
    ./ "$VPS_USER@$VPS_HOST:$VPS_PATH/"

log_info "✅ Код синхронизирован"

# =====================================================
# Шаг 4: Применение миграций
# =====================================================
echo ""
log_info "Шаг 4/6: Применение миграций БД..."

ssh "$VPS_USER@$VPS_HOST" << 'MIGRATION'
cd /opt/sec-scanner

# Проверить .env.production
if [ ! -f .env.production ]; then
    echo "⚠️  .env.production не найден!"
    exit 1
fi

# Убедиться что БД запущена
docker compose -f docker-compose.prod.yml up -d db
sleep 5

# Применить миграции
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

echo "✅ Миграции применены"
MIGRATION

# =====================================================
# Шаг 5: Пересборка и перезапуск
# =====================================================
echo ""
log_info "Шаг 5/6: Пересборка и перезапуск контейнеров..."

ssh "$VPS_USER@$VPS_HOST" << 'DEPLOY'
cd /opt/sec-scanner

echo "🔨 Пересборка Docker образов..."
docker compose -f docker-compose.prod.yml build

echo "🔄 Перезапуск сервисов..."
docker compose -f docker-compose.prod.yml up -d

echo "⏳ Ожидание запуска (15 сек)..."
sleep 15

echo "📊 Статус контейнеров:"
docker compose -f docker-compose.prod.yml ps
DEPLOY

log_info "✅ Контейнеры перезапущены"

# =====================================================
# Шаг 6: Проверка здоровья
# =====================================================
echo ""
log_info "Шаг 6/6: Проверка здоровья сервисов..."

ssh "$VPS_USER@$VPS_HOST" << 'HEALTH'
cd /opt/sec-scanner

echo "🏥 Health check:"
if curl -sf http://127.0.0.1:8000/healthz > /dev/null; then
    echo "✅ /healthz - OK"
else
    echo "❌ /healthz - FAILED"
fi

echo ""
echo "🔍 Readiness check:"
if curl -sf http://127.0.0.1:8000/readyz > /dev/null; then
    echo "✅ /readyz - OK"
else
    echo "❌ /readyz - FAILED"
fi

echo ""
echo "📋 Версия миграции:"
docker compose -f docker-compose.prod.yml run --rm api alembic current 2>/dev/null | tail -1
HEALTH

# =====================================================
# Завершение
# =====================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "🎉 Деплой завершён!"
echo ""
echo "Проверьте:"
echo "  📱 UI: https://sec-scanner.pro/app/dashboard"
echo "  🔌 API: https://api.sec-scanner.pro/healthz"
echo "  📖 Docs: https://api.sec-scanner.pro/docs"
echo ""
