# Backend Deployment Prompt

> **Используй эту документацию как промпт для настройки деплоя FastAPI бекенда на удалённый сервер с Docker, Nginx, SSL и PostgreSQL.**

---

## 🎯 Цель

Настроить полный деплой FastAPI бекенда с:
- Docker и Docker Compose для контейнеризации
- Nginx как reverse proxy с SSL (Let's Encrypt)
- PostgreSQL и Redis
- Makefile для автоматизации команд
- Zero-downtime деплой

---

## 📁 Структура файлов для создания

```
backend/
├── Dockerfile                    # Multi-stage Docker образ
├── docker-compose.yml            # Development environment
├── docker-compose.prod.yml       # Production environment
├── Makefile                      # Команды автоматизации
├── .gitignore                    # Git ignore
├── .dockerignore                 # Docker ignore (ускоряет сборку)
├── env.dev                       # Dev environment template
├── env.prod.example              # Prod environment template
├── alembic/
│   └── env.py                    # ВАЖНО: экранирование % для URL-encoded паролей
├── nginx/
│   ├── nginx-initial.conf        # Начальная конфигурация (HTTP only)
│   ├── nginx.conf.template       # Шаблон с SSL
│   └── conf.d/                   # Дополнительные конфиги
└── scripts/
    ├── init-ssl.sh               # Инициализация SSL сертификатов
    ├── deploy.sh                 # Zero-downtime деплой
    └── backup.sh                 # Бэкапы БД
```

---

## 🔧 Ключевые файлы

### 1. Dockerfile (Multi-stage build)

```dockerfile
# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for better caching
COPY pyproject.toml README.md ./
COPY app/ ./app/

# Create virtualenv and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .


# Production stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2. docker-compose.prod.yml (Production)

```yaml
services:
  nginx:
    image: nginx:alpine
    container_name: ${PROJECT_NAME}_nginx_prod
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - certbot_webroot:/var/www/certbot:ro
      - certbot_certs:/etc/letsencrypt:ro
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - app_network

  certbot:
    image: certbot/certbot:latest
    container_name: ${PROJECT_NAME}_certbot_prod
    volumes:
      - certbot_webroot:/var/www/certbot
      - certbot_certs:/etc/letsencrypt
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
    networks:
      - app_network

  postgres:
    image: postgres:16-alpine
    container_name: ${PROJECT_NAME}_postgres_prod
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-app_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
      POSTGRES_DB: ${POSTGRES_DB:-app_db}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    expose:
      - "5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-app_user} -d ${POSTGRES_DB:-app_db}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app_network

  redis:
    image: redis:7-alpine
    container_name: ${PROJECT_NAME}_redis_prod
    restart: unless-stopped
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:?REDIS_PASSWORD is required}
    volumes:
      - redis_data:/data
    expose:
      - "6379"
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app_network

  backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ${PROJECT_NAME}_backend_prod
    restart: unless-stopped
    env_file:
      - .env.prod
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-app_user}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-app_db}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      ENVIRONMENT: production
    expose:
      - "8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    networks:
      - app_network

  # ВАЖНО: migrations использует ТОТ ЖЕ образ что и backend!
  migrations:
    image: backend-backend:latest  # НЕ build, а image!
    container_name: ${PROJECT_NAME}_migrations_prod
    env_file:
      - .env.prod
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-app_user}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-app_db}
    command: alembic upgrade head
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"
    networks:
      - app_network

volumes:
  postgres_data:
  redis_data:
  certbot_webroot:
  certbot_certs:

networks:
  app_network:
    driver: bridge
```

### 3. alembic/env.py (КРИТИЧЕСКИ ВАЖНОЕ ИСПРАВЛЕНИЕ!)

```python
# Alembic Config object
config = context.config

# ВАЖНО: Экранирование % для ConfigParser
# Если в пароле есть спецсимволы (/, @, % и т.д.), они URL-encoded
# ConfigParser интерпретирует % как интерполяцию, поэтому нужно экранировать
database_url_str = str(settings.database_url).replace("%", "%%")
config.set_main_option("sqlalchemy.url", database_url_str)
```

---

## ⚠️ Критические ошибки и их решения

### Ошибка 1: URL-encoded пароли в DATABASE_URL

**Проблема:** Пароль содержит спецсимволы (`/`, `@`, `%`)

**Решение:** URL-encode спецсимволы в пароле:
```bash
# Пароль: 7cFe5yi/CU2O7RkbMDT7PlYg/Ig9bW0L
# После encoding: 7cFe5yi%2FCU2O7RkbMDT7PlYg%2FIg9bW0L

# / → %2F
# @ → %40
# % → %25
```

**В .env.prod:**
```
DATABASE_URL=postgresql+asyncpg://user:7cFe5yi%2FCU2O7RkbMDT7PlYg%2FIg9bW0L@postgres:5432/db
```

### Ошибка 2: ConfigParser interpolation в alembic

**Проблема:** `ValueError: invalid interpolation syntax in '...' at position 37`

**Решение:** В `alembic/env.py` экранировать `%`:
```python
database_url_str = str(settings.database_url).replace("%", "%%")
config.set_main_option("sqlalchemy.url", database_url_str)
```

### Ошибка 3: Сервис migrations использует старый образ

**Проблема:** После `docker compose build backend` сервис `migrations` всё ещё использует старый образ

**Решение:** В `docker-compose.prod.yml` использовать `image:` вместо `build:`:
```yaml
migrations:
  image: backend-backend:latest  # Использует тот же образ что и backend
  # НЕ build: ... !
```

### Ошибка 4: Переменные окружения не загружаются

**Проблема:** `POSTGRES_PASSWORD is missing a value`

**Решение:** ВСЕГДА использовать `--env-file`:
```bash
# ПРАВИЛЬНО:
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

# НЕПРАВИЛЬНО:
docker compose -f docker-compose.prod.yml up -d
```

### Ошибка 5: SSL сертификат не создаётся

**Проблема:** Nginx возвращает 404 на ACME challenge

**Решение:** Использовать standalone режим certbot:
```bash
# Остановить nginx
docker compose -f docker-compose.prod.yml --env-file .env.prod stop nginx

# Получить сертификат в standalone режиме
docker run --rm -p 80:80 -v certbot_certs:/etc/letsencrypt certbot/certbot certonly \
  --standalone -d api.domain.com -d admin.domain.com --email admin@domain.com --agree-tos --no-eff-email

# Запустить nginx с SSL конфигурацией
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d nginx
```

---

## 🚀 Пошаговый деплой на сервер

### Шаг 1: Подготовка сервера

```bash
# Установка Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Установка Docker Compose (если не входит в Docker)
sudo apt install docker-compose-plugin

# Создание директории
sudo mkdir -p /opt/myproject
sudo chown $USER:$USER /opt/myproject
cd /opt/myproject
```

### Шаг 2: Клонирование и настройка

```bash
# Клонирование
git clone https://github.com/user/repo.git .
cd backend

# Настройка окружения
cp env.prod.example .env.prod
nano .env.prod  # Заполнить ВСЕ значения!

# ВАЖНО: Если в пароле есть / или другие спецсимволы - URL-encode их!
```

### Шаг 3: Настройка DNS

Создать A-записи:
- `api.domain.com` → IP сервера
- `admin.domain.com` → IP сервера

### Шаг 4: Первый запуск (HTTP)

```bash
# Копируем начальную конфигурацию nginx
cp nginx/nginx-initial.conf nginx/nginx.conf

# Запускаем сервисы
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d postgres redis
sleep 5

# Собираем и запускаем backend
docker compose -f docker-compose.prod.yml --env-file .env.prod build backend
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d backend

# Запускаем nginx
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d nginx
```

### Шаг 5: Получение SSL сертификата

```bash
# Способ 1: Через скрипт
chmod +x scripts/init-ssl.sh
./scripts/init-ssl.sh domain.com admin@domain.com

# Способ 2: Вручную (если скрипт не работает)
# Остановить nginx
docker compose -f docker-compose.prod.yml --env-file .env.prod stop nginx

# Получить сертификат
docker run --rm -p 80:80 \
  -v cms_certbot_certs:/etc/letsencrypt \
  certbot/certbot certonly --standalone \
  -d api.domain.com -d admin.domain.com \
  --email admin@domain.com --agree-tos --no-eff-email

# Сгенерировать nginx конфиг
export DOMAIN=domain.com
envsubst '${DOMAIN}' < nginx/nginx.conf.template > nginx/nginx.conf

# Запустить nginx
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d nginx
```

### Шаг 6: Миграции и инициализация

```bash
# Миграции (ПОСЛЕ сборки backend!)
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations

# Инициализация админа
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python -m app.scripts.init_admin
```

### Шаг 7: Проверка

```bash
# Статус сервисов
docker compose -f docker-compose.prod.yml --env-file .env.prod ps

# Логи
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f backend

# Тест API
curl https://api.domain.com/health
```

---

## 📋 Makefile команды

```makefile
# Основные команды
prod-up:
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

prod-down:
	docker compose -f docker-compose.prod.yml --env-file .env.prod down

prod-logs:
	docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f

prod-build:
	docker compose -f docker-compose.prod.yml --env-file .env.prod build

# Миграции
migrate-prod:
	docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations

# Админ
init-admin-prod:
	docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python -m app.scripts.init_admin

# Деплой
deploy:
	./scripts/deploy.sh
```

---

## 🔄 Обновление (деплой новой версии)

```bash
cd /opt/myproject/backend

# Получить изменения
git pull origin main

# Пересобрать образ
docker compose -f docker-compose.prod.yml --env-file .env.prod build --no-cache backend

# Миграции (если есть новые)
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrations

# Перезапуск
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d backend
docker compose -f docker-compose.prod.yml --env-file .env.prod exec nginx nginx -s reload
```

---

## 📦 Чеклист перед деплоем

- [ ] DNS A-записи настроены (api.domain.com, admin.domain.com)
- [ ] `.env.prod` заполнен всеми значениями
- [ ] Пароли с спецсимволами URL-encoded
- [ ] `alembic/env.py` содержит экранирование `%`
- [ ] Сервис `migrations` использует `image:` а не `build:`
- [ ] Порты 80 и 443 открыты в firewall
- [ ] Docker login выполнен (для избежания rate limits)

---

## 🛡️ Безопасность

1. **Не храни .env.prod в Git!** (добавь в .gitignore)
2. **Используй сложные пароли:** `openssl rand -base64 24`
3. **Ограничь доступ к серверу** (SSH keys only, fail2ban)
4. **Регулярные бэкапы:** `make db-backup`
5. **Мониторинг логов:** `make prod-logs`

