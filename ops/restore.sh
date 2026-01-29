#!/usr/bin/env bash
set -euo pipefail

# Restore Postgres from a backup directory created by ops/backup.sh
# WARNING: causes downtime for API/worker during restore.
#
# Intended to be copied/run on VPS under /opt/sec-scanner/ops/.

APP_DIR="${APP_DIR:-/opt/sec-scanner}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"

BACKUP_DIR="${1:-}"
if [[ -z "$BACKUP_DIR" ]]; then
  echo "Usage: $0 /var/backups/sec-scanner/sec-scanner/<timestamp>"
  exit 2
fi
if [[ ! -f "$BACKUP_DIR/postgres.dump" ]]; then
  echo "[error] Missing $BACKUP_DIR/postgres.dump"
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "[error] Missing $ENV_FILE"
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

echo "[1/7] Stop API + worker (reduce active connections)"
docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" stop api worker || true

echo "[2/7] Ensure db is running"
docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d db

echo "[3/7] Terminate existing DB connections"
docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T \
  -e PGPASSWORD="${POSTGRES_PASSWORD:-}" \
  db psql -U "${POSTGRES_USER:-sec_scanner}" -d "postgres" -v ON_ERROR_STOP=1 <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'sec_scanner' AND pid <> pg_backend_pid();
SQL

echo "[4/7] Restore globals (optional)"
if [[ -f "$BACKUP_DIR/postgres.globals.sql" ]]; then
  docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T \
    -e PGPASSWORD="${POSTGRES_PASSWORD:-}" \
    db psql -U "${POSTGRES_USER:-sec_scanner}" -d "postgres" -v ON_ERROR_STOP=1 < "$BACKUP_DIR/postgres.globals.sql" || true
fi

echo "[5/7] Restore database from custom dump"
docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T \
  -e PGPASSWORD="${POSTGRES_PASSWORD:-}" \
  db pg_restore \
    -U "${POSTGRES_USER:-sec_scanner}" \
    -d "${POSTGRES_DB:-sec_scanner}" \
    --clean --if-exists \
    --no-owner --no-acl \
  < "$BACKUP_DIR/postgres.dump"

echo "[6/7] Start stack"
docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d

echo "[7/7] Quick health check"
curl -fsS "http://127.0.0.1:8000/healthz" >/dev/null && echo "[ok] /healthz" || echo "[warn] /healthz failed"

