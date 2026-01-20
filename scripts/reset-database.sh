#!/bin/bash
# DANGER: This script will DELETE ALL DATA from the database!
# Use only for development/testing environments!

set -e

echo "=== DATABASE RESET SCRIPT ==="
echo ""
echo "⚠️  WARNING: This will DELETE ALL DATA from the database!"
echo "   - All users"
echo "   - All payments"
echo "   - All checks"
echo "   - All referrals"
echo "   - Everything!"
echo ""
read -p "Are you ABSOLUTELY SURE? Type 'DELETE ALL DATA' to confirm: " confirmation

if [ "$confirmation" != "DELETE ALL DATA" ]; then
    echo "Aborted. Database was NOT modified."
    exit 1
fi

cd ~/projects/unfollower_bot || exit 1

echo ""
echo "Stopping containers..."
docker compose -f docker-compose.prod.yml --env-file .env.prod down

echo "Starting PostgreSQL only..."
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d postgres

echo "Waiting for PostgreSQL to be ready..."
sleep 10

echo "Dropping database..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres -c "DROP DATABASE IF EXISTS mutual_followers;"

echo "Creating fresh database..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres -c "CREATE DATABASE mutual_followers;"

echo "Starting all services..."
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

echo "Waiting for services to be ready..."
sleep 10

echo "Applying all migrations from scratch..."
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations alembic upgrade head

echo ""
echo "=== Database Reset Complete ==="
echo "Database is now empty and all migrations have been applied."

