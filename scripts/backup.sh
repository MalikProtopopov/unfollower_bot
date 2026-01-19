#!/bin/bash

# Database Backup Script
# Usage: ./backup.sh [backup_dir]
# Example: ./backup.sh /home/user/backups

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

# Project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Check for .env.prod
if [ ! -f ".env.prod" ]; then
    error ".env.prod file not found!"
fi

# Load environment variables
set -a
source .env.prod
set +a

# Backup directory
BACKUP_DIR="${1:-$PROJECT_DIR/backups}"
mkdir -p "$BACKUP_DIR"

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Database settings
DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-mutual_followers}"

info "Starting database backup..."
info "Database: $DB_NAME"
info "Backup directory: $BACKUP_DIR"

# Backup filename
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql"
BACKUP_FILE_GZ="${BACKUP_FILE}.gz"

# Create backup
info "Creating backup: $BACKUP_FILE_GZ"

docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres \
    pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE_GZ"

if [ $? -eq 0 ] && [ -s "$BACKUP_FILE_GZ" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE_GZ" | cut -f1)
    info "Backup created successfully!"
    info "File: $BACKUP_FILE_GZ"
    info "Size: $BACKUP_SIZE"
else
    error "Backup failed!"
fi

# Optional: Remove old backups (keep last 7 days)
info "Cleaning up old backups (keeping last 7 days)..."
find "$BACKUP_DIR" -name "*.sql.gz" -type f -mtime +7 -delete 2>/dev/null || true

# Also backup data/checks directory
DATA_BACKUP_FILE="$BACKUP_DIR/data_checks_${TIMESTAMP}.tar.gz"
if [ -d "$PROJECT_DIR/data/checks" ] && [ "$(ls -A $PROJECT_DIR/data/checks 2>/dev/null)" ]; then
    info "Backing up data/checks directory..."
    tar -czf "$DATA_BACKUP_FILE" -C "$PROJECT_DIR" data/checks
    DATA_SIZE=$(du -h "$DATA_BACKUP_FILE" | cut -f1)
    info "Data backup: $DATA_BACKUP_FILE ($DATA_SIZE)"
fi

echo ""
info "Backup completed!"
echo ""
echo "To restore database from backup:"
echo "  gunzip < $BACKUP_FILE_GZ | docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U $DB_USER $DB_NAME"

