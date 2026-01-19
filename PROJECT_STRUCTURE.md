# Структура проекта

## Обзор

Проект организован по принципу разделения ответственности (separation of concerns) с четкой структурой директорий.

## Директории

### `/app` - Основное приложение

- **`api/`** - FastAPI endpoints
  - `router.py` - Основной роутер API
  - `admin.py` - Административные endpoints
  - `payments.py` - Интеграция с платежной системой (Robokassa)
  - `referrals.py` - Реферальная программа
  - `tariffs.py` - Управление тарифами

- **`bot/`** - Telegram бот (aiogram v3)
  - `main.py` - Точка входа бота
  - `handlers/` - Обработчики команд и callback'ов
    - `commands.py` - Обработка команд (`/start`, `/check`, etc.)
    - `callbacks.py` - Обработка inline кнопок

- **`models/`** - Модели данных
  - `database.py` - Настройка подключения к БД
  - `models.py` - SQLAlchemy ORM модели
  - `schemas.py` - Pydantic схемы для валидации

- **`services/`** - Бизнес-логика
  - `check_service.py` - Сервис проверки подписок
  - `instagram_scraper.py` - Парсинг Instagram
  - `file_generator.py` - Генерация Excel отчетов
  - `queue_service.py` - Управление очередью задач
  - `queue_worker.py` - Воркер для обработки очереди
  - `notification_service.py` - Уведомления пользователей
  - `admin_notification_service.py` - Уведомления админов
  - `referral_service.py` - Логика реферальной программы

- **`utils/`** - Утилиты
  - `logger.py` - Настройка логирования
  - `robokassa.py` - Утилиты для работы с Robokassa
  - `validators.py` - Валидаторы данных

- **`config.py`** - Конфигурация приложения
- **`main.py`** - FastAPI приложение

### `/alembic` - Миграции базы данных

- `versions/` - Файлы миграций
  - `001_initial_migration.py` - Начальная миграция
  - `002_monetization.py` - Миграция для монетизации

- `env.py` - Настройка Alembic
- `script.py.mako` - Шаблон для миграций

### `/data` - Данные приложения

- `checks/` - Сгенерированные Excel отчеты (игнорируются в Git)

### `/docs` - Документация

- `SERVER_SETUP.md` - Настройка сервера
- `reqs.md` - Требования проекта
- `ROBOKASSA_URLS.md` - Настройка Robokassa
- `robokassa_cheatsheet.md` - Шпаргалка по Robokassa
- `robokassa_research_prompt.md` - Исследование Robokassa
- `upgrade_prompt.md` - Документация по обновлению
- `README.md` - Индекс документации

### `/scripts` - Скрипты

- `cleanup_server.sh` - Очистка сервера от старого проекта
- `setup_server.sh` - Автоматическая настройка проекта
- `QUICK_START.md` - Быстрый старт

### `/logs` - Логи приложения

- Логи игнорируются в Git

### `/law_docs` - Юридические документы

- Договоры, оферты и другие документы

## Конфигурационные файлы

- `docker-compose.yml` - Конфигурация Docker Compose
- `Dockerfile` - Образ Docker
- `requirements.txt` - Python зависимости
- `pyproject.toml` - Poetry конфигурация
- `alembic.ini` - Конфигурация Alembic
- `env.example` - Пример переменных окружения
- `.gitignore` - Игнорируемые файлы Git

## Docker сервисы

1. **db** - PostgreSQL база данных
2. **app** - FastAPI приложение (порт 8080)
3. **bot** - Telegram бот
4. **worker** - Воркер для обработки очереди

## Порядок запуска

1. База данных (db) - сначала
2. Приложение (app) - после БД
3. Бот (bot) - после приложения
4. Воркер (worker) - после приложения

