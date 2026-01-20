#!/bin/bash
# Fix alembic version issue when database has reference to non-existent revision

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "🔧 Fixing Alembic version issue..."
echo ""

# Get database name from env or use default
DB_NAME="${POSTGRES_DB:-mutual_followers}"
DB_USER="${POSTGRES_USER:-postgres}"

echo "📊 Current alembic version in database:"
CURRENT_VERSION=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U "$DB_USER" "$DB_NAME" -t -c "SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d ' ' || echo "")

if [ -z "$CURRENT_VERSION" ]; then
    echo -e "${YELLOW}⚠️  No alembic_version found in database${NC}"
else
    echo "   Current version: $CURRENT_VERSION"
fi

echo ""
echo "📋 Available migrations:"
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic history | head -20 || true

echo ""
echo "🔍 Checking if current version exists in code..."
if docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic history | grep -q "$CURRENT_VERSION"; then
    echo -e "${GREEN}✅ Current version exists in code${NC}"
    echo "   Trying to upgrade to head..."
    docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head
else
    echo -e "${YELLOW}⚠️  Current version $CURRENT_VERSION not found in code${NC}"
    echo ""
    echo "💡 Options:"
    echo "   1. Set version to latest available migration"
    echo "   2. Stamp database to latest migration"
    echo ""
    read -p "Do you want to stamp database to head? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "📌 Stamping database to head..."
        docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic stamp head
        echo ""
        echo "🔄 Now trying to upgrade..."
        docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head || {
            echo -e "${YELLOW}⚠️  Upgrade failed, but database is stamped${NC}"
        }
    else
        echo "Skipping stamp. You may need to manually fix alembic_version table."
    fi
fi

echo ""
echo "✅ Done!"

