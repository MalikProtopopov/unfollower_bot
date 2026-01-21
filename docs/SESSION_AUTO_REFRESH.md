# Автоматическое обновление Instagram Session

## Обзор

Эта функция автоматически обновляет Instagram `sessionid` cookie, предотвращая ошибки 401 Unauthorized и минимизируя потерю данных при проверках.

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                    ADMIN API                             │
│  POST /api/v1/admin/session/credentials - сохранить     │
│  POST /api/v1/admin/session/refresh - запустить обновл. │
│  GET  /api/v1/admin/session/refresh-status - статус     │
└───────────────────────────┬─────────────────────────────┘
                            │
        ┌───────────────────▼───────────────────┐
        │         TaskIQ Worker                  │
        │  (Background Tasks with Redis)         │
        ├────────────────────────────────────────┤
        │  • proactive_refresh_task (каждые 6ч) │
        │  • reactive_refresh_task (при 401)    │
        │  • check_session_health_task (каждый ч)│
        └───────────────────────────┬───────────┘
                                    │
        ┌───────────────────────────▼───────────┐
        │       SessionRefreshService            │
        ├────────────────────────────────────────┤
        │  • login_with_playwright()             │
        │  • refresh_session()                   │
        │  • reactive_refresh()                  │
        └────────────────────────────────────────┘
                            │
                            ▼
        ┌────────────────────────────────────────┐
        │          PostgreSQL                     │
        │  • instagram_sessions (+ new fields)   │
        │  • refresh_credentials (encrypted)     │
        │  • check_progress (resume data)        │
        └────────────────────────────────────────┘
```

## Компоненты

### 1. SessionRefreshService

Основной сервис для получения новой сессии через Playwright:

- Автоматический логин в Instagram
- Поддержка 2FA через TOTP
- Извлечение sessionid cookie
- Anti-detection механизмы

### 2. TaskIQ Tasks

- **proactive_refresh_task**: Запускается каждые 6 часов, проверяет нужно ли обновить сессию (старше 2 дней)
- **reactive_refresh_task**: Запускается при получении 401 ошибки
- **check_session_health_task**: Проверяет здоровье сессии каждый час

### 3. Progress Service

Сохраняет прогресс проверки для возможности продолжения после обновления сессии.

## Настройка

### 1. Добавить переменные окружения

```env
# Redis для TaskIQ
REDIS_URL=redis://localhost:6379/0
USE_REDIS=true

# Ключ шифрования для credentials
ENCRYPTION_KEY=your-32-byte-secret-key
```

### 2. Применить миграцию

```bash
docker compose exec app alembic upgrade head
```

### 3. Запустить TaskIQ worker и scheduler

```bash
# С профилем auto-refresh
docker compose --profile auto-refresh up -d
```

### 4. Сохранить credentials через Admin API

```bash
curl -X POST http://localhost:8080/api/v1/admin/session/credentials \
  -H "Content-Type: application/json" \
  -H "X-User-Id: YOUR_ADMIN_ID" \
  -d '{"username": "instagram_username", "password": "instagram_password"}'
```

## API Endpoints

### GET /api/v1/admin/session/refresh-status

Получить статус системы автоматического обновления.

**Response:**
```json
{
  "has_credentials": true,
  "credentials_username": "instagram_user",
  "session_active": true,
  "session_valid": true,
  "next_refresh_at": "2026-01-23T03:00:00Z",
  "fail_count": 0,
  "last_error": null
}
```

### POST /api/v1/admin/session/credentials

Сохранить credentials для автоматического обновления.

**Request:**
```json
{
  "username": "instagram_username",
  "password": "instagram_password",
  "totp_secret": "OPTIONAL_2FA_SECRET"
}
```

### POST /api/v1/admin/session/refresh

Запустить обновление сессии асинхронно (через TaskIQ).

### POST /api/v1/admin/session/refresh-sync

Запустить обновление сессии синхронно (блокирует до завершения).

## Безопасность

1. **Шифрование**: Все credentials шифруются с помощью Fernet (AES-128-CBC) перед сохранением в БД
2. **Не логируются**: Пароли никогда не выводятся в логи
3. **Ротация**: Рекомендуется периодически менять ENCRYPTION_KEY

## Мониторинг

Логи содержат информацию о:
- Успешных/неуспешных обновлениях сессии
- Расписании следующего обновления
- Ошибках при логине

## Troubleshooting

### Session refresh fails

1. Проверьте credentials правильные
2. Проверьте нет ли 2FA без TOTP secret
3. Проверьте не заблокирован ли аккаунт Instagram

### TaskIQ tasks not running

1. Проверьте Redis запущен: `docker compose ps redis`
2. Проверьте TaskIQ worker: `docker compose logs taskiq-worker`
3. Проверьте USE_REDIS=true

### Playwright errors in Docker

1. Убедитесь Dockerfile включает все зависимости Chromium
2. Попробуйте пересобрать: `docker compose build --no-cache`
