#!/usr/bin/env bash
set -euo pipefail

# Minimal alerts without heavy monitoring.
# - container status/health
# - disk usage
# - SSL expiry (Let's Encrypt)
#
# Notification is pluggable: if ALERT_WEBHOOK_URL is set, POST a JSON payload.
# Otherwise prints to stdout (cron can email if configured).
#
# Intended to be copied/run on VPS under /opt/sec-scanner/ops/.

APP_DIR="${APP_DIR:-/opt/sec-scanner}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"

DISK_WARN_PCT="${DISK_WARN_PCT:-85}"
SSL_WARN_DAYS="${SSL_WARN_DAYS:-14}"

ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}" # optional: your own webhook relay

send_alert() {
  local title="$1"
  local body="$2"
  local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $title: $body"
  if [[ -n "$ALERT_WEBHOOK_URL" ]] && command -v curl >/dev/null 2>&1; then
    curl -fsS -X POST -H 'Content-Type: application/json' \
      -d "{\"title\":\"$title\",\"body\":\"$body\"}" \
      "$ALERT_WEBHOOK_URL" >/dev/null || true
  else
    echo "$msg"
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[error] Missing $ENV_FILE"
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

echo "[1/3] Container status"
for svc in db redis api worker web-check; do
  cid="$(docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps -q "$svc" || true)"
  if [[ -z "$cid" ]]; then
    send_alert "container_missing" "service=$svc has no container id"
    continue
  fi
  status="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo unknown)"
  if [[ "$status" != "running" ]]; then
    send_alert "container_down" "service=$svc status=$status health=$health"
  elif [[ "$health" == "unhealthy" ]]; then
    send_alert "container_unhealthy" "service=$svc status=$status health=$health"
  fi
done

echo "[2/3] Disk usage"
root_pct="$(df -P / | awk 'NR==2{gsub(/%/,"",$5); print $5}')"
if [[ "${root_pct:-0}" -ge "$DISK_WARN_PCT" ]]; then
  send_alert "disk_high" "root usage=${root_pct}% (warn>=${DISK_WARN_PCT}%)"
fi

echo "[3/3] SSL expiry"
if [[ -n "${API_DOMAIN:-}" ]] && [[ -f "/etc/letsencrypt/live/${API_DOMAIN}/fullchain.pem" ]]; then
  enddate="$(openssl x509 -enddate -noout -in "/etc/letsencrypt/live/${API_DOMAIN}/fullchain.pem" | cut -d= -f2)"
  end_ts="$(date -d "$enddate" +%s 2>/dev/null || echo 0)"
  now_ts="$(date +%s)"
  days_left="$(( (end_ts - now_ts) / 86400 ))"
  if [[ "$days_left" -le "$SSL_WARN_DAYS" ]]; then
    send_alert "ssl_expiring" "domain=${API_DOMAIN} days_left=${days_left} (warn<=${SSL_WARN_DAYS})"
  fi
else
  echo "[info] SSL cert not found for API_DOMAIN (skip)"
fi
