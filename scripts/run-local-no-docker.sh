#!/usr/bin/env bash
# Запуск API и Frontend локально БЕЗ Docker (удобно при проблемах с сетью/Docker Hub)
# Использование: запустите в двух терминалах команды ниже или только API/только frontend.

set -e
cd "$(dirname "$0")/.."

echo "🛠️  Локальная разработка без Docker"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Запустите в ДВУХ терминалах:"
echo ""
echo "  Терминал 1 — API:"
echo "    cd $(pwd)"
echo "    source .venv/bin/activate"
echo "    uvicorn app:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "  Терминал 2 — Frontend:"
echo "    cd $(pwd)/services/frontend"
echo "    npm run dev"
echo ""
echo "Если .venv нет: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
echo "Если node_modules нет: cd services/frontend && npm install"
echo ""
echo "Откройте: http://localhost:3000  (или порт из вывода npm run dev)"
echo "API Base URL в Settings: http://localhost:8000"
echo ""

# Запуск только API в этом терминале (если вызвано с аргументом api)
if [ "${1:-}" = "api" ]; then
    if [ ! -d .venv ]; then
        echo "Создаю .venv..."
        python3 -m venv .venv
        # shellcheck source=.venv/bin/activate disable=SC1091
        . .venv/bin/activate
        pip install -r requirements.txt
    else
        # shellcheck source=.venv/bin/activate disable=SC1091
        . .venv/bin/activate
    fi
    echo "Запуск API на http://localhost:8000 ..."
    exec uvicorn app:app --reload --host 0.0.0.0 --port 8000
fi

# Запуск только frontend
if [ "${1:-}" = "frontend" ]; then
    cd services/frontend
    [ ! -d node_modules ] && npm install
    echo "Запуск Frontend (dev)..."
    exec npm run dev
fi

exit 0
