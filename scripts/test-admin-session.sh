#!/bin/bash
# Test script to verify admin session management is working

set -e

echo "🔍 Testing Admin Session Management"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd ~/projects/unfollower_bot

# Check for .env.prod
if [ ! -f ".env.prod" ]; then
    echo "Error: .env.prod file not found!"
    exit 1
fi

echo "1️⃣  Checking admin_bot container status..."
docker compose -f docker-compose.prod.yml --env-file .env.prod ps admin_bot

echo ""
echo "2️⃣  Checking admin_bot logs (last 20 lines)..."
docker compose -f docker-compose.prod.yml --env-file .env.prod logs admin_bot --tail=20

echo ""
echo "3️⃣  Checking if instagram_sessions table exists..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "\d instagram_sessions" || echo "⚠️  Table not found!"

echo ""
echo "4️⃣  Checking sessions in database..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "
SELECT 
    id, 
    LEFT(session_id, 20) || '...' as session_preview,
    is_active,
    is_valid,
    created_at,
    last_used_at
FROM instagram_sessions 
ORDER BY created_at DESC 
LIMIT 5;
"

echo ""
echo "5️⃣  Checking alembic version..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "SELECT * FROM alembic_version;"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Test completed!"
echo ""
echo "📝 Next steps:"
echo "   1. Send /admin_set_session YOUR_TOKEN in admin bot"
echo "   2. Send /admin_check_session to verify"
echo "   3. Run this script again to see if session was saved"

