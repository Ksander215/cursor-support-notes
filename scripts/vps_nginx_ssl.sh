#!/usr/bin/env bash
set -euo pipefail

cd /opt/sec-scanner

SUDO="sudo"
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
fi

if [ ! -f .env.production ]; then
  echo "Missing .env.production. Create it from .env.production.example"
  exit 1
fi

set -a
. ./.env.production
set +a

: "${API_DOMAIN:?API_DOMAIN is required}"
: "${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL is required}"

TMP_CONF="/tmp/sec-scanner-nginx.conf"
OUT_CONF="/etc/nginx/sites-available/sec-scanner"

echo "[1/5] render nginx config"
envsubst '${ROOT_DOMAIN} ${API_DOMAIN}' < ./deploy/nginx/sec-scanner.conf.template > "$TMP_CONF"

echo "[2/5] install + enable site"
$SUDO cp "$TMP_CONF" "$OUT_CONF"
$SUDO ln -sf "$OUT_CONF" /etc/nginx/sites-enabled/sec-scanner
$SUDO rm -f /etc/nginx/sites-enabled/default || true
$SUDO nginx -t
$SUDO systemctl reload nginx

echo "[3/5] issue certificates (Let's Encrypt)"
DOMAINS=(-d "$API_DOMAIN")
# Include ROOT_DOMAIN only when it resolves to this VPS.
if [ -n "${ROOT_DOMAIN:-}" ]; then
  VPS_IPV4=$(hostname -I | awk '{print $1}')
  ROOT_IPV4=$(getent ahostsv4 "$ROOT_DOMAIN" 2>/dev/null | awk 'NR==1{print $1}')
  if [ -n "$ROOT_IPV4" ] && [ "$ROOT_IPV4" = "$VPS_IPV4" ]; then
    DOMAINS+=(-d "$ROOT_DOMAIN")
  else
    echo "[warn] ROOT_DOMAIN ($ROOT_DOMAIN) resolves to '$ROOT_IPV4' (expected '$VPS_IPV4'). Skipping root for now."
  fi
fi

$SUDO certbot --nginx \
  "${DOMAINS[@]}" \
  --non-interactive --agree-tos -m "$LETSENCRYPT_EMAIL" \
  --redirect

echo "[4/5] reload nginx"
$SUDO nginx -t
$SUDO systemctl reload nginx

echo "[5/5] done"
echo "API: https://$API_DOMAIN"
echo "Web-Check: https://$API_DOMAIN/web-check/"
