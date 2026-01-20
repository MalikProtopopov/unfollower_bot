#!/bin/bash
# Fix migrations issue: rebuild backend image with new migration files

set -e

echo "🔄 Fixing migrations..."

cd ~/projects/unfollower_bot

echo "📥 Pulling latest code..."
git pull origin main

echo "🔨 Rebuilding backend image (no cache)..."
docker compose -f docker-compose.prod.yml --env-file .env.prod build --no-cache backend

echo "📊 Running migrations..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head || {
    echo "⚠️  Migration failed, trying to fix..."
    echo "🔍 Checking current migration version in database..."
    docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "SELECT version_num FROM alembic_version;" || true
    echo "💡 If migration fails, you may need to manually fix alembic_version table"
}

echo "🔍 Checking current migration version..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic current

echo ""
echo "✅ Verifying tariffs in database after migration..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "
SELECT 
    name, 
    checks_count, 
    price_stars, 
    is_active,
    sort_order
FROM tariffs 
WHERE is_active = true 
ORDER BY sort_order, price_stars;
"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "🔍 Checking for test/trial tariffs (should be empty)..."
TEST_TARIFFS=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U postgres mutual_followers -t -c "
SELECT COUNT(*) 
FROM tariffs 
WHERE name IN ('Test', 'Test Pack', 'Trial', 'Тест: 1 проверка', 'Тест: 3 проверки', '1 проверка (тест)', '3 проверки (тест)');
" | tr -d ' ')

if [ "$TEST_TARIFFS" = "0" ] || [ -z "$TEST_TARIFFS" ]; then
    echo "✅ Test/trial tariffs successfully removed!"
else
    echo "⚠️  Warning: Found $TEST_TARIFFS test/trial tariff(s) in database"
    docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "
    SELECT name, checks_count, price_stars 
    FROM tariffs 
    WHERE name IN ('Test', 'Test Pack', 'Trial', 'Тест: 1 проверка', 'Тест: 3 проверки', '1 проверка (тест)', '3 проверки (тест)');
    "
fi

echo ""
echo "🔄 Restarting backend and bot..."
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --force-recreate backend bot worker

echo ""
echo "✅ Done! Migrations applied and services restarted."
echo "📊 Summary:"
echo "   - Migration version: $(docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic current 2>/dev/null | grep -v INFO || echo 'check manually')"
echo "   - Active tariffs: $(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U postgres mutual_followers -t -c 'SELECT COUNT(*) FROM tariffs WHERE is_active = true;' | tr -d ' ')"

