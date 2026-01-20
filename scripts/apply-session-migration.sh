#!/bin/bash
# Apply Instagram sessions migration after fixing alembic version

set -e

echo "🔧 Step 1: Fixing Alembic version issue..."
cd ~/projects/unfollower_bot

# Check for .env.prod
if [ ! -f ".env.prod" ]; then
    echo "Error: .env.prod file not found!"
    exit 1
fi

# Get current version
CURRENT_VERSION=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U postgres mutual_followers -t -c "SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d ' ' || echo "")

echo "Current version in DB: $CURRENT_VERSION"

# Check if version exists in code
if docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic history | grep -q "$CURRENT_VERSION"; then
    echo "✅ Version exists in code, upgrading..."
    docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head
else
    echo "⚠️  Version not found in code, stamping to head..."
    docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic stamp head
    echo "🔄 Now upgrading..."
    docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head
fi

echo ""
echo "✅ Step 2: Verifying migration..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic current

echo ""
echo "✅ Step 3: Checking if instagram_sessions table exists..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "\d instagram_sessions" || echo "⚠️  Table not found yet"

echo ""
echo "✅ Step 4: Restarting bot to load new code..."
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --force-recreate bot

echo ""
echo "✅ Done! Now try /admin_check_session in Telegram bot"

