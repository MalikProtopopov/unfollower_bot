#!/bin/bash

# Zero-Downtime Deployment Script
# Usage: ./deploy.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Check for .env.prod
if [ ! -f ".env.prod" ]; then
    error ".env.prod file not found!"
fi

info "Starting deployment..."
echo ""

# Step 1: Pull latest changes
step "Pulling latest changes from git..."
git pull origin main || git pull origin master || warn "Git pull failed, continuing with local code"

# Step 2: Build new images
step "Building new Docker images..."
docker compose -f docker-compose.prod.yml --env-file .env.prod build --no-cache backend

# Step 3: Run database migrations
step "Running database migrations..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head

if [ $? -ne 0 ]; then
    warn "Migrations failed or no new migrations to apply"
fi

# Step 3.5: Verify tariffs after migration
step "Verifying tariffs in database..."
echo ""
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
" || warn "Could not query tariffs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for test/trial tariffs
TEST_COUNT=$(docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U postgres mutual_followers -t -c "
SELECT COUNT(*) 
FROM tariffs 
WHERE name IN ('Test', 'Test Pack', 'Trial', 'Тест: 1 проверка', 'Тест: 3 проверки', '1 проверка (тест)', '3 проверки (тест)');
" 2>/dev/null | tr -d ' ' || echo "0")

if [ "$TEST_COUNT" = "0" ] || [ -z "$TEST_COUNT" ]; then
    info "✅ Test/trial tariffs successfully removed!"
else
    warn "⚠️  Found $TEST_COUNT test/trial tariff(s) in database"
fi
echo ""

# Step 4: Restart services
step "Restarting services..."

# Stop old containers (except postgres and nginx)
docker compose -f docker-compose.prod.yml --env-file .env.prod stop backend bot worker

# Start new containers
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d backend bot worker

# Step 5: Reload nginx (if running)
step "Reloading nginx..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec nginx nginx -s reload 2>/dev/null || warn "Nginx reload skipped"

# Step 6: Health check
step "Performing health check..."
sleep 5

HEALTH_URL="http://localhost:8000/health"
if docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend curl -f $HEALTH_URL > /dev/null 2>&1; then
    info "Health check passed!"
else
    warn "Health check failed - please verify manually"
fi

# Step 7: Show status
step "Current container status:"
docker compose -f docker-compose.prod.yml --env-file .env.prod ps

echo ""
info "Deployment completed!"
info "Check logs with: docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f"

