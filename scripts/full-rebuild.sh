#!/bin/bash
# Full rebuild script for production

set -e

echo "=== Full Rebuild Script ==="
echo "This will:"
echo "1. Stop all containers"
echo "2. Remove all containers"
echo "3. Remove all images"
echo "4. Pull latest code"
echo "5. Rebuild everything from scratch"
echo "6. Apply migrations"
echo "7. Start services"
echo ""
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

cd ~/projects/unfollower_bot || exit 1

# 1. Stop and remove containers
echo "Stopping containers..."
docker compose -f docker-compose.prod.yml --env-file .env.prod down

# 2. Remove images (optional - uncomment if needed)
# echo "Removing images..."
# docker compose -f docker-compose.prod.yml --env-file .env.prod down --rmi all

# 3. Pull latest code
echo "Pulling latest code..."
git pull origin main

# 4. Rebuild without cache
echo "Rebuilding images (no cache)..."
docker compose -f docker-compose.prod.yml --env-file .env.prod build --no-cache backend bot migrations

# 5. Start services
echo "Starting services..."
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

# 6. Wait for postgres to be ready
echo "Waiting for PostgreSQL..."
sleep 10

# 7. Apply migrations
echo "Applying migrations..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head

# 8. Check status
echo "Checking container status..."
docker compose -f docker-compose.prod.yml --env-file .env.prod ps

echo ""
echo "=== Rebuild Complete ==="
echo "Check logs with: docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f"

