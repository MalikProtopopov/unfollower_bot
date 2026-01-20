#!/bin/bash
# Check tariffs in database

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "📊 Checking tariffs in database..."
echo ""

# Get database name from env or use default
DB_NAME="${POSTGRES_DB:-mutual_followers}"
DB_USER="${POSTGRES_USER:-postgres}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Active Tariffs:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U "$DB_USER" "$DB_NAME" -c "
SELECT 
    name, 
    checks_count, 
    price_stars, 
    is_active,
    sort_order
FROM tariffs 
WHERE is_active = true 
ORDER BY sort_order, price_stars;
" || echo "Could not query tariffs"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Checking for test/trial tariffs (should be 0):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TEST_TARIFFS=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U "$DB_USER" "$DB_NAME" -t -c "
SELECT name, checks_count, price_stars 
FROM tariffs 
WHERE name IN ('Test', 'Test Pack', 'Trial', 'Тест: 1 проверка', 'Тест: 3 проверки', '1 проверка (тест)', '3 проверки (тест)');
" 2>/dev/null || echo "")

TEST_COUNT=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U "$DB_USER" "$DB_NAME" -t -c "
SELECT COUNT(*) 
FROM tariffs 
WHERE name IN ('Test', 'Test Pack', 'Trial', 'Тест: 1 проверка', 'Тест: 3 проверки', '1 проверка (тест)', '3 проверки (тест)');
" 2>/dev/null | tr -d ' ' || echo "0")

if [ "$TEST_COUNT" = "0" ] || [ -z "$TEST_COUNT" ]; then
    echo -e "${GREEN}✅ No test/trial tariffs found!${NC}"
else
    echo -e "${YELLOW}⚠️  Found $TEST_COUNT test/trial tariff(s):${NC}"
    echo "$TEST_TARIFFS"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TOTAL_COUNT=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U "$DB_USER" "$DB_NAME" -t -c "SELECT COUNT(*) FROM tariffs WHERE is_active = true;" 2>/dev/null | tr -d ' ' || echo "0")
echo "Total active tariffs: $TOTAL_COUNT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

