#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/opt/sec-scanner}"
ENV_FILE="${ENV_FILE:-$ROOT/.env.production}"
KEY_FILE="${KEY_FILE:-/root/sec_scanner_api_key.txt}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[error] env file not found: $ENV_FILE" >&2
  exit 1
fi

export ENV_FILE KEY_FILE
python3 - <<'PY'
import os
import secrets

env_file = os.environ["ENV_FILE"]
key_file = os.environ["KEY_FILE"]

with open(env_file, "r", encoding="utf-8") as f:
    lines = f.read().splitlines()

out: list[str] = []
for ln in lines:
    s = ln.strip()
    if s == "SEC_SCANNER_API_KEY" or s.startswith("SEC_SCANNER_API_KEY="):
        continue
    out.append(ln)

key = "sk_" + secrets.token_urlsafe(32)
out.append(f"SEC_SCANNER_API_KEY={key}")

with open(env_file, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join([l for l in out if l.strip()]) + "\n")
os.chmod(env_file, 0o600)

with open(key_file, "w", encoding="utf-8", newline="\n") as f:
    f.write(key + "\n")
os.chmod(key_file, 0o600)

print("API_KEY_ROTATED last4=" + key[-4:])
PY

docker-compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.prod.yml" up -d --build api worker

echo "ROOT_STATUS=$(curl -s -o /dev/null -w \"%{http_code}\" https://api.sec-scanner.pro/)"
echo "AUDITS_NO_KEY_STATUS=$(curl -s -o /dev/null -w \"%{http_code}\" https://api.sec-scanner.pro/api/v1/audits)"

echo "[ok] Key stored at: $KEY_FILE (do not paste it into chat)"
