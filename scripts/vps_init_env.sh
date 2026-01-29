#!/usr/bin/env bash
set -euo pipefail

# Initialize /opt/sec-scanner/.env.production safely (no secrets printed).
# - Copies from .env.production.example if missing
# - Ensures required domain/email keys are set
# - Generates strong POSTGRES_PASSWORD if placeholder is present
# - Generates SEC_SCANNER_API_KEY_PEPPER if placeholder is present (safe even if SaaS disabled)
#
# Run on VPS:
#   cd /opt/sec-scanner && ./scripts/vps_init_env.sh

cd /opt/sec-scanner

if [ ! -f .env.production ]; then
  cp .env.production.example .env.production
fi
chmod 600 .env.production

gen_hex() {
  local n="${1:-32}"
  python3 -c "import secrets; print(secrets.token_hex(${n}))"
}

set_kv() {
  local key="$1"
  local val="$2"
  if grep -qE "^${key}=" .env.production; then
    sed -i "s|^${key}=.*$|${key}=${val}|" .env.production
  else
    printf "%s=%s\n" "$key" "$val" >> .env.production
  fi
}

get_kv() {
  local key="$1"
  grep -E "^${key}=" .env.production | head -n 1 | cut -d= -f2- || true
}

ensure_nonempty() {
  local key="$1"
  local def="$2"
  local cur
  cur="$(get_kv "$key")"
  if [ -z "${cur}" ]; then
    set_kv "$key" "$def"
  fi
}

ensure_secret_not_placeholder() {
  local key="$1"
  local placeholder="$2"
  local gen_n="$3"
  local cur
  cur="$(get_kv "$key")"
  if [ -z "${cur}" ] || [ "${cur}" = "${placeholder}" ]; then
    set_kv "$key" "$(gen_hex "$gen_n")"
  fi
}

# Required keys for Nginx + certbot scripts
ensure_nonempty "ROOT_DOMAIN" "sec-scanner.pro"
ensure_nonempty "API_DOMAIN" "api.sec-scanner.pro"
ensure_nonempty "LETSENCRYPT_EMAIL" "admin@sec-scanner.pro"

# Secrets (generated, not printed)
ensure_secret_not_placeholder "POSTGRES_PASSWORD" "CHANGE_ME_STRONG" 24
ensure_secret_not_placeholder "SEC_SCANNER_API_KEY_PEPPER" "CHANGE_ME_RANDOM" 32

# Safe defaults (do not enable auth automatically)
ensure_nonempty "SEC_SCANNER_ALLOW_PRIVATE_TARGETS" "false"
ensure_nonempty "SEC_SCANNER_REQUIRE_API_KEY" "false"
ensure_nonempty "SEC_SCANNER_API_KEY" ""

echo "[ok] .env.production initialized (values not printed)."
echo "Keys present:"
grep -E '^(POSTGRES_PASSWORD|ROOT_DOMAIN|API_DOMAIN|LETSENCRYPT_EMAIL|SEC_SCANNER_API_KEY|SEC_SCANNER_ALLOW_PRIVATE_TARGETS|SEC_SCANNER_REQUIRE_API_KEY|SEC_SCANNER_API_KEY_PEPPER)=' .env.production \
  | sed -E 's/^(POSTGRES_PASSWORD|SEC_SCANNER_API_KEY|SEC_SCANNER_API_KEY_PEPPER)=.*/\1=*** (hidden)/'

