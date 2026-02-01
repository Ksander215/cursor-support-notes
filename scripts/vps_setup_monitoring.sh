#!/bin/bash
# Setup monitoring cron job on VPS
# Usage: ./vps_setup_monitoring.sh [--email EMAIL]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="/opt/sec-scanner"
MONITOR_SCRIPT="$SCRIPT_DIR/vps_monitor.sh"
CRON_SCHEDULE="0 */6 * * *"  # Every 6 hours
ALERT_EMAIL="${1:-}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    echo "[ERROR] $*" >&2
    exit 1
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root (use sudo)"
fi

# Make monitor script executable
if [ ! -f "$MONITOR_SCRIPT" ]; then
    error "Monitor script not found: $MONITOR_SCRIPT"
fi

chmod +x "$MONITOR_SCRIPT"

# Install mailutils if email alerts are requested
if [ -n "$ALERT_EMAIL" ]; then
    log "Installing mailutils for email alerts..."
    if ! command -v mail &> /dev/null; then
        apt-get update -qq
        apt-get install -y -qq mailutils postfix || {
            warn "Failed to install mailutils. Email alerts will not work."
            warn "You can install manually: apt-get install mailutils postfix"
        }
    fi

    log "Email alerts will be sent to: $ALERT_EMAIL"
else
    log "No email configured. Alerts will be logged only."
fi

# Create cron job
log "Setting up cron job..."

# Remove existing cron job if exists
crontab -l 2>/dev/null | grep -v "$MONITOR_SCRIPT" | crontab - || true

# Add new cron job
if [ -n "$ALERT_EMAIL" ]; then
    CRON_CMD="$CRON_SCHEDULE $MONITOR_SCRIPT --alert-email $ALERT_EMAIL >> /var/log/vps-monitor.log 2>&1"
else
    CRON_CMD="$CRON_SCHEDULE $MONITOR_SCRIPT >> /var/log/vps-monitor.log 2>&1"
fi

(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

log "Cron job installed successfully"
log "Schedule: $CRON_SCHEDULE"
log "Log file: /var/log/vps-monitor.log"

# Test run
log "Running test check..."
if [ -n "$ALERT_EMAIL" ]; then
    "$MONITOR_SCRIPT" --alert-email "$ALERT_EMAIL"
else
    "$MONITOR_SCRIPT"
fi

log "Monitoring setup complete!"
log ""
log "To view logs: tail -f /var/log/vps-monitor.log"
log "To edit schedule: crontab -e"
log "To remove monitoring: crontab -l | grep -v '$MONITOR_SCRIPT' | crontab -"
