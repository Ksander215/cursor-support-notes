#!/usr/bin/env bash
set -euo pipefail

# Backup script for /opt/sec-scanner (docker-compose.prod.yml).
# - Postgres: custom-format dump + globals
# - Nginx: site config + template
# - App: compose file
# - Secrets: .env.production ONLY encrypted with age (recommended)
#
# Intended to be copied/run on VPS under /opt/sec-scanner/ops/.
#
# IMPORTANT:
# - Do NOT store plaintext .env.production in backups.
# - Provide AGE_RECIPIENT (public key) to enable env encryption.

APP_DIR="${APP_DIR:-/opt/sec-scanner}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"
PROJECT_NAME="${PROJECT_NAME:-sec-scanner}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/sec-scanner}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

# Encryption for .env.production (no secrets in plaintext backups)
AGE_RECIPIENT="${AGE_RECIPIENT:-}"   # e.g. age1...

umask 077

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[error] Missing $ENV_FILE"
  exit 1
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "[error] Missing $COMPOSE_FILE"
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="$BACKUP_DIR/$PROJECT_NAME/$TS"
mkdir -p "$OUT_DIR"

echo "[1/6] Postgres dump (custom format)"
docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T \
  -e PGPASSWORD="${POSTGRES_PASSWORD:-}" \
  db pg_dump \
    -U "${POSTGRES_USER:-sec_scanner}" \
    -d "${POSTGRES_DB:-sec_scanner}" \
    -Fc \
    --no-owner --no-acl \
  > "$OUT_DIR/postgres.dump"

echo "[2/6] Postgres globals (roles/permissions)"
docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T \
  -e PGPASSWORD="${POSTGRES_PASSWORD:-}" \
  db pg_dumpall \
    -U "${POSTGRES_USER:-sec_scanner}" \
    --globals-only \
  > "$OUT_DIR/postgres.globals.sql"

echo "[3/6] Nginx config backup"
if [[ -f /etc/nginx/sites-available/sec-scanner ]]; then
  cp -a /etc/nginx/sites-available/sec-scanner "$OUT_DIR/nginx.sec-scanner.conf"
else
  echo "[warn] /etc/nginx/sites-available/sec-scanner not found (skip)"
fi
if [[ -f "$APP_DIR/deploy/nginx/sec-scanner.conf.template" ]]; then
  cp -a "$APP_DIR/deploy/nginx/sec-scanner.conf.template" "$OUT_DIR/nginx.template.conf"
fi

echo "[4/6] Compose file backup"
cp -a "$COMPOSE_FILE" "$OUT_DIR/docker-compose.prod.yml"

echo "[5/6] .env.production backup (encrypted)"
if command -v age >/dev/null 2>&1 && [[ -n "$AGE_RECIPIENT" ]]; then
  age -r "$AGE_RECIPIENT" -o "$OUT_DIR/.env.production.age" "$ENV_FILE"
else
  echo "[warn] Skipping .env.production backup: need 'age' + AGE_RECIPIENT (public key)."
fi

echo "[6/6] Retention cleanup (> ${RETENTION_DAYS} days)"
if command -v find >/dev/null 2>&1; then
  find "$BACKUP_DIR/$PROJECT_NAME" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION_DAYS" -print0 2>/dev/null | xargs -0r rm -rf
fi

echo "[ok] Backup created: $OUT_DIR"

