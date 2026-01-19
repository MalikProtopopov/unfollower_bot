# NoFollowBot Makefile
# Production deployment automation for nofollowbot.parmenid.tech

.PHONY: help dev dev-up dev-down dev-logs dev-build \
        prod-init prod-up prod-down prod-logs prod-build prod-restart prod-ps \
        migrate-dev migrate-prod ssl-init deploy db-backup clean

# Default target
help:
	@echo "NoFollowBot - Makefile Commands"
	@echo ""
	@echo "Development:"
	@echo "  make dev          - Start development environment"
	@echo "  make dev-down     - Stop development environment"
	@echo "  make dev-logs     - View development logs"
	@echo "  make dev-build    - Rebuild development containers"
	@echo ""
	@echo "Production:"
	@echo "  make prod-init    - First-time production setup (HTTP only)"
	@echo "  make prod-up      - Start production environment"
	@echo "  make prod-down    - Stop production environment"
	@echo "  make prod-logs    - View production logs"
	@echo "  make prod-build   - Rebuild production containers"
	@echo "  make prod-restart - Restart production services"
	@echo "  make prod-ps      - Show production container status"
	@echo ""
	@echo "Database:"
	@echo "  make migrate-dev  - Run migrations (development)"
	@echo "  make migrate-prod - Run migrations (production)"
	@echo "  make db-backup    - Backup production database"
	@echo ""
	@echo "SSL & Deployment:"
	@echo "  make ssl-init     - Initialize SSL certificates"
	@echo "  make deploy       - Full deployment (pull, build, migrate, restart)"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean        - Remove unused Docker resources"

# =============================================================================
# DEVELOPMENT
# =============================================================================

dev: dev-up

dev-up:
	docker compose up -d
	@echo ""
	@echo "Development environment started!"
	@echo "API: http://localhost:8080"
	@echo "Docs: http://localhost:8080/docs"

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f

dev-build:
	docker compose build

migrate-dev:
	docker compose exec app alembic upgrade head

# =============================================================================
# PRODUCTION
# =============================================================================

# Check for .env.prod file
check-env-prod:
	@if [ ! -f .env.prod ]; then \
		echo "Error: .env.prod file not found!"; \
		echo "Create it from env.prod.example:"; \
		echo "  cp env.prod.example .env.prod"; \
		echo "  nano .env.prod"; \
		exit 1; \
	fi

# First-time setup (HTTP only, before SSL)
prod-init: check-env-prod
	@echo "Initializing production environment..."
	mkdir -p data/checks logs backups
	cp nginx/nginx-initial.conf nginx/nginx.conf
	docker compose -f docker-compose.prod.yml --env-file .env.prod build
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d postgres
	@echo "Waiting for PostgreSQL to be ready..."
	sleep 5
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d backend bot worker
	@echo "Waiting for backend to be ready..."
	sleep 10
	docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations || true
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d nginx
	@echo ""
	@echo "Production environment initialized (HTTP only)!"
	@echo "Now run 'make ssl-init' to obtain SSL certificate"

prod-up: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

prod-down: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod down

prod-logs: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f

prod-logs-backend: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f backend

prod-logs-bot: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f bot

prod-logs-worker: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f worker

prod-build: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod build

prod-restart: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod restart backend bot worker
	docker compose -f docker-compose.prod.yml --env-file .env.prod exec nginx nginx -s reload || true

prod-ps: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod ps

# =============================================================================
# DATABASE
# =============================================================================

migrate-prod: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations

db-backup: check-env-prod
	./scripts/backup.sh

db-restore: check-env-prod
	@echo "Usage: gunzip < backups/BACKUP_FILE.sql.gz | docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U postgres mutual_followers"

# =============================================================================
# SSL & DEPLOYMENT
# =============================================================================

ssl-init: check-env-prod
	chmod +x scripts/init-ssl.sh
	./scripts/init-ssl.sh

ssl-renew: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod exec certbot certbot renew
	docker compose -f docker-compose.prod.yml --env-file .env.prod exec nginx nginx -s reload

deploy: check-env-prod
	chmod +x scripts/deploy.sh
	./scripts/deploy.sh

# =============================================================================
# MAINTENANCE
# =============================================================================

clean:
	docker system prune -af --volumes
	@echo "Docker cleanup completed!"

# Show container resource usage
stats: check-env-prod
	docker stats --no-stream

# Enter backend container shell
shell-backend: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend bash

# Enter postgres container
shell-db: check-env-prod
	docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers

