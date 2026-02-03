#!/usr/bin/env bash
# Локальная разработка: API в Docker, Frontend в dev-режиме (hot reload)
# Использование: bash scripts/start-local-dev.sh

set -e
cd "$(dirname "$0")/.."

echo "🛠️  Локальная разработка sec-scanner.pro"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Будет запущено:"
echo "  • API + Web-Check в Docker (порты 8000, 3000)"
echo "  • Frontend в dev-режиме с hot reload (порт 4321)"
echo ""
echo "В Settings укажите API Base URL: http://localhost:8000"
echo ""

# Проверка Docker
if ! command -v docker &>/dev/null; then
    echo "❌ Docker не найден. Установите Docker или запустите вручную:"
    echo "   Терминал 1: docker-compose up api web-check"
    echo "   Терминал 2: cd services/frontend && npm run dev"
    exit 1
fi

# Запуск API и Web-Check в фоне
echo "📦 Запуск API и Web-Check (Docker)..."
docker-compose up -d api web-check 2>/dev/null || docker compose up -d api web-check 2>/dev/null || true

echo "⏳ Ожидание готовности API (5 сек)..."
sleep 5

# Проверка API
if curl -s http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "✅ API доступен: http://localhost:8000"
else
    echo "⚠️  API пока не отвечает. Подождите и проверьте: curl http://localhost:8000/healthz"
fi

echo ""
echo "🌐 Запуск Frontend (dev с hot reload)..."
echo "   Откройте: http://localhost:4321"
echo "   Остановка: Ctrl+C"
echo ""

cd services/frontend
# Порт 4321 чтобы не конфликтовать с web-check (3000)
npx astro dev --host 0.0.0.0 --port 4321
