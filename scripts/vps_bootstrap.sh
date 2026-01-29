#!/usr/bin/env bash
set -euo pipefail

# Ubuntu 24.04 bootstrap: docker + docker-compose + nginx + certbot

SUDO="sudo"
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
fi

echo "[1/6] apt update + base packages"
$SUDO apt-get update -y
$SUDO apt-get install -y ca-certificates curl gnupg lsb-release ufw nginx certbot python3-certbot-nginx gettext-base

echo "[2/6] install docker (official repo)"
if ! command -v docker >/dev/null 2>&1; then
  $SUDO install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null
  $SUDO apt-get update -y
  $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  $SUDO usermod -aG docker "$USER" || true
fi

echo "[3/6] ensure docker-compose command"
if ! command -v docker-compose >/dev/null 2>&1; then
  # For compatibility: create docker-compose shim if only plugin exists
  if docker compose version >/dev/null 2>&1; then
    $SUDO tee /usr/local/bin/docker-compose >/dev/null <<'EOF'
#!/usr/bin/env bash
exec docker compose "$@"
EOF
    $SUDO chmod +x /usr/local/bin/docker-compose
  fi
fi

echo "[4/6] firewall"
$SUDO ufw --force enable
$SUDO ufw allow OpenSSH
$SUDO ufw allow 'Nginx Full'

echo "[5/6] create app directory"
$SUDO mkdir -p /opt/sec-scanner
$SUDO chown -R "$USER:$USER" /opt/sec-scanner

echo "[6/6] done"
echo "Next: upload project to /opt/sec-scanner"

