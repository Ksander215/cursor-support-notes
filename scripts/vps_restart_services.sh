#!/bin/bash
# Скрипт для безопасного перезапуска всех сервисов на VPS
# Использование: bash scripts/vps_restart_services.sh

set -e

cd /opt/sec-scanner

echo "🛑 Остановка всех контейнеров..."
docker compose -f docker-compose.prod.yml down

echo ""
echo "🚀 Запуск всех сервисов..."
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "⏳ Ожидание готовности сервисов (10 секунд)..."
sleep 10

echo ""
echo "📊 Статус контейнеров:"
docker compose -f docker-compose.prod.yml ps

echo ""
echo "🏥 Проверка health checks..."
echo "   API:"
curl -f http://127.0.0.1:8000/healthz && echo " ✅" || echo " ❌"

echo ""
echo "✅ Перезапуск завершен!"
