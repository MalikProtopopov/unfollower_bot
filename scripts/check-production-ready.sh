#!/bin/bash
# Comprehensive production readiness check for the bot

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS="${GREEN}✅${NC}"
FAIL="${RED}❌${NC}"
WARN="${YELLOW}⚠️${NC}"
INFO="${BLUE}ℹ️${NC}"

ERRORS=0
WARNINGS=0

echo "🔍 Production Readiness Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Get database name from env or use default
DB_NAME="${POSTGRES_DB:-mutual_followers}"
DB_USER="${POSTGRES_USER:-postgres}"

# 1. Check Docker containers
echo "1️⃣  Checking Docker containers..."
if docker compose -f docker-compose.prod.yml --env-file .env.prod ps | grep -q "Up"; then
    echo -e "   ${PASS} Containers are running"
    
    # Check specific containers
    BACKEND_UP=$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps | grep "backend_prod" | grep -c "Up" || echo "0")
    BOT_UP=$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps | grep "bot_prod" | grep -c "Up" || echo "0")
    WORKER_UP=$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps | grep "worker_prod" | grep -c "Up" || echo "0")
    POSTGRES_UP=$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps | grep "postgres_prod" | grep -c "Up" || echo "0")
    
    if [ "$BACKEND_UP" = "1" ]; then
        echo -e "   ${PASS} Backend container is running"
    else
        echo -e "   ${FAIL} Backend container is NOT running"
        ((ERRORS++))
    fi
    
    if [ "$BOT_UP" = "1" ]; then
        echo -e "   ${PASS} Bot container is running"
    else
        echo -e "   ${FAIL} Bot container is NOT running"
        ((ERRORS++))
    fi
    
    if [ "$WORKER_UP" = "1" ]; then
        echo -e "   ${PASS} Worker container is running"
    else
        echo -e "   ${FAIL} Worker container is NOT running"
        ((ERRORS++))
    fi
    
    if [ "$POSTGRES_UP" = "1" ]; then
        echo -e "   ${PASS} PostgreSQL container is running"
    else
        echo -e "   ${FAIL} PostgreSQL container is NOT running"
        ((ERRORS++))
    fi
else
    echo -e "   ${FAIL} Containers are NOT running"
    ((ERRORS++))
fi
echo ""

# 2. Check database migrations
echo "2️⃣  Checking database migrations..."
CURRENT_VERSION=$(docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic current 2>/dev/null | grep -oP '^\s*\K[0-9a-f]+' | head -1 || echo "")
HEAD_VERSION=$(docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic heads 2>/dev/null | grep -oP '^\s*\K[0-9a-f]+' | head -1 || echo "")

if [ -n "$CURRENT_VERSION" ] && [ -n "$HEAD_VERSION" ]; then
    if [ "$CURRENT_VERSION" = "$HEAD_VERSION" ]; then
        echo -e "   ${PASS} Migrations are up to date (version: $CURRENT_VERSION)"
    else
        echo -e "   ${FAIL} Migrations are NOT up to date (current: $CURRENT_VERSION, head: $HEAD_VERSION)"
        ((ERRORS++))
    fi
else
    echo -e "   ${WARN} Could not determine migration status"
    ((WARNINGS++))
fi
echo ""

# 3. Check tariffs
echo "3️⃣  Checking tariffs..."
TARIFF_COUNT=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U "$DB_USER" "$DB_NAME" -t -c "SELECT COUNT(*) FROM tariffs WHERE is_active = true;" 2>/dev/null | tr -d ' ' || echo "0")

if [ "$TARIFF_COUNT" -gt "0" ]; then
    echo -e "   ${PASS} Found $TARIFF_COUNT active tariff(s)"
    
    # Check for test tariffs
    TEST_COUNT=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U "$DB_USER" "$DB_NAME" -t -c "
    SELECT COUNT(*) 
    FROM tariffs 
    WHERE name IN ('Test', 'Test Pack', 'Trial', 'Тест: 1 проверка', 'Тест: 3 проверки', '1 проверка (тест)', '3 проверки (тест)');
    " 2>/dev/null | tr -d ' ' || echo "0")
    
    if [ "$TEST_COUNT" = "0" ]; then
        echo -e "   ${PASS} No test/trial tariffs found"
    else
        echo -e "   ${FAIL} Found $TEST_COUNT test/trial tariff(s) - should be removed!"
        ((ERRORS++))
    fi
    
    # Show active tariffs
    echo "   ${INFO} Active tariffs:"
    docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U "$DB_USER" "$DB_NAME" -c "
    SELECT name, checks_count, price_stars 
    FROM tariffs 
    WHERE is_active = true 
    ORDER BY sort_order, price_stars;
    " 2>/dev/null | tail -n +3 | head -n -1 | sed 's/^/      /' || true
else
    echo -e "   ${FAIL} No active tariffs found!"
    ((ERRORS++))
fi
echo ""

# 4. Check environment variables
echo "4️⃣  Checking critical environment variables..."
if [ -f ".env.prod" ]; then
    echo -e "   ${PASS} .env.prod file exists"
    
    # Check critical vars
    if grep -q "TELEGRAM_TOKEN=" .env.prod && ! grep -q "TELEGRAM_TOKEN=$" .env.prod; then
        echo -e "   ${PASS} TELEGRAM_TOKEN is set"
    else
        echo -e "   ${FAIL} TELEGRAM_TOKEN is NOT set or empty"
        ((ERRORS++))
    fi
    
    if grep -q "INSTAGRAM_SESSION_ID=" .env.prod && ! grep -q "INSTAGRAM_SESSION_ID=$" .env.prod; then
        echo -e "   ${PASS} INSTAGRAM_SESSION_ID is set"
    else
        echo -e "   ${WARN} INSTAGRAM_SESSION_ID is NOT set - Instagram scraping may not work"
        ((WARNINGS++))
    fi
    
    if grep -q "DATABASE_URL=" .env.prod; then
        echo -e "   ${PASS} DATABASE_URL is set"
    else
        echo -e "   ${FAIL} DATABASE_URL is NOT set"
        ((ERRORS++))
    fi
else
    echo -e "   ${FAIL} .env.prod file NOT found"
    ((ERRORS++))
fi
echo ""

# 5. Check API health
echo "5️⃣  Checking API health..."
if docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "   ${PASS} API health check passed"
else
    echo -e "   ${FAIL} API health check failed"
    ((ERRORS++))
fi
echo ""

# 6. Check recent bot logs
echo "6️⃣  Checking bot logs (last 5 lines)..."
BOT_LOGS=$(docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail=5 bot 2>/dev/null || echo "")
if echo "$BOT_LOGS" | grep -q "Starting Mutual Followers Bot"; then
    echo -e "   ${PASS} Bot appears to be running"
    echo "$BOT_LOGS" | tail -3 | sed 's/^/      /'
else
    echo -e "   ${WARN} Could not verify bot status from logs"
    ((WARNINGS++))
fi
echo ""

# 7. Check worker logs
echo "7️⃣  Checking worker logs (last 5 lines)..."
WORKER_LOGS=$(docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail=5 worker 2>/dev/null || echo "")
if echo "$WORKER_LOGS" | grep -q "Queue worker started"; then
    echo -e "   ${PASS} Worker appears to be running"
    echo "$WORKER_LOGS" | tail -3 | sed 's/^/      /'
else
    echo -e "   ${WARN} Could not verify worker status from logs"
    ((WARNINGS++))
fi
echo ""

# 8. Check database connectivity
echo "8️⃣  Checking database connectivity..."
if docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U "$DB_USER" "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
    echo -e "   ${PASS} Database is accessible"
    
    # Check if tables exist
    TABLE_COUNT=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U "$DB_USER" "$DB_NAME" -t -c "
    SELECT COUNT(*) 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name IN ('users', 'checks', 'tariffs', 'payments');
    " 2>/dev/null | tr -d ' ' || echo "0")
    
    if [ "$TABLE_COUNT" -ge "4" ]; then
        echo -e "   ${PASS} Required tables exist ($TABLE_COUNT/4)"
    else
        echo -e "   ${FAIL} Missing tables (found $TABLE_COUNT/4)"
        ((ERRORS++))
    fi
else
    echo -e "   ${FAIL} Database is NOT accessible"
    ((ERRORS++))
fi
echo ""

# 9. Check for users in database
echo "9️⃣  Checking database content..."
USER_COUNT=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U "$DB_USER" "$DB_NAME" -t -c "SELECT COUNT(*) FROM users;" 2>/dev/null | tr -d ' ' || echo "0")
echo -e "   ${INFO} Total users in database: $USER_COUNT"

CHECK_COUNT=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U "$DB_USER" "$DB_NAME" -t -c "SELECT COUNT(*) FROM checks;" 2>/dev/null | tr -d ' ' || echo "0")
echo -e "   ${INFO} Total checks in database: $CHECK_COUNT"
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Summary:"
echo ""

if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed! Bot is ready for production.${NC}"
    exit 0
elif [ "$ERRORS" -eq 0 ]; then
    echo -e "${YELLOW}⚠️  Bot is mostly ready, but has $WARNINGS warning(s).${NC}"
    echo -e "${YELLOW}   Review warnings above before going live.${NC}"
    exit 0
else
    echo -e "${RED}❌ Bot is NOT ready for production!${NC}"
    echo -e "${RED}   Found $ERRORS error(s) and $WARNINGS warning(s).${NC}"
    echo ""
    echo "🔧 To fix issues:"
    echo "   1. Fix migration issues: ./scripts/fix-alembic-version.sh"
    echo "   2. Remove test tariffs: ./scripts/remove-test-tariffs-manual.sh"
    echo "   3. Check logs: docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f"
    exit 1
fi

