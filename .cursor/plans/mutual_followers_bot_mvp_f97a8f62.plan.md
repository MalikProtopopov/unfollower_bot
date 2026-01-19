---
name: Mutual Followers Bot MVP
overview: Реализация Telegram-бота для анализа взаимных подписок Instagram с FastAPI backend, PostgreSQL, собственным GraphQL-скрейпером и Docker-инфраструктурой.
todos:
  - id: init-project
    content: "Инициализация проекта: Poetry, структура директорий, Docker Compose"
    status: completed
  - id: db-models
    content: SQLAlchemy модели (users, checks, non_mutual_users) и Alembic миграции
    status: completed
    dependencies:
      - init-project
  - id: instagram-scraper
    content: Instagram GraphQL scraper (followers, following, user_info)
    status: completed
    dependencies:
      - init-project
  - id: fastapi-backend
    content: "FastAPI endpoints: POST /check/initiate, GET /check/{check_id}"
    status: completed
    dependencies:
      - db-models
  - id: background-task
    content: "Background task: скрейпинг, вычисление non_mutual, сохранение"
    status: completed
    dependencies:
      - fastapi-backend
      - instagram-scraper
  - id: file-generator
    content: Генератор XLSX файлов с результатами
    status: completed
    dependencies:
      - background-task
  - id: telegram-bot
    content: "Telegram bot (aiogram v3): /start, /check, /help, polling статуса"
    status: completed
    dependencies:
      - fastapi-backend
      - file-generator
  - id: integration-test
    content: Интеграция компонентов и тестирование end-to-end
    status: completed
    dependencies:
      - telegram-bot
---

# План реализации Mutual Followers Analyzer Bot (MVP)

## Архитектура системы

```mermaid
flowchart TB
    subgraph TelegramBot [Telegram Bot - aiogram]
        Start[/start]
        Check[/check]
        Help[/help]
    end
    
    subgraph FastAPIBackend [FastAPI Backend]
        InitiateAPI[POST /api/v1/check/initiate]
        StatusAPI[GET /api/v1/check/check_id]
        BackgroundTask[Background Worker]
    end
    
    subgraph DataLayer [Data Layer]
        PostgreSQL[(PostgreSQL)]
        FileStorage[/data/checks/*.xlsx]
    end
    
    subgraph ExternalScraper [Instagram Scraper]
        GraphQL[GraphQL Scraper]
        SessionManager[Session Manager]
    end
    
    Check --> InitiateAPI
    InitiateAPI --> PostgreSQL
    InitiateAPI --> BackgroundTask
    BackgroundTask --> GraphQL
    GraphQL --> SessionManager
    BackgroundTask --> PostgreSQL
    BackgroundTask --> FileStorage
    StatusAPI --> PostgreSQL
    StatusAPI --> FileStorage
```

---

## Этап 1: Инициализация проекта и инфраструктура

### 1.1 Структура проекта и Poetry

Создать базовую структуру:

```javascript
mutual-followers-analyzer/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── api/
│   ├── models/
│   ├── services/
│   ├── bot/
│   └── utils/
├── data/checks/
└── logs/
```



### 1.2 Зависимости (pyproject.toml)

- fastapi, uvicorn
- aiogram (v3)
- sqlalchemy, asyncpg, alembic
- httpx, aiohttp (для скрейпера)
- pandas, openpyxl
- pydantic-settings
- python-dotenv

### 1.3 Docker Compose

Сервисы:

- `db` - PostgreSQL 15
- `app` - FastAPI backend + background tasks
- `bot` - Telegram bot (aiogram)

---

## Этап 2: База данных и модели

### 2.1 SQLAlchemy модели

Таблицы для MVP:

- `users` - пользователи Telegram-бота
- `checks` - записи проверок (check_id, status, target_username, file_path)
- `non_mutual_users` - результаты проверки

### 2.2 Alembic миграции

Настроить автогенерацию миграций и initial migration.---

## Этап 3: Instagram GraphQL Scraper

### 3.1 Модуль скрейпера (`app/services/instagram_scraper.py`)

Реализовать:

- Класс `InstagramScraper` с методами:
- `get_followers(username)` - получение подписчиков
- `get_following(username)` - получение подписок
- `get_user_info(username)` - базовая информация профиля
- Session management (cookies, headers эмуляции браузера)
- Rate limiting и retry с exponential backoff
- Обход Cloudflare (User-Agent rotation, delays)

### 3.2 GraphQL endpoints

Использовать query_hash для:

- Followers: `query_hash=...&variables={"id":"...","first":50}`
- Following: аналогичный запрос с другим query_hash

### 3.3 Обработка ошибок

- Приватный аккаунт
- Несуществующий пользователь
- Rate limit от Instagram
- Изменение API (логирование для отладки)

---

## Этап 4: FastAPI Backend

### 4.1 API Endpoints (`app/api/router.py`)

**POST /api/v1/check/initiate**

- Валидация Instagram username
- Создание записи в `checks` со статусом `pending`
- Запуск background task для скрейпинга
- Возврат `check_id`

**GET /api/v1/check/{check_id}**

- Возврат текущего статуса проверки
- При `completed` - путь к файлу и статистика

### 4.2 Background Task (`app/services/check_service.py`)

Логика:

1. Получить followers и following через scraper
2. Вычислить non_mutual = following - followers
3. Сохранить результаты в `non_mutual_users`
4. Сгенерировать XLSX файл
5. Обновить статус на `completed`

### 4.3 Pydantic Schemas (`app/models/schemas.py`)

- `CheckInitiateRequest`, `CheckInitiateResponse`
- `CheckStatusResponse`
- `NonMutualUser`

---

## Этап 5: Генерация XLSX файла

### 5.1 File Generator (`app/services/file_generator.py`)

Колонки:

- # (порядковый номер)
- Username
- Имя (full_name)
- Подписан на целевого? (да/нет)
- Целевой подписан? (да/нет)
- Взаимно? (да/нет)

Метаданные в шапке:

- Анализ для @username
- Дата проверки
- Всего подписок / Не взаимных

---

## Этап 6: Telegram Bot (aiogram v3)

### 6.1 Handlers (`app/bot/handlers/`)

**/start**

- Регистрация пользователя в `users`
- Приветственное сообщение

**/check**

- Запрос Instagram username
- Валидация и нормализация ника
- Вызов POST /api/v1/check/initiate
- Polling статуса каждые 5 секунд
- Отправка файла при готовности

**/help**

- Краткая инструкция

### 6.2 Callback handlers

- Inline-кнопки для отмены проверки
- Обработка состояний (FSM)

### 6.3 Интеграция с FastAPI

Бот общается с backend через httpx/aiohttp или напрямую через импорт сервисов.---

## Этап 7: Конфигурация и запуск

### 7.1 Переменные окружения (.env)

```env
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/mutual_followers
TELEGRAM_TOKEN=your_bot_token
INSTAGRAM_SESSION_ID=...  # опционально для авторизованных запросов
UPLOAD_DIR=./data/checks
DEBUG=True
```



### 7.2 Docker запуск

```bash
docker-compose up --build
```

---

## Риски и митигация

| Риск | Митигация ||------|-----------|| Бан сессии Instagram | Rotation User-Agent, delays между запросами, retry logic || Изменение GraphQL API | Логирование ответов, alerts при ошибках парсинга || Приватные аккаунты | Чёткое сообщение пользователю о невозможности проверки |---

## Порядок реализации

1. **Инфраструктура** - Poetry, Docker, базовая структура
2. **БД** - модели SQLAlchemy, миграции Alembic
3. **Скрейпер** - Instagram GraphQL модуль
4. **Backend** - FastAPI endpoints, background tasks
5. **Генератор файлов** - XLSX с pandas