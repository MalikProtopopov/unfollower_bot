#!/bin/bash
# Fix alembic version issue and apply migration 007

set -e

echo "🔧 Fixing Alembic version and applying migration 007..."
echo ""

cd ~/projects/unfollower_bot

# Check for .env.prod
if [ ! -f ".env.prod" ]; then
    echo "Error: .env.prod file not found!"
    exit 1
fi

echo "📊 Step 1: Checking current version in database..."
CURRENT_VERSION=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U postgres mutual_followers -t -c "SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d ' ' || echo "")

echo "   Current version in DB: $CURRENT_VERSION"

echo ""
echo "📋 Step 2: Available migrations in code:"
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic history | grep -E "^[0-9a-f]+" | head -10

echo ""
echo "🔧 Step 3: Setting version to f73d7ff2c911 (last known migration before 007)..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "UPDATE alembic_version SET version_num = 'f73d7ff2c911';"

echo ""
echo "✅ Step 4: Verifying version update..."
NEW_VERSION=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U postgres mutual_followers -t -c "SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d ' ')
echo "   New version in DB: $NEW_VERSION"

echo ""
echo "🔄 Step 5: Applying migration 007..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head

echo ""
echo "✅ Step 6: Verifying final state..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic current

echo ""
echo "✅ Step 7: Checking if instagram_sessions table exists..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "\d instagram_sessions" || echo "⚠️  Table not found"

echo ""
echo "✅ Done! Migration 007 should be applied now."

