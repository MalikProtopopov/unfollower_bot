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
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head

echo "🔍 Checking current migration version..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic current

echo "✅ Verifying tariffs in database..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers -c "SELECT name, checks_count, price_stars FROM tariffs WHERE is_active = true ORDER BY sort_order;"

echo "🔄 Restarting backend and bot..."
docker compose -f docker-compose.prod.yml --env-file .env.prod restart backend bot

echo "✅ Done! Migrations should now be applied."

