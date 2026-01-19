# Mutual Followers Analyzer

Telegram-бот для анализа взаимных подписок Instagram. Позволяет узнать, кто из ваших подписок не подписан на вас взаимно.

## Возможности

- 🔍 Анализ взаимных подписок Instagram
- 📊 Генерация отчёта в Excel формате
- 📱 Удобный интерфейс через Telegram-бота
- 🚀 Асинхронная обработка запросов

## Технологии

- **Backend**: FastAPI
- **Bot**: aiogram v3
- **Database**: PostgreSQL + SQLAlchemy
- **Scraper**: httpx + Instagram GraphQL API
- **Reports**: pandas + openpyxl
- **Infrastructure**: Docker + Docker Compose
- **Package Manager**: Poetry

## Быстрый старт

### 1. Клонирование и настройка

```bash
cd check_follows

# Копируем пример конфигурации
cp env.example .env
```

### 2. Настройка переменных окружения

Отредактируйте `.env` файл:

```env
# Telegram Bot Token (получить у @BotFather)
TELEGRAM_TOKEN=your_bot_token_here

# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=mutual_followers

# Instagram (опционально - для авторизованных запросов)
INSTAGRAM_SESSION_ID=
```

### 3. Запуск через Docker

```bash
docker-compose up --build
```

Это запустит:
- PostgreSQL базу данных
- FastAPI backend на порту 8000
- Telegram бот

### 4. Использование бота

1. Найдите вашего бота в Telegram
2. Отправьте `/start`
3. Используйте `/check` для начала проверки
4. Введите Instagram ник или ссылку на профиль
5. Дождитесь результата и получите Excel файл

## Структура проекта

```
mutual-followers-analyzer/
├── app/
│   ├── api/           # FastAPI endpoints
│   ├── bot/           # Telegram bot (aiogram)
│   │   └── handlers/  # Command handlers
│   ├── models/        # SQLAlchemy models & Pydantic schemas
│   ├── services/      # Business logic
│   │   ├── instagram_scraper.py
│   │   ├── check_service.py
│   │   └── file_generator.py
│   └── utils/         # Utilities
├── alembic/           # Database migrations
├── data/checks/       # Generated reports
├── logs/              # Application logs
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## API Endpoints

### POST /api/v1/check/initiate
Инициирует новую проверку.

**Request:**
```json
{
  "username": "instagram_username",
  "platform": "instagram",
  "user_id": 123456789
}
```

**Response:**
```json
{
  "check_id": "uuid",
  "status": "pending",
  "estimated_time": 60
}
```

### GET /api/v1/check/{check_id}
Получает статус проверки.

**Response (processing):**
```json
{
  "check_id": "uuid",
  "status": "processing",
  "progress": 50
}
```

**Response (completed):**
```json
{
  "check_id": "uuid",
  "status": "completed",
  "total_subscriptions": 500,
  "total_followers": 450,
  "total_non_mutual": 100,
  "file_path": "/data/checks/uuid.xlsx"
}
```

## Разработка

### Локальный запуск без Docker

```bash
# Установка зависимостей
poetry install

# Запуск PostgreSQL
docker run -d --name postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=mutual_followers \
  -p 5432:5432 postgres:15-alpine

# Применение миграций
alembic upgrade head

# Запуск FastAPI
poetry run uvicorn app.main:app --reload

# Запуск бота (в отдельном терминале)
poetry run python -m app.bot.main
```

### Миграции базы данных

```bash
# Создание новой миграции
alembic revision --autogenerate -m "description"

# Применение миграций
alembic upgrade head

# Откат миграции
alembic downgrade -1
```

## Настройка на сервере

### Очистка сервера от старого проекта

Если на сервере был другой проект и нужно его удалить:

```bash
# Использование скрипта (рекомендуется)
chmod +x scripts/cleanup_server.sh
./scripts/cleanup_server.sh

# Или вручную
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
docker rmi $(docker images -q)
docker system prune -af --volumes
```

### Настройка нового проекта

```bash
# 1. Загрузите проект на сервер (git clone или scp)

# 2. Используйте скрипт автоматической настройки
chmod +x scripts/setup_server.sh
./scripts/setup_server.sh

# Или вручную:
cp env.example .env
# Отредактируйте .env файл с вашими настройками
mkdir -p data/checks logs
docker-compose build
docker-compose up -d
docker-compose exec app alembic upgrade head
```

**Подробная инструкция:** [docs/SERVER_SETUP.md](docs/SERVER_SETUP.md)

## Ограничения

- ⚠️ Работает только с публичными Instagram аккаунтами
- ⚠️ Максимум 10,000 подписок/подписчиков
- ⚠️ Instagram может временно ограничивать доступ при частых запросах

## Лицензия

MIT

# unfollower_bot
