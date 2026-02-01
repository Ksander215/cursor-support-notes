#!/usr/bin/env bash
set -euo pipefail

# Автоматический деплой на VPS при изменениях
# Использование:
#   ./scripts/auto-deploy.sh [--dry-run] [--frontend-only] [--api-only]
#
# Настройка (один раз):
#   ./scripts/setup-auto-deploy.sh

# Load config if exists
if [ -f .vps-deploy.env ]; then
    set -a
    source .vps-deploy.env
    set +a
fi

DRY_RUN="${1:-}"
FRONTEND_ONLY="${2:-}"
API_ONLY="${3:-}"

# Конфигурация (можно вынести в .env или передавать как параметры)
VPS_HOST="${VPS_HOST:-your-vps-ip-or-domain}"
VPS_USER="${VPS_USER:-root}"
VPS_PATH="${VPS_PATH:-/opt/sec-scanner}"
SSH_KEY="${SSH_KEY:-~/.ssh/id_rsa}"

# Настройка ssh-agent для ключей с парольной фразой
setup_ssh_agent() {
    # Проверить, запущен ли ssh-agent
    if [ -z "${SSH_AUTH_SOCK:-}" ]; then
        echo "🔑 Запуск ssh-agent..."
        eval "$(ssh-agent -s)" > /dev/null
    fi

    # Проверить, добавлен ли ключ в ssh-agent
    if ! ssh-add -l 2>/dev/null | grep -q "$(basename "$SSH_KEY")"; then
        echo "🔑 Добавление SSH ключа в ssh-agent..."
        echo "   Введите парольную фразу для ключа (если требуется):"
        ssh-add "$SSH_KEY" 2>/dev/null || {
            echo "⚠️  Не удалось добавить ключ в ssh-agent"
            echo "   Продолжаю без ssh-agent (может запрашивать парольную фразу)"
        }
    fi
}

# Проверка SSH подключения
check_ssh() {
    echo "🔍 Проверка SSH подключения к VPS..."
    if ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
        "$VPS_USER@$VPS_HOST" "echo 'SSH connection OK'" 2>/dev/null; then
        echo "✅ SSH подключение работает"
        return 0
    else
        echo "❌ Не удалось подключиться к VPS"
        echo "   Проверьте: VPS_HOST, VPS_USER, SSH_KEY"
        return 1
    fi
}

# Синхронизация кода через rsync
sync_code() {
    local exclude_file=".rsync-exclude"

    # Использовать существующий файл или создать базовый
    if [ ! -f "$exclude_file" ]; then
        echo "⚠️  Файл .rsync-exclude не найден, создаю базовый..."
        cat > "$exclude_file" <<EOF
# Исключения для rsync
.env.production
.env.local
*.pyc
__pycache__/
node_modules/
.venv/
venv/
.git/
*.log
dist/
build/
.astro/
.cache/
*.db
*.sqlite
pgdata/
redisdata/
EOF
    fi

    echo "📦 Синхронизация кода с VPS..."

    if [ "$DRY_RUN" = "--dry-run" ]; then
        rsync -avz --dry-run \
            -e "ssh -i $SSH_KEY" \
            --exclude-from="$exclude_file" \
            ./ "$VPS_USER@$VPS_HOST:$VPS_PATH/"
    else
        rsync -avz \
            -e "ssh -i $SSH_KEY" \
            --exclude-from="$exclude_file" \
            ./ "$VPS_USER@$VPS_HOST:$VPS_PATH/"
        echo "✅ Код синхронизирован"
    fi
}

# Деплой на VPS
deploy_on_vps() {
    local service="${1:-all}"

    echo "🚀 Деплой на VPS..."

    if [ "$DRY_RUN" = "--dry-run" ]; then
        echo "🔍 [DRY RUN] Команды которые будут выполнены:"
        ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" <<EOF
cd $VPS_PATH
echo "docker compose -f docker-compose.prod.yml build $service"
echo "docker compose -f docker-compose.prod.yml up -d $service"
EOF
        return 0
    fi

    ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" <<EOF
set -e
cd $VPS_PATH

# Проверить что .env.production существует
if [ ! -f .env.production ]; then
    echo "⚠️  .env.production не найден. Запускаю vps_init_env.sh..."
    ./scripts/vps_init_env.sh || true
fi

# Пересобрать и перезапустить сервисы
if [ "$service" = "frontend" ]; then
    echo "🔨 Пересборка frontend..."
    docker compose -f docker-compose.prod.yml build frontend
    docker compose -f docker-compose.prod.yml up -d frontend
elif [ "$service" = "api" ]; then
    echo "🔨 Пересборка api и worker..."
    docker compose -f docker-compose.prod.yml build api worker
    docker compose -f docker-compose.prod.yml up -d api worker
else
    echo "🔨 Пересборка всех сервисов..."
    docker compose -f docker-compose.prod.yml build
    docker compose -f docker-compose.prod.yml up -d
fi

# Проверить статус
echo "📊 Статус контейнеров:"
docker compose -f docker-compose.prod.yml ps

# Health check
echo "🏥 Проверка здоровья API..."
sleep 5
curl -f http://127.0.0.1:8000/healthz || echo "⚠️  API health check failed"
EOF
}

# Основная логика
main() {
    echo "🚀 Автоматический деплой на VPS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Настройка ssh-agent (для ключей с парольной фразой)
    setup_ssh_agent

    # Проверка SSH
    if ! check_ssh; then
        echo ""
        echo "💡 Настройте переменные окружения:"
        echo "   export VPS_HOST=your-vps-ip"
        echo "   export VPS_USER=root"
        echo "   export SSH_KEY=~/.ssh/id_rsa"
        echo ""
        echo "   Или передайте параметры:"
        echo "   VPS_HOST=1.2.3.4 VPS_USER=root ./scripts/auto-deploy.sh"
        exit 1
    fi

    # Определить какой сервис деплоить
    local service="all"
    if [ "$FRONTEND_ONLY" = "--frontend-only" ]; then
        service="frontend"
    elif [ "$API_ONLY" = "--api-only" ]; then
        service="api"
    fi

    # Синхронизация кода
    sync_code

    # Деплой
    if [ "$DRY_RUN" != "--dry-run" ]; then
        deploy_on_vps "$service"
        echo ""
        echo "✅ Деплой завершен!"
        echo "🌐 Проверьте:"
        echo "   - UI: https://sec-scanner.pro/app/dashboard"
        echo "   - API: https://api.sec-scanner.pro/healthz"
    fi
}

main "$@"
