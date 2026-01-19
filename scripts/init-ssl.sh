#!/bin/bash

# SSL Certificate Initialization Script
# Usage: ./init-ssl.sh [domain] [email]
# Example: ./init-ssl.sh nofollowbot.parmenid.tech admin@parmenid.tech

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

# Default values
DOMAIN="${1:-nofollowbot.parmenid.tech}"
EMAIL="${2:-admin@parmenid.tech}"

# Project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Check for .env.prod
if [ ! -f ".env.prod" ]; then
    error ".env.prod file not found! Create it from env.prod.example first."
fi

# Load environment variables
set -a
source .env.prod
set +a

info "SSL Certificate Initialization for: $DOMAIN"
info "Email: $EMAIL"
echo ""

# Step 1: Stop nginx if running
step "Stopping nginx (if running)..."
docker compose -f docker-compose.prod.yml --env-file .env.prod stop nginx 2>/dev/null || true

# Step 2: Get certificate using standalone mode
step "Obtaining SSL certificate using certbot standalone..."

# Determine volume name (based on project directory name)
VOLUME_PREFIX=$(basename "$PROJECT_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')
CERT_VOLUME="${VOLUME_PREFIX}_certbot_certs"

# Check if volume exists, create if not
docker volume inspect "$CERT_VOLUME" > /dev/null 2>&1 || docker volume create "$CERT_VOLUME"

# Run certbot in standalone mode
docker run --rm \
    -p 80:80 \
    -v "$CERT_VOLUME:/etc/letsencrypt" \
    certbot/certbot certonly \
    --standalone \
    --preferred-challenges http \
    -d "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive

if [ $? -ne 0 ]; then
    error "Failed to obtain SSL certificate. Check if port 80 is accessible and DNS is configured."
fi

info "SSL certificate obtained successfully!"

# Step 3: Generate nginx config from template
step "Generating nginx configuration with SSL..."

export DOMAIN
envsubst '${DOMAIN}' < nginx/nginx.conf.template > nginx/nginx.conf

if [ $? -eq 0 ]; then
    info "nginx.conf generated successfully"
else
    error "Failed to generate nginx.conf"
fi

# Step 4: Start nginx with SSL config
step "Starting nginx with SSL configuration..."
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d nginx

echo ""
info "SSL setup completed!"
info "Your site should now be accessible at: https://$DOMAIN"
echo ""
info "To verify SSL certificate:"
echo "  curl -I https://$DOMAIN/health"
echo ""
info "To check certificate expiry:"
echo "  docker run --rm -v ${CERT_VOLUME}:/etc/letsencrypt certbot/certbot certificates"

