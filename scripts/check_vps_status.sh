#!/bin/bash
# Скрипт проверки статуса VPS сервера
# Запуск: bash scripts/check_vps_status.sh

set -e

# Конфигурация
VPS_HOST="${VPS_HOST:?}"
VPS_USER="root"
VPS_PATH="${VPS_PATH:-/opt/sec-scanner}"
SSH_KEY="$HOME/.ssh/id_ed25519"
OUTPUT_FILE="vps_status_report.txt"

echo "🔍 Проверка статуса VPS сервера: $VPS_HOST"
echo "================================================"

# Исправить права на SSH ключ
chmod 600 "$SSH_KEY" 2>/dev/null || true

# Проверка доступности сервера
echo "Проверка доступности сервера..."
if ! ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cd $VPS_PATH && exit" 2>/dev/null; then
    echo "❌ Не удалось подключиться к серверу $VPS_HOST"
    exit 1
fi

echo "✅ Сервер доступен"
echo ""

# Выполнение проверок на VPS
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" << 'REMOTE_SCRIPT' | tee "$OUTPUT_FILE"
cd /opt/sec-scanner 2>/dev/null || { echo "❌ Директория /opt/sec-scanner не найдена"; exit 1; }

echo "=== 📦 СТАТУС DOCKER КОНТЕЙНЕРОВ ==="
docker compose -f docker-compose.prod.yml ps 2>/dev/null || docker-compose -f docker-compose.prod.yml ps 2>/dev/null || echo "Docker Compose не найден"
echo ""

echo "=== 🏥 HEALTH CHECK API ==="
curl -s http://127.0.0.1:8000/healthz 2>/dev/null || echo "API недоступен на localhost:8000"
echo ""
echo ""

echo "=== 🔧 READINESS CHECK ==="
curl -s http://127.0.0.1:8000/readyz 2>/dev/null || echo "Readyz endpoint недоступен"
echo ""
echo ""

echo "=== 💾 ДИСКОВОЕ ПРОСТРАНСТВО ==="
df -h / /var/lib/docker 2>/dev/null | head -5
echo ""

echo "=== 🔐 ВЕРСИЯ ALEMBIC МИГРАЦИЙ ==="
docker compose -f docker-compose.prod.yml exec -T api alembic current 2>/dev/null || echo "Не удалось проверить миграции"
echo ""

echo "=== 📋 ПОСЛЕДНИЕ ЛОГИ API (20 строк) ==="
docker compose -f docker-compose.prod.yml logs --tail=20 api 2>/dev/null || echo "Не удалось получить логи"
echo ""

echo "=== ⚠️ ОШИБКИ В ЛОГАХ (последние 50 строк) ==="
docker compose -f docker-compose.prod.yml logs --tail=50 2>/dev/null | grep -i -E "(error|exception|failed|critical)" | tail -10 || echo "Ошибок не найдено"
echo ""

echo "=== 📊 ИСПОЛЬЗОВАНИЕ РЕСУРСОВ ==="
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null || echo "Не удалось получить статистику"
echo ""

echo "=== 🌐 ПРОВЕРКА ВНЕШНИХ ENDPOINTS ==="
echo -n "sec-scanner.pro: "
curl -s -o /dev/null -w "%{http_code}" https://sec-scanner.pro/ 2>/dev/null || echo "N/A"
echo ""
echo -n "api.sec-scanner.pro/healthz: "
curl -s -o /dev/null -w "%{http_code}" https://api.sec-scanner.pro/healthz 2>/dev/null || echo "N/A"
echo ""

echo ""
echo "=== ✅ ПРОВЕРКА ЗАВЕРШЕНА ==="
echo "Дата: $(date)"
REMOTE_SCRIPT

echo ""
echo "📄 Отчет сохранен в: $OUTPUT_FILE"
echo "================================================"
