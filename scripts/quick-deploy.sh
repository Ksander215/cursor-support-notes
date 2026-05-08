#!/usr/bin/env bash
set -euo pipefail

# Быстрый деплой изменений на VPS
VPS_HOST="${VPS_HOST:?}"
VPS_USER="root"
VPS_PATH="/opt/sec-scanner"
SSH_KEY="$HOME/.ssh/id_ed25519"

echo "🚀 Быстрый деплой на VPS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Проверка SSH
echo "🔍 Проверка SSH подключения..."
if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "❌ Не удалось подключиться к VPS"
    exit 1
fi
echo "✅ SSH подключение OK"

# Синхронизация измененных файлов
echo ""
echo "📦 Синхронизация файлов..."
rsync -avz --progress \
    -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
    services/frontend/src/pages/app/settings.astro \
    services/frontend/src/lib/api.ts \
    src/sec_scanner/api.py \
    src/sec_scanner/schemas.py \
    src/sec_scanner/db.py \
    "$VPS_USER@$VPS_HOST:$VPS_PATH/"

echo "✅ Файлы синхронизированы"

# Пересборка и перезапуск frontend
echo ""
echo "🔨 Пересборка frontend..."
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" << 'REMOTE_SCRIPT'
set -e
cd /opt/sec-scanner
docker compose -f docker-compose.prod.yml build frontend
docker compose -f docker-compose.prod.yml up -d frontend
echo "✅ Frontend перезапущен"
REMOTE_SCRIPT

# Пересборка и перезапуск API
echo ""
echo "🔨 Пересборка API..."
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" << 'REMOTE_SCRIPT'
set -e
cd /opt/sec-scanner
docker compose -f docker-compose.prod.yml build api worker
docker compose -f docker-compose.prod.yml up -d api worker
echo "✅ API и worker перезапущены"
REMOTE_SCRIPT

# Проверка статуса
echo ""
echo "📊 Статус контейнеров:"
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cd /opt/sec-scanner && docker compose -f docker-compose.prod.yml ps"

echo ""
echo "🏥 Проверка здоровья API..."
sleep 3
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "curl -f http://127.0.0.1:8000/healthz || echo '⚠️  API health check failed'"

echo ""
echo "✅ Деплой завершен!"
echo "🌐 Проверьте:"
echo "   - UI: https://sec-scanner.pro/app/settings"
echo "   - API: https://api.sec-scanner.pro/healthz"
