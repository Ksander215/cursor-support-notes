#!/usr/bin/env bash
set -euo pipefail

# Восстановление PostgreSQL из бэкапа
# Использование: ./vps_restore_db.sh /var/backups/sec-scanner/postgres_20260202_030000.dump

APP_DIR="${APP_DIR:-/opt/sec-scanner}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"

BACKUP_FILE="${1:-}"

if [[ -z "$BACKUP_FILE" ]]; then
    echo "Использование: $0 <путь_к_бэкапу.dump>"
    echo ""
    echo "Пример:"
    echo "  $0 /var/backups/sec-scanner/postgres_20260202_030000.dump"
    echo ""
    echo "Доступные бэкапы:"
    # shellcheck disable=SC2012
    ls -lh /var/backups/sec-scanner/postgres_*.dump 2>/dev/null | tail -5 || echo "  (бэкапов не найдено)"
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "❌ Ошибка: файл $BACKUP_FILE не найден"
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ Ошибка: файл $ENV_FILE не найден"
    exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "❌ Ошибка: файл $COMPOSE_FILE не найден"
    exit 1
fi

# Загрузить переменные окружения
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

echo "⚠️  ВНИМАНИЕ: Восстановление перезапишет текущую базу данных!"
echo "Бэкап: $BACKUP_FILE"
echo "Размер: $(du -h "$BACKUP_FILE" | cut -f1)"
echo ""
read -p "Продолжить восстановление? (yes/no): " -r
if [[ ! $REPLY == "yes" ]]; then
    echo "Отменено."
    exit 0
fi

echo ""
echo "🛑 Остановка API и Worker..."
docker compose -f "$COMPOSE_FILE" stop api worker || true

echo "✅ Проверка что DB запущена..."
docker compose -f "$COMPOSE_FILE" up -d db
sleep 2

echo "🔄 Завершение активных подключений..."
docker compose -f "$COMPOSE_FILE" exec -T \
    -e PGPASSWORD="${POSTGRES_PASSWORD:?}" \
    db psql -U "${POSTGRES_USER:?}" -d "postgres" -v ON_ERROR_STOP=1 <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'sec_scanner' AND pid <> pg_backend_pid();
SQL

echo "📥 Восстановление базы данных..."
if docker compose -f "$COMPOSE_FILE" exec -T \
    -e PGPASSWORD="${POSTGRES_PASSWORD:?}" \
    db pg_restore \
    -U "${POSTGRES_USER:?}" \
    -d sec_scanner \
    --clean \
    --if-exists \
    < "$BACKUP_FILE"; then
    echo "✅ База данных восстановлена успешно!"
else
    echo "❌ Ошибка при восстановлении базы данных"
    exit 1
fi

echo "🚀 Запуск API и Worker..."
docker compose -f "$COMPOSE_FILE" start api worker

echo ""
echo "✅ Восстановление завершено!"
echo "Проверьте логи: docker compose -f $COMPOSE_FILE logs api"
