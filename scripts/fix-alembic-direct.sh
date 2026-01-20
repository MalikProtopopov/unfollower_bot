#!/bin/bash
# Directly fix alembic version in database when normal commands fail

set -e

echo "🔧 Directly fixing Alembic version in database..."

cd ~/projects/unfollower_bot

# Check for .env.prod
if [ ! -f ".env.prod" ]; then
    echo "Error: .env.prod file not found!"
    exit 1
fi

echo ""
echo "📊 Step 1: Current alembic version:"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "SELECT * FROM alembic_version;"

echo ""
echo "📋 Step 2: Available migrations in code:"
ls -la alembic/versions/*.py | grep -v __pycache__ | grep -v __init__

echo ""
echo "🔧 Step 3: Directly updating alembic_version to '006'..."
echo "   (006 is the last known good version before instagram_sessions)"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "DELETE FROM alembic_version; INSERT INTO alembic_version (version_num) VALUES ('006');"

echo ""
echo "✅ Step 4: Verifying new version:"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "SELECT * FROM alembic_version;"

echo ""
echo "🔄 Step 5: Running migrations to apply 007 and 008..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head

echo ""
echo "✅ Step 6: Final verification:"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "SELECT * FROM alembic_version;"

echo ""
echo "📋 Step 7: Check if instagram_sessions table exists:"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "\d instagram_sessions" || echo "Table not created yet"

echo ""
echo "🔄 Step 8: Rebuilding and restarting bot..."
docker compose -f docker-compose.prod.yml --env-file .env.prod build bot
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --force-recreate bot

echo ""
echo "✅ Done! Now test /admin_check_session in Telegram"

