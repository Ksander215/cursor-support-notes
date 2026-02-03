#!/usr/bin/env bash
# Скрипт для деплоя изменений на VPS
# Использование: bash scripts/deploy-changes.sh

set -e

VPS_HOST="85.239.38.163"
VPS_USER="root"
VPS_PATH="/opt/sec-scanner"
SSH_KEY="$HOME/.ssh/id_ed25519"
LOG_FILE="deploy_$(date +%Y%m%d_%H%M%S).log"

echo "🚀 Деплой изменений на VPS" | tee -a "$LOG_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$LOG_FILE"

# 1. Копирование файлов
echo "" | tee -a "$LOG_FILE"
echo "📦 Копирование файлов..." | tee -a "$LOG_FILE"

scp -i "$SSH_KEY" services/frontend/src/pages/app/settings.astro "$VPS_USER@$VPS_HOST:$VPS_PATH/services/frontend/src/pages/app/settings.astro" 2>&1 | tee -a "$LOG_FILE"
scp -i "$SSH_KEY" services/frontend/src/lib/api.ts "$VPS_USER@$VPS_HOST:$VPS_PATH/services/frontend/src/lib/api.ts" 2>&1 | tee -a "$LOG_FILE"
scp -i "$SSH_KEY" src/sec_scanner/api.py "$VPS_USER@$VPS_HOST:$VPS_PATH/src/sec_scanner/api.py" 2>&1 | tee -a "$LOG_FILE"
scp -i "$SSH_KEY" src/sec_scanner/schemas.py "$VPS_USER@$VPS_HOST:$VPS_PATH/src/sec_scanner/schemas.py" 2>&1 | tee -a "$LOG_FILE"
scp -i "$SSH_KEY" src/sec_scanner/db.py "$VPS_USER@$VPS_HOST:$VPS_PATH/src/sec_scanner/db.py" 2>&1 | tee -a "$LOG_FILE"

echo "✅ Файлы скопированы" | tee -a "$LOG_FILE"

# 2. Пересборка frontend
echo "" | tee -a "$LOG_FILE"
echo "🔨 Пересборка frontend..." | tee -a "$LOG_FILE"
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cd $VPS_PATH && docker compose -f docker-compose.prod.yml build frontend" 2>&1 | tee -a "$LOG_FILE"
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cd $VPS_PATH && docker compose -f docker-compose.prod.yml up -d frontend" 2>&1 | tee -a "$LOG_FILE"
echo "✅ Frontend перезапущен" | tee -a "$LOG_FILE"

# 3. Пересборка API
echo "" | tee -a "$LOG_FILE"
echo "🔨 Пересборка API и worker..." | tee -a "$LOG_FILE"
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cd $VPS_PATH && docker compose -f docker-compose.prod.yml build api worker" 2>&1 | tee -a "$LOG_FILE"
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cd $VPS_PATH && docker compose -f docker-compose.prod.yml up -d api worker" 2>&1 | tee -a "$LOG_FILE"
echo "✅ API и worker перезапущены" | tee -a "$LOG_FILE"

# 4. Проверка статуса
echo "" | tee -a "$LOG_FILE"
echo "📊 Статус контейнеров:" | tee -a "$LOG_FILE"
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cd $VPS_PATH && docker compose -f docker-compose.prod.yml ps" 2>&1 | tee -a "$LOG_FILE"

# 5. Health check
echo "" | tee -a "$LOG_FILE"
echo "🏥 Проверка здоровья API..." | tee -a "$LOG_FILE"
sleep 3
curl -s https://api.sec-scanner.pro/healthz | tee -a "$LOG_FILE" || echo "⚠️  API health check failed" | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "✅ Деплой завершен!" | tee -a "$LOG_FILE"
echo "📄 Лог сохранен в: $LOG_FILE" | tee -a "$LOG_FILE"
echo "🌐 Проверьте: https://sec-scanner.pro/app/settings" | tee -a "$LOG_FILE"
