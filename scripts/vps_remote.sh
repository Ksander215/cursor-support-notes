#!/usr/bin/env bash
# vps_remote.sh — удалённое управление VPS по SSH
#
# Использование:
#   ./scripts/vps_remote.sh <task>           — выполнить задачу
#   ./scripts/vps_remote.sh exec -- "cmd"    — выполнить команду на VPS
#
# Задачи:
#   check-ssh              — проверить SSH-подключение
#   check-env              — проверить .env.production (наличие STRIPE_*, без вывода значений)
#   fix-compose-env-file   — добавить env_file: .env.production в api и worker
#   check-stripe           — проверить, что STRIPE_* попадают в контейнер api
#   run-migrations         — выполнить alembic upgrade head в контейнере api
#   sync                  — rsync кода на VPS (как auto-deploy, без деплоя)
#   deploy [service]      — sync + перезапуск сервисов (all|api|frontend)
#   exec -- "cmd"         — выполнить произвольную команду на VPS
#
# Настройка (один раз):
#   ./scripts/setup-auto-deploy.sh   # создаёт .vps-deploy.env
#   ssh-copy-id -i ~/.ssh/id_ed25519 root@VPS_HOST   # вход без пароля
#
# Агенты (AGENTS.md): пишут в agent_outputs/*.md; этот скрипт применяет
# изменения на VPS по решению оператора (не автоматически).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Конфиг (тот же, что у auto-deploy)
if [ -f .vps-deploy.env ]; then
    set -a
    source .vps-deploy.env
    set +a
fi

VPS_HOST="${VPS_HOST:-}"
VPS_USER="${VPS_USER:-root}"
VPS_PATH="${VPS_PATH:-/opt/sec-scanner}"
SSH_KEY="${SSH_KEY:-}"

if [ -z "$SSH_KEY" ]; then
    if [ -f ~/.ssh/id_ed25519 ]; then
        SSH_KEY=~/.ssh/id_ed25519
    elif [ -f ~/.ssh/id_rsa ]; then
        SSH_KEY=~/.ssh/id_rsa
    fi
fi

SSH_OPTS=(-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
[ -n "${SSH_KEY:-}" ] && [ -f "$SSH_KEY" ] && SSH_OPTS=(-i "$SSH_KEY" "${SSH_OPTS[@]}")

setup_ssh_agent() {
    if [ -z "${SSH_AUTH_SOCK:-}" ]; then
        eval "$(ssh-agent -s)" > /dev/null
    fi
    if [ -n "${SSH_KEY:-}" ] && [ -f "$SSH_KEY" ] && ! ssh-add -l 2>/dev/null | grep -q "$(basename "$SSH_KEY")"; then
        ssh-add "$SSH_KEY" 2>/dev/null || true
    fi
}

# Выполнить команду на VPS (без TTY)
vps_run() {
    if [ -z "${VPS_HOST:-}" ]; then
        echo "VPS_HOST не задан. Загрузите .vps-deploy.env или export VPS_HOST=..."
        return 1
    fi
    ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" "$@"
}

# Выполнить команду на VPS с TTY (для nano, vi и т.п.)
vps_run_tty() {
    if [ -z "${VPS_HOST:-}" ]; then
        echo "VPS_HOST не задан. Загрузите .vps-deploy.env или export VPS_HOST=..."
        return 1
    fi
    ssh -t "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" "$@"
}

# Задача: проверить SSH
task_check_ssh() {
    setup_ssh_agent
    echo "Проверка SSH: $VPS_USER@$VPS_HOST"
    vps_run "echo 'SSH OK'"
}

# Задача: проверить наличие STRIPE_* в .env.production (без вывода значений)
task_check_env() {
    echo "Проверка .env.production на VPS (наличие STRIPE_*, без значений)..."
    vps_run "grep -E '^STRIPE_' $VPS_PATH/.env.production 2>/dev/null | sed 's/=.*/=***/' || echo '(файл или переменные не найдены)'"
}

# Задача: добавить env_file в api и worker, если ещё нет
task_fix_compose_env_file() {
    echo "Добавление env_file в api и worker (если отсутствует)..."
    vps_run "cd $VPS_PATH && python3 << 'PYEOF'
import sys
path = \"$VPS_PATH/docker-compose.prod.yml\"
with open(path, 'r') as f:
    lines = f.readlines()

def find_section(lines, start_marker, end_marker):
    start = end = None
    for i, line in enumerate(lines):
        if line.strip() == start_marker and line.startswith('  ') and not line.startswith('    '):
            start = i
        if start is not None and line.strip() == end_marker and line.startswith('  ') and not line.startswith('    '):
            end = i
            break
    return start, end

api_start, api_end = find_section(lines, 'api:', 'worker:')
worker_start, worker_end = find_section(lines, 'worker:', 'web-check:')
inserted = 0
for section_start, section_end in [(api_start, api_end), (worker_start, worker_end)]:
    if section_start is None or section_end is None:
        continue
    has_env_file = any('env_file' in lines[i] for i in range(section_start, section_end))
    if has_env_file:
        continue
    for i in range(section_start + 1, section_end):
        if lines[i].strip() == 'environment:' and lines[i].startswith('    '):
            block = '    env_file:\n      - .env.production\n'
            lines.insert(i, block)
            inserted += 1
            break
with open(path, 'w') as f:
    f.writelines(lines)
print('Inserted env_file in', inserted, 'section(s).')
PYEOF"
}

# Задача: проверить STRIPE_* в контейнере api
task_check_stripe() {
    echo "Проверка STRIPE_* в контейнере api..."
    vps_run "cd $VPS_PATH && docker compose -f docker-compose.prod.yml exec -T api env 2>/dev/null | grep -E '^STRIPE_' | sed 's/=.*/=***/' || echo '(переменные не найдены или контейнер не запущен)'"
}

# Задача: миграции
task_run_migrations() {
    echo "Выполнение alembic upgrade head на VPS..."
    vps_run "cd $VPS_PATH && docker compose -f docker-compose.prod.yml exec -T api alembic upgrade head"
}

# Задача: sync кода (без деплоя)
task_sync() {
    setup_ssh_agent
    if [ ! -f .rsync-exclude ]; then
        echo "Создаю .rsync-exclude..."
        cat > .rsync-exclude <<'EXCL'
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
EXCL
    fi
    echo "Синхронизация с VPS..."
    RSYNC_SSH="ssh"
    [ -n "${SSH_KEY:-}" ] && [ -f "$SSH_KEY" ] && RSYNC_SSH="ssh -i $SSH_KEY -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new"
    rsync -avz -e "$RSYNC_SSH" --exclude-from=.rsync-exclude \
        ./ "$VPS_USER@$VPS_HOST:$VPS_PATH/"
    echo "Sync завершён."
}

# Задача: deploy (sync + перезапуск)
task_deploy() {
    local service="${1:-all}"
    task_sync
    echo "Перезапуск сервисов: $service"
    if [ "$service" = "api" ]; then
        vps_run "cd $VPS_PATH && docker compose -f docker-compose.prod.yml up -d api worker"
    elif [ "$service" = "frontend" ]; then
        vps_run "cd $VPS_PATH && docker compose -f docker-compose.prod.yml up -d frontend"
    else
        vps_run "cd $VPS_PATH && docker compose -f docker-compose.prod.yml up -d"
    fi
    vps_run "cd $VPS_PATH && docker compose -f docker-compose.prod.yml ps"
}

# Задача: произвольная команда (после exec можно указать --, затем команду)
# Использует TTY для интерактивных команд (nano, vi)
task_exec() {
    shift
    while [ "${1:-}" = "--" ]; do shift; done
    if [ $# -eq 0 ]; then
        echo "Использование: $0 exec -- 'команда на VPS'"
        return 1
    fi
    vps_run_tty "cd $VPS_PATH && $*"
}

usage() {
    echo "Использование: $0 <task> [аргументы]"
    echo ""
    echo "Задачи:"
    echo "  check-ssh              — проверить SSH"
    echo "  check-env              — проверить .env.production (STRIPE_*)"
    echo "  fix-compose-env-file   — добавить env_file в api/worker"
    echo "  check-stripe           — проверить STRIPE_* в контейнере api"
    echo "  run-migrations        — alembic upgrade head"
    echo "  sync                   — rsync кода на VPS"
    echo "  deploy [all|api|frontend] — sync + перезапуск"
    echo "  exec -- 'cmd'          — выполнить команду на VPS"
    echo ""
    echo "Настройка: .vps-deploy.env (VPS_HOST, VPS_USER, VPS_PATH, SSH_KEY)"
    echo "Без пароля: ssh-copy-id -i \$SSH_KEY $VPS_USER@\$VPS_HOST"
}

main() {
    local task="${1:-}"
    shift || true

    case "$task" in
        check-ssh)           task_check_ssh ;;
        check-env)           task_check_env ;;
        fix-compose-env-file) task_fix_compose_env_file ;;
        check-stripe)        task_check_stripe ;;
        run-migrations)      task_run_migrations ;;
        sync)                task_sync ;;
        deploy)              task_deploy "${1:-all}" ;;
        exec)                task_exec "$@" ;;
        help|--help|-h|"")   usage ;;
        *)
            echo "Неизвестная задача: $task"
            usage
            exit 1
            ;;
    esac
}

main "$@"
