#!/bin/bash
# Basic monitoring script for VPS
# Checks: Docker containers, disk usage, SSL expiry
# Usage: ./vps_monitor.sh [--alert-email EMAIL]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="/opt/sec-scanner"
ALERT_EMAIL="${1:-}"
ALERT_THRESHOLD_DISK_PERCENT=85
ALERT_THRESHOLD_SSL_DAYS=30

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

send_alert() {
    local subject="$1"
    local body="$2"

    if [ -n "$ALERT_EMAIL" ]; then
        echo "$body" | mail -s "$subject" "$ALERT_EMAIL" 2>/dev/null || {
            warn "Failed to send email alert to $ALERT_EMAIL"
        }
    else
        warn "Alert: $subject"
        echo "$body"
    fi
}

# Check Docker containers
check_containers() {
    log "Checking Docker containers..."

    cd "$PROJECT_DIR" || exit 1

    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
        return 1
    fi

    if ! docker ps &> /dev/null; then
        error "Cannot access Docker daemon"
        return 1
    fi

    local failed_containers=()
    local stopped_containers=()

    # Check containers defined in docker-compose.prod.yml
    # Try both naming conventions: sec-scanner-{service}-1 and sec-scanner_{service}_1
    local expected_containers=("api" "worker" "db" "redis" "web-check" "frontend")

    for container in "${expected_containers[@]}"; do
        # Try with dashes first (newer docker-compose format)
        local container_name_dash="sec-scanner-${container}-1"
        # Try with underscores (older docker-compose format)
        local container_name_underscore="sec-scanner_${container}_1"

        # Check which naming convention is used
        local status_dash=$(docker inspect --format='{{.State.Status}}' "$container_name_dash" 2>/dev/null || echo "not_found")
        local status_underscore=$(docker inspect --format='{{.State.Status}}' "$container_name_underscore" 2>/dev/null || echo "not_found")

        local container_name=""
        local status="not_found"

        if [ "$status_dash" != "not_found" ]; then
            container_name="$container_name_dash"
            status="$status_dash"
        elif [ "$status_underscore" != "not_found" ]; then
            container_name="$container_name_underscore"
            status="$status_underscore"
        else
            container_name="$container_name_dash"  # Default to dash format for error message
            status="not_found"
        fi

        if [ "$status" = "not_found" ]; then
            warn "Container $container_name not found"
            stopped_containers+=("$container_name")
        elif [ "$status" != "running" ]; then
            error "Container $container_name is not running (status: $status)"
            failed_containers+=("$container_name")
        else
            # Check health status if healthcheck is configured
            local health=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "none")
            if [ "$health" = "unhealthy" ]; then
                error "Container $container_name is unhealthy"
                failed_containers+=("$container_name")
            fi
        fi
    done

    if [ ${#failed_containers[@]} -gt 0 ] || [ ${#stopped_containers[@]} -gt 0 ]; then
        local alert_body="Docker containers status check failed:\n\n"
        if [ ${#failed_containers[@]} -gt 0 ]; then
            alert_body+="Failed containers:\n"
            for c in "${failed_containers[@]}"; do
                alert_body+="  - $c\n"
            done
        fi
        if [ ${#stopped_containers[@]} -gt 0 ]; then
            alert_body+="Stopped containers:\n"
            for c in "${stopped_containers[@]}"; do
                alert_body+="  - $c\n"
            done
        fi
        alert_body+="\nRun 'docker ps -a' for details."

        send_alert "VPS Alert: Docker containers issue" "$alert_body"
        return 1
    else
        info "All containers are running"
        return 0
    fi
}

# Check disk usage
check_disk() {
    log "Checking disk usage..."

    local disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')

    if [ -z "$disk_usage" ]; then
        error "Failed to get disk usage"
        return 1
    fi

    if [ "$disk_usage" -ge "$ALERT_THRESHOLD_DISK_PERCENT" ]; then
        local available=$(df -h / | awk 'NR==2 {print $4}')
        local used=$(df -h / | awk 'NR==2 {print $3}')
        local total=$(df -h / | awk 'NR==2 {print $2}')

        local alert_body="Disk usage is ${disk_usage}% (threshold: ${ALERT_THRESHOLD_DISK_PERCENT}%)\n\n"
        alert_body+="Details:\n"
        alert_body+="  Used: $used\n"
        alert_body+="  Available: $available\n"
        alert_body+="  Total: $total\n\n"
        alert_body+="Please clean up disk space or expand the volume."

        send_alert "VPS Alert: High disk usage (${disk_usage}%)" "$alert_body"
        return 1
    else
        info "Disk usage: ${disk_usage}% (OK)"
        return 0
    fi
}

# Check SSL certificate expiry
check_ssl() {
    log "Checking SSL certificate expiry..."

    local domains=("sec-scanner.pro" "api.sec-scanner.pro")
    local issues=()

    for domain in "${domains[@]}"; do
        local expiry_date=$(echo | openssl s_client -servername "$domain" -connect "$domain:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)

        if [ -z "$expiry_date" ]; then
            warn "Could not check SSL certificate for $domain"
            continue
        fi

        # Convert expiry date to epoch
        local expiry_epoch=$(date -d "$expiry_date" +%s 2>/dev/null || date -j -f "%b %d %H:%M:%S %Y %Z" "$expiry_date" +%s 2>/dev/null)
        local current_epoch=$(date +%s)
        local days_until_expiry=$(( (expiry_epoch - current_epoch) / 86400 ))

        if [ "$days_until_expiry" -lt "$ALERT_THRESHOLD_SSL_DAYS" ]; then
            local expiry_formatted=$(date -d "@$expiry_epoch" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "$expiry_date")
            issues+=("$domain: expires in $days_until_expiry days ($expiry_formatted)")
        else
            info "SSL for $domain: OK (expires in $days_until_expiry days)"
        fi
    done

    if [ ${#issues[@]} -gt 0 ]; then
        local alert_body="SSL certificates expiring soon:\n\n"
        for issue in "${issues[@]}"; do
            alert_body+="  - $issue\n"
        done
        alert_body+="\nPlease renew certificates using certbot."

        send_alert "VPS Alert: SSL certificates expiring soon" "$alert_body"
        return 1
    else
        info "All SSL certificates are valid"
        return 0
    fi
}

# Main
main() {
    log "Starting VPS monitoring check..."

    local exit_code=0

    check_containers || exit_code=1
    check_disk || exit_code=1
    check_ssl || exit_code=1

    if [ $exit_code -eq 0 ]; then
        info "All checks passed"
    else
        error "Some checks failed"
    fi

    return $exit_code
}

# Parse arguments
if [ "${1:-}" = "--alert-email" ] && [ -n "${2:-}" ]; then
    ALERT_EMAIL="$2"
    shift 2
fi

main "$@"
