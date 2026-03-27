#!/bin/bash
# Setup Supabase connection for sec-scanner.pro
# Usage: ./scripts/setup_supabase.sh <PROJECT_REF> <DB_PASSWORD> <SERVICE_ROLE_KEY>

set -e

PROJECT_REF="${1:-}"
DB_PASSWORD="${2:-}"
SERVICE_ROLE_KEY="${3:-}"

if [ -z "$PROJECT_REF" ] || [ -z "$DB_PASSWORD" ]; then
    echo "Usage: $0 <PROJECT_REF> <DB_PASSWORD> [SERVICE_ROLE_KEY]"
    echo ""
    echo "Example:"
    echo "  $0 abcdefghijklmnop your-secure-password eyJ..."
    exit 1
fi

# Region (default: EU Central)
REGION="${REGION:-eu-central-1}"

# Connection strings
DB_URL="postgresql+psycopg://postgres.${PROJECT_REF}:${DB_PASSWORD}@aws-0-${REGION}.pooler.supabase.com:6543/postgres"
SUPABASE_URL="https://${PROJECT_REF}.supabase.co"

echo "=== Supabase Setup ==="
echo "Project Ref: $PROJECT_REF"
echo "Region: $REGION"
echo "Database URL: ${DB_URL%%:*}:***@***"
echo ""

# Check if .env exists
ENV_FILE="${ENV_FILE:-/opt/sec-scanner/.env}"
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found"
    exit 1
fi

# Backup original .env
cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"

# Update or add variables
update_env() {
    local key="$1"
    local value="$2"
    local file="$3"
    
    if grep -q "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

# Update environment variables
update_env "SEC_SCANNER_DATABASE_URL" "$DB_URL" "$ENV_FILE"
update_env "SUPABASE_URL" "$SUPABASE_URL" "$ENV_FILE"

if [ -n "$SERVICE_ROLE_KEY" ]; then
    update_env "SUPABASE_SERVICE_ROLE_KEY" "$SERVICE_ROLE_KEY" "$ENV_FILE"
fi

echo "Updated $ENV_FILE"
echo ""

# Test connection
echo "Testing database connection..."
if command -v alembic &> /dev/null; then
    export SEC_SCANNER_DATABASE_URL="$DB_URL"
    
    echo "Current Alembic revision:"
    alembic current || echo "  (none - fresh database)"
    
    echo ""
    echo "To apply migrations, run:"
    echo "  export SEC_SCANNER_DATABASE_URL=\"$DB_URL\""
    echo "  alembic upgrade head"
fi

echo ""
echo "=== Next Steps ==="
echo "1. Apply migrations: alembic upgrade head"
echo "2. Restart services: docker compose down && docker compose up -d"
echo "3. Initialize plans: python -m scripts.init_default_plans"
echo ""
echo "Done!"