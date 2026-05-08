#!/usr/bin/env bash
# Fix .env.production on VPS: remove wrong DATABASE_URL, set REQUIRE_API_KEY=true, add UI_API_BASE_URL if missing.
# Run on VPS: bash fix_env_production_on_vps.sh (from /opt/sec-scanner) or:
#   ssh root@${VPS_HOST:?} "cd /opt/sec-scanner && bash -s" < scripts/fix_env_production_on_vps.sh

set -e
ENV_FILE="${1:-.env.production}"
if [ ! -f "$ENV_FILE" ]; then
  echo "File not found: $ENV_FILE"
  exit 1
fi

# Backup
cp -a "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)"
echo "Backup created: ${ENV_FILE}.bak.*"

# 1) Remove SEC_SCANNER_DATABASE_URL line (compose provides correct URL)
sed -i '/^SEC_SCANNER_DATABASE_URL=/d' "$ENV_FILE"
echo "Removed SEC_SCANNER_DATABASE_URL line."

# 2) SEC_SCANNER_REQUIRE_API_KEY=false -> true
sed -i 's/^SEC_SCANNER_REQUIRE_API_KEY=false$/SEC_SCANNER_REQUIRE_API_KEY=true/' "$ENV_FILE"
echo "Set SEC_SCANNER_REQUIRE_API_KEY=true."

# 3) Add UI_API_BASE_URL if missing
if ! grep -q '^UI_API_BASE_URL=' "$ENV_FILE"; then
  # Insert after API_DOMAIN= if present, else at line 2
  if grep -q '^API_DOMAIN=' "$ENV_FILE"; then
    sed -i '/^API_DOMAIN=/a UI_API_BASE_URL=https://api.sec-scanner.pro' "$ENV_FILE"
  else
    sed -i '2i UI_API_BASE_URL=https://api.sec-scanner.pro' "$ENV_FILE"
  fi
  echo "Added UI_API_BASE_URL=https://api.sec-scanner.pro"
else
  echo "UI_API_BASE_URL already present."
fi

echo "Done. Restart API/worker to apply: docker compose -f docker-compose.prod.yml restart api worker"
