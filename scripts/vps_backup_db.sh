#!/usr/bin/env bash
set -euo pipefail

# Автоматический бэкап PostgreSQL для sec-scanner.pro
# Используется в cron для ежедневных бэкапов
#
# Настройка:
#   BACKUP_DIR - директория для бэкапов (по умолчанию /var/backups/sec-scanner)
#   RETENTION_DAYS - сколько дней хранить бэкапы (по умолчанию 30)
#   LOG_FILE - файл для логов (по умолчанию /var/log/sec-scanner-backup.log)

APP_DIR="${APP_DIR:-/opt/sec-scanner}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/sec-scanner}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
LOG_FILE="${LOG_FILE:-/var/log/sec-scanner-backup.log}"

# Создать директорию для логов если нужно
mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$BACKUP_DIR"

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Начало бэкапа PostgreSQL ==="

# Проверка наличия файлов
if [[ ! -f "$ENV_FILE" ]]; then
    log "[ERROR] Файл $ENV_FILE не найден"
    exit 1
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
    log "[ERROR] Файл $COMPOSE_FILE не найден"
    exit 1
fi

# Загрузить переменные окружения
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Проверка что контейнер db запущен
if ! docker compose -f "$COMPOSE_FILE" ps db | grep -q "Up"; then
    log "[ERROR] Контейнер db не запущен"
    exit 1
fi

# Создать директорию для бэкапа
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/postgres_${TIMESTAMP}.dump"
BACKUP_GLOBALS="$BACKUP_DIR/postgres_globals_${TIMESTAMP}.sql"

log "Создание бэкапа: $BACKUP_FILE"

# Бэкап базы данных (custom format - сжатый)
if docker compose -f "$COMPOSE_FILE" exec -T \
    -e PGPASSWORD="${POSTGRES_PASSWORD:?}" \
    db pg_dump \
    -U "${POSTGRES_USER:?}" \
    -d "${POSTGRES_DB:?}" \
    -Fc \
    --no-owner --no-acl \
    > "$BACKUP_FILE" 2>>"$LOG_FILE"; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "[OK] Бэкап БД создан: $BACKUP_FILE ($BACKUP_SIZE)"
else
    log "[ERROR] Ошибка при создании бэкапа БД"
    exit 1
fi

# Бэкап глобальных объектов (роли, права)
if docker compose -f "$COMPOSE_FILE" exec -T \
    -e PGPASSWORD="${POSTGRES_PASSWORD:?}" \
    db pg_dumpall \
    -U "${POSTGRES_USER:?}" \
    --globals-only \
    > "$BACKUP_GLOBALS" 2>>"$LOG_FILE"; then
    log "[OK] Бэкап глобальных объектов создан: $BACKUP_GLOBALS"
else
    log "[WARN] Ошибка при создании бэкапа глобальных объектов (не критично)"
fi

# Ротация старых бэкапов
log "Очистка старых бэкапов (старше $RETENTION_DAYS дней)"
DELETED_COUNT=0
while IFS= read -r -d '' old_backup; do
    if rm -f "$old_backup"; then
        DELETED_COUNT=$((DELETED_COUNT + 1))
        log "Удалён старый бэкап: $(basename "$old_backup")"
    fi
done < <(find "$BACKUP_DIR" -name "postgres_*.dump" -type f -mtime "+$RETENTION_DAYS" -print0 2>/dev/null || true)

while IFS= read -r -d '' old_globals; do
    if rm -f "$old_globals"; then
        log "Удалён старый бэкап глобальных объектов: $(basename "$old_globals")"
    fi
done < <(find "$BACKUP_DIR" -name "postgres_globals_*.sql" -type f -mtime "+$RETENTION_DAYS" -print0 2>/dev/null || true)

if [[ $DELETED_COUNT -gt 0 ]]; then
    log "Удалено старых бэкапов: $DELETED_COUNT"
fi

# Проверка дискового пространства
DISK_USAGE=$(df -h "$BACKUP_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
if [[ $DISK_USAGE -gt 85 ]]; then
    log "[WARN] Дисковое пространство заполнено на ${DISK_USAGE}%"
fi

# Статистика бэкапов
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "postgres_*.dump" -type f | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Всего бэкапов: $TOTAL_BACKUPS, общий размер: $TOTAL_SIZE"

log "=== Бэкап завершён успешно ==="
exit 0
