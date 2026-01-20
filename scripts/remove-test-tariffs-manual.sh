#!/bin/bash
# Manually remove test/trial tariffs from database

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "🗑️  Removing test/trial tariffs from database..."
echo ""

# Get database name from env or use default
DB_NAME="${POSTGRES_DB:-mutual_followers}"
DB_USER="${POSTGRES_USER:-postgres}"

# Check current tariffs
echo "📊 Current test/trial tariffs:"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U "$DB_USER" "$DB_NAME" -c "
SELECT name, checks_count, price_stars 
FROM tariffs 
WHERE name IN ('Test', 'Test Pack', 'Trial', 'Тест: 1 проверка', 'Тест: 3 проверки', '1 проверка (тест)', '3 проверки (тест)');
" || exit 1

echo ""
read -p "Do you want to delete these tariffs? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "🗑️  Deleting test/trial tariffs..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U "$DB_USER" "$DB_NAME" -c "
DELETE FROM tariffs 
WHERE name IN ('Test', 'Test Pack', 'Trial', 'Тест: 1 проверка', 'Тест: 3 проверки', '1 проверка (тест)', '3 проверки (тест)');
" || exit 1

echo ""
echo -e "${GREEN}✅ Test/trial tariffs deleted!${NC}"
echo ""
echo "📊 Remaining active tariffs:"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U "$DB_USER" "$DB_NAME" -c "
SELECT name, checks_count, price_stars, is_active
FROM tariffs 
WHERE is_active = true 
ORDER BY sort_order, price_stars;
"

