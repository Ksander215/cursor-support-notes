#!/usr/bin/env bash
set -euo pipefail

# Настройка fail2ban для защиты от brute-force атак
# Использование:
#   sudo ./scripts/vps_setup_fail2ban.sh

SUDO="sudo"
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
fi

echo "🔒 Настройка fail2ban для защиты от brute-force"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Проверка что скрипт запущен от root или с sudo
if [ "$(id -u)" -ne 0 ]; then
  echo "⚠️  Этот скрипт требует прав root. Используйте sudo."
  exit 1
fi

echo "[1/5] Установка fail2ban"
if ! command -v fail2ban-server >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y fail2ban
else
  echo "✅ fail2ban уже установлен"
fi

echo "[2/5] Создание конфигурации jail.local"
cat > /etc/fail2ban/jail.local <<'EOF'
# Fail2ban configuration for sec-scanner.pro
# This file overrides settings in jail.conf

[DEFAULT]
# Ban hosts for 1 hour (3600 seconds)
bantime = 3600
# Find hosts within 10 minutes (600 seconds)
findtime = 600
# Ban after 5 failed attempts
maxretry = 5
# Ignore localhost
ignoreip = 127.0.0.1/8 ::1
# Email notifications (optional, uncomment and configure if needed)
# destemail = admin@sec-scanner.pro
# sendername = Fail2Ban
# action = %(action_mwl)s

[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
backend = %(sshd_backend)s
maxretry = 5
findtime = 600
bantime = 3600

[nginx-http-auth]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 5
findtime = 600
bantime = 3600

[nginx-limit-req]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 10
findtime = 60
bantime = 300
# Filter for 429 Too Many Requests
failregex = ^.*limiting requests.*client: <HOST>.*$

[nginx-botsearch]
enabled = true
port = http,https
logpath = /var/log/nginx/access.log
maxretry = 10
findtime = 300
bantime = 1800
# Filter for repeated 404 errors (common bot behavior)
failregex = ^<HOST>.*" 404 .*$
EOF

echo "[3/5] Создание фильтра для nginx-http-auth"
cat > /etc/fail2ban/filter.d/nginx-http-auth.local <<'EOF'
# Fail2ban filter for Nginx HTTP authentication failures
# Matches 401 Unauthorized errors

[Definition]
failregex = ^.*\[error\].*client: <HOST>.*,.*401.*$
            ^.*\[error\].*client <HOST>.*,.*401.*$
ignoreregex =
EOF

echo "[4/5] Создание фильтра для nginx-limit-req"
cat > /etc/fail2ban/filter.d/nginx-limit-req.local <<'EOF'
# Fail2ban filter for Nginx rate limiting (429 errors)

[Definition]
failregex = ^.*limiting requests.*client: <HOST>.*$
            ^.*limiting requests.*client <HOST>.*$
ignoreregex =
EOF

echo "[5/5] Запуск и включение fail2ban"
systemctl enable fail2ban
systemctl restart fail2ban

# Проверка статуса
sleep 2
if systemctl is-active --quiet fail2ban; then
  echo "✅ fail2ban запущен и работает"
else
  echo "⚠️  fail2ban не запустился. Проверьте логи: journalctl -u fail2ban"
  exit 1
fi

echo ""
echo "✅ Настройка fail2ban завершена!"
echo ""
echo "📊 Полезные команды:"
echo "   # Проверить статус"
echo "   sudo fail2ban-client status"
echo ""
echo "   # Проверить конкретный jail"
echo "   sudo fail2ban-client status sshd"
echo "   sudo fail2ban-client status nginx-http-auth"
echo ""
echo "   # Разблокировать IP (если заблокирован по ошибке)"
echo "   sudo fail2ban-client set sshd unbanip <IP_ADDRESS>"
echo ""
echo "   # Просмотр логов"
echo "   sudo tail -f /var/log/fail2ban.log"
echo ""
echo "⚠️  ВАЖНО: Убедитесь что у вас есть доступ к VPS через SSH ключ"
echo "   перед закрытием текущей SSH сессии!"
