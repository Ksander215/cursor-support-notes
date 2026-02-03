#!/usr/bin/env bash
set -euo pipefail

# Скрипт настройки автоматических бэкапов PostgreSQL на VPS
# Создаёт cron job для ежедневных бэкапов в 3:00 AM

APP_DIR="${APP_DIR:-/opt/sec-scanner}"
BACKUP_SCRIPT="$APP_DIR/scripts/vps_backup_db.sh"
CRON_LOG="/var/log/sec-scanner-backup.log"

echo "🔧 Настройка автоматических бэкапов PostgreSQL"
echo "================================================"

# Проверка что скрипт существует
if [[ ! -f "$BACKUP_SCRIPT" ]]; then
    echo "❌ Ошибка: скрипт $BACKUP_SCRIPT не найден"
    exit 1
fi

# Сделать скрипт исполняемым
chmod +x "$BACKUP_SCRIPT"

# Создать директорию для бэкапов
BACKUP_DIR="/var/backups/sec-scanner"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Создать директорию для логов
mkdir -p "$(dirname "$CRON_LOG")"

# Проверить существующий cron job
CRON_CMD="0 3 * * * $BACKUP_SCRIPT >> $CRON_LOG 2>&1"
CRON_EXISTS=$(crontab -l 2>/dev/null | grep -c "$BACKUP_SCRIPT" || echo "0")

if [[ "$CRON_EXISTS" -gt 0 ]]; then
    echo "⚠️  Cron job для бэкапов уже существует"
    echo ""
    echo "Текущие cron jobs для бэкапов:"
    crontab -l 2>/dev/null | grep "$BACKUP_SCRIPT" || true
    echo ""
    read -p "Заменить существующий cron job? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Отменено. Cron job не изменён."
        exit 0
    fi

    # Удалить старый cron job
    crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" | crontab - || true
fi

# Добавить новый cron job
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo "✅ Cron job добавлен:"
echo "   Время: каждый день в 3:00 AM"
echo "   Скрипт: $BACKUP_SCRIPT"
echo "   Логи: $CRON_LOG"
echo ""
echo "📋 Текущие cron jobs:"
crontab -l | grep -E "(backup|sec-scanner)" || echo "   (нет других связанных jobs)"
echo ""

# Тестовый запуск
echo "🧪 Тестовый запуск бэкапа..."
if "$BACKUP_SCRIPT"; then
    echo "✅ Тестовый бэкап успешен!"
    echo ""
    echo "📁 Бэкапы хранятся в: $BACKUP_DIR"
    echo "📊 Последний бэкап:"
    # shellcheck disable=SC2012
    ls -lh "$BACKUP_DIR"/postgres_*.dump 2>/dev/null | tail -1 || echo "   (бэкапов пока нет)"
else
    echo "❌ Ошибка при тестовом бэкапе. Проверьте логи: $CRON_LOG"
    exit 1
fi

echo ""
echo "✅ Настройка завершена!"
echo ""
echo "📝 Полезные команды:"
echo "   Просмотр логов: tail -f $CRON_LOG"
echo "   Ручной бэкап: $BACKUP_SCRIPT"
echo "   Список бэкапов: ls -lh $BACKUP_DIR"
echo "   Удалить cron job: crontab -e (удалить строку с $BACKUP_SCRIPT)"
