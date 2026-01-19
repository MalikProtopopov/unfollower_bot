Собрал всё в один большой файл в одном сообщении. [stackoverflow](https://stackoverflow.com/questions/1580746/how-to-concatenate-multiple-python-source-files-into-a-single-file)

Скопируй содержимое ниже в файл, например `mutual_followers_full_spec.md`, и используй как единый документ.

***

```markdown
# Исследовательский Промпт + Спецификация Требований  
## Проект: Telegram Bot для Анализа Взаимных Подписок (FastAPI, Docker, Poetry, aiogram)

---

## ЧАСТЬ 1. Исследовательский Промпт: Анализатор Взаимных Подписок

### Цель исследования

Собрать полные требования для разработки **Telegram-бота с FastAPI backend**, который позволяет анализировать взаимные подписки между пользователем и его подписчиками (по Telegram или Instagram-аккаунту) и определять, какие из подписок пользователя не подписаны на него взаимно, с использованием асинхронных двухэтапных API-запросов.

- Итоговая архитектура API под капотом:
  1. `POST` — отправка заявки, в ответе приходит `check_id` (идентификатор проверки).
  2. `GET` — запрос по `check_id`, который возвращает таблицу с пользователями (не взаимные подписки) и метаданными.

- Взаимодействие пользователя — через **Telegram-бот**:
  - Пользователь присылает свой ник/ссылку (TG или Instagram)
  - Получает файл с таблицей, кто не подписан взаимно.

---

### 1. Источник данных (API)

**Нужно исследовать и зафиксировать:**

- Какой API используется как источник данных:
  - Telegram (через user API / client API / сторонние сервисы)
  - Instagram (официальный Graph API / неофициальный / сторонний сервис аналитики)
- Есть ли готовый внешний endpoint (или нужно писать свой скрейпер), который:
  - Принимает username / user_id
  - Возвращает `check_id` в ответе при инициации проверки
  - По `check_id` возвращает список пользователей с полной информацией:
    - username
    - first_name / full_name
    - avatar
    - флаги: подписан ли он на меня / подписан ли я на него / взаимно ли
- Формат и структура ответов API:
  - Тело `POST /check/initiate`
  - Тело `GET /check/{check_id}`
  - Формат ошибок
- Ограничения:
  - Rate limiting (кол-во запросов в минуту/час)
  - Лимит по количеству подписок (например, до 10k)
- Авторизация:
  - Нужен ли API key / Bearer token / OAuth
  - Как хранить и прокидывать токены

**Вопросы в исследовании:**

1. Можно ли по одному никнейму (Instagram/TG) получить:
   - Список подписчиков
   - Список подписок
   - Отметку, кто из подписок не подписан взаимно?
2. Есть ли готовой логики формирования `check_id` на стороне API или это ответственность нашего сервиса?
3. Как долго внешний API обрабатывает одну проверку (по времени), чтобы спланировать polling?

---

### 2. Архитектура двухэтапного запроса

#### Этап 1: Инициация проверки

Пример целевого контракта:

```http
POST /api/v1/check/initiate
Content-Type: application/json

{
  "username": "example_user",
  "platform": "instagram"   // или "telegram"
}
```

Ответ:

```json
{
  "check_id": "uuid-xxx-yyy",
  "status": "pending",
  "estimated_time": 30
}
```

**Требования:**

- Валидация username:
  - Для Telegram: `^@?[a-zA-Z0-9_]{5,32}$`
  - Для Instagram: `^[a-zA-Z0-9._]{1,30}$`
- Унификация username (убрать `@` в начале, привести к lower-case, если нужно).
- Генерация/приём `check_id` (если внешний API его отдаёт — просто сохраняем).
- Сохранение записи в БД в таблицу `checks`:
  - user_id (из Telegram)
  - target_username
  - статус `pending`
  - платформа (instagram/telegram)
  - timestamp создания
- Параллельный запуск фоновой задачи:
  - Либо через background tasks FastAPI
  - Либо через Celery (в перспективе)

#### Этап 2: Получение результатов

```http
GET /api/v1/check/{check_id}
```

Ответ при разных статусах:

- `pending` / `processing`:

```json
{
  "status": "processing",
  "progress": 40,
  "message": "Обработка 40% подписок..."
}
```

- `completed`:

```json
{
  "status": "completed",
  "progress": 100,
  "users": [
    {
      "username": "user123",
      "first_name": "John",
      "last_name": "Doe",
      "avatar": "https://...",
      "user_follows_target": true,
      "target_follows_user": false,
      "is_mutual": false
    }
  ],
  "total_subscriptions": 342,
  "total_non_mutual": 45,
  "file_path": "/data/checks/{check_id}.xlsx"
}
```

**Требования:**

- Polling механизм:
  - Интервал опроса: каждые 5 секунд
  - Максимальное время ожидания: например, 10 минут
- После получения `completed`:
  - Сохранить данные в БД (`non_mutual_users`)
  - Сгенерировать файл с таблицей (XLSX/CSV)
  - Обновить запись `checks`:
    - `status = completed`
    - `file_path`, `total_non_mutual`, `total_subscriptions`, `completed_at`
- В случае `failed`:
  - Сохранить сообщение об ошибке
  - Отправить пользователю понятный текст

---

### 3. Структура базы данных

#### Таблица `users` (Telegram-пользователи бота)

```sql
user_id: BigInt (PRIMARY KEY)          -- TG user ID
username: String                       -- TG username
first_name: String
last_name: String
phone: String (nullable)
avatar_file_id: String (nullable)
created_at: DateTime
updated_at: DateTime
is_active: Boolean
```

#### Таблица `checks` (проверки)

```sql
check_id: UUID (PRIMARY KEY)
user_id: BigInt (FOREIGN KEY → users.user_id)
target_username: String
platform: Enum('telegram', 'instagram')
status: Enum('pending', 'processing', 'completed', 'failed')
total_subscriptions: Int
total_non_mutual: Int
file_path: String (nullable)
file_type: Enum('csv', 'xlsx')
file_size: Int (nullable)
external_check_id: String (nullable)
error_message: String (nullable)
cache_used: Boolean (default false)
created_at: DateTime
completed_at: DateTime (nullable)
```

#### Таблица `non_mutual_users` (результаты по конкретной проверке)

```sql
id: UUID (PRIMARY KEY)
check_id: UUID (FOREIGN KEY → checks.check_id ON DELETE CASCADE)
target_user_id: String
target_username: String
target_first_name: String
target_last_name: String
target_avatar_url: String (nullable)
user_follows_target: Boolean
target_follows_user: Boolean
created_at: DateTime
```

---

### 4. Интеграция Telegram-бота (aiogram)

**Главные команды:**

- `/start` — регистрация/приветствие
- `/check` — запуск проверки, бот спрашивает:
  - Платформу: [Telegram] [Instagram]
  - Ник или ссылку на профиль
- `/my_checks` — история проверок пользователя
- `/help` — помощь

**Пример сценария:**

1. Пользователь: `/check`
2. Бот: "Выбери платформу: [Telegram] [Instagram]"
3. Пользователь нажимает `Instagram`
4. Бот: "Пришли ник или ссылку на профиль"
5. Пользователь: `@some_inst_user` или `https://instagram.com/some_inst_user`
6. Бот:
   - нормализует ник
   - вызывает `POST /api/v1/check/initiate`
   - получает `check_id`
   - отвечает:  
     "Запустил проверку для `@some_inst_user`. Это займет примерно 30–60 секунд. ID проверки: `xxxx`"
7. Бот начинает polling `GET /api/v1/check/{check_id}`.
8. При готовности — присылает файл с таблицей и короткую сводку.

---

### 5. Генерация файлов с результатами

**Требования к таблице:**

Колонки:

- `#` — порядковый номер
- `Username`
- `Имя`
- `Подписан на целевого?` (user_follows_target, ✓/✗)
- `Целевой подписан на него?` (target_follows_user, ✓/✗)
- `Взаимно?` (is_mutual, ✓/✗)

Пример:

| #  | Username | Имя  | Подписан на целевого? | Целевой подписан на него? | Взаимно? |
|----|----------|------|-----------------------|----------------------------|---------|
| 1  | user123  | John | ✓                     | ✗                          | ✗       |
| 2  | user456  | Jane | ✓                     | ✓                          | ✓       |

**Форматы:**

- MVP — `CSV` или `XLSX`
- Рекомендуется `XLSX`:
  - Через pandas + openpyxl
  - Возможность сделать условное форматирование (например, красный фон, если не взаимно)

**Метаданные в файле:**

- Заголовок: `Анализ взаимных подписок: @username (platform)`
- Дата проверки
- Кол-во подписок, не взаимных, процент

---

### 6. Обработка ошибок и edge cases

Обязательно продумать:

- Username не существует / профиль недоступен
- Аккаунт приватный (Instagram)
- Слишком много подписок (10k+)
- Превышен лимит внешнего API
- Внешний API не отвечает/падает

**Стратегия:**

- Retry с exponential backoff (3 попытки)
- Таймаут проверки (например, 10 минут)
- Понятные сообщения пользователю:
  - "Похоже, ваш аккаунт приватный, и мы не можем получить список подписок."
  - "Внешний сервис сейчас недоступен, попробуйте позже."

---

### 7. Безопасность и лимиты

- Rate limiting для пользователей бота:
  - Не более 5 проверок в сутки на одного Telegram user_id
- Хранить результаты не вечно:
  - Удалять проверки старше 30 дней
- Логи:
  - Не логировать чувствительные данные (пароли, токены)

---

### 8. Асинхронность и масштабируемость

MVP:

- FastAPI background tasks + APScheduler для периодических задач

Продвинуто:

- Celery + Redis для:
  - постановки задач проверки
  - мониторинга прогресса

Компоненты:

- FastAPI backend
- PostgreSQL
- Redis (для rate limiting и потенциально Celery)
- aiogram-бот как отдельный процесс

---

### 9. Мониторинг и логирование

- Логи:
  - INFO: успешные запросы, создание проверок
  - WARNING/ERROR: фейлы API, таймауты
- Метрики:
  - Среднее время проверки
  - Количество проверок в день
- Ошибки:
  - Интеграция с Sentry (по желанию)

---

## ЧАСТЬ 2. Спецификация Требований (Requirements Spec)

### 1. Обзор продукта

**Название:** Mutual Followers Analyzer (Telegram Bot + FastAPI Backend)

**Описание:**

Сервис позволяет пользователю через Telegram-бота проверить свои взаимные подписки по никнейму (Telegram или Instagram) и получить файл с теми, кто не подписан на него взаимно.

---

### 2. Функциональные требования (FR)

#### FR1: Инициация проверки

Пользователь отправляет ник/ссылку → создается запись проверки и возвращается `check_id`.

**Вход:**

- `user_id` (из Telegram)
- `username` (target_username)
- `platform` (`telegram` или `instagram`)

**Выход:**

- `check_id`
- `status` = `pending`
- `estimated_time`

Ошибки (пример):

- Невалидный username → 400
- Превышен rate-limit → 429
- Внешний API не доступен → 503/ошибка с описанием

---

#### FR2: Получение результатов по check_id

FastAPI endpoint:

```http
GET /api/v1/check/{check_id}
```

**Сценарии:**

- В процессе: вернуть `status = processing` и `progress`.
- Завершено: вернуть список пользователей, статистику и путь к файлу.
- Не найдено: 404.

---

#### FR3: Генерация и сохранение файла

На основании полученных пользователей формируется:

- DataFrame
- Сортировка по non-mutual
- Генерация XLSX
- Сохранение файла по пути `/data/checks/{check_id}.xlsx`
- Обновление записи `checks.file_path` и `file_size`

---

#### FR4: Интеграция с Telegram-ботом

- /check — запуск проверки:
  - спрашивает платформу
  - принимает ник
  - запускает FR1
- /my_checks — история проверок:
  - показывает последние N проверок
  - inline-кнопки "Открыть результат", "Удалить"
- /help — краткая документация

Бот должен уметь:

- отображать прогресс (например, сообщения вида: "Обработка 30%", "Готово")
- присылать файл результата

---

#### FR5: История проверок

Пользователь может получить список последних N проверок, с краткой информацией:

- `@username`, платформа
- дата проверки
- кол-во non-mutual

---

#### FR6: Кэширование

Если пользователь повторно проверяет тот же аккаунт на той же платформе менее чем через 24 часа:

- можно использовать уже сохраненные результаты
- опционально показать сообщение: "Результаты из кэша (проверка была X часов назад)"

---

### 3. Нефункциональные требования (NFR)

- Время ответа `POST /check/initiate` < 2 сек
- Время ответа `GET /check/{check_id}` (по БД) < 1 сек
- Время генерации XLSX < 5 сек (до 1000 строк)
- До 10 000 пользователей в одной проверке
- Rate-limit: 5 проверок / сутки / user_id
- Хранение данных: 30 дней, затем очистка

---

### 4. Архитектура системы (логическая)

Компоненты:

- **Telegram Bot (aiogram)** — принимает команды, дергает FastAPI.
- **FastAPI** — REST API:
  - `/api/v1/check/initiate`
  - `/api/v1/check/{check_id}`
  - `/api/v1/checks` — история проверок
- **PostgreSQL** — хранит пользователей бота, проверки и результаты.
- **Redis** — кэш и rate limiting.
- **Фоновый worker** (background tasks / APScheduler / Celery) — опрашивает внешний API и обновляет статусы.

---

### 5. Структура проекта (директории)

Рекомендуемая структура:

```text
mutual-followers-analyzer/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── router.py
│   ├── models/
│   │   ├── database.py
│   │   ├── schemas.py
│   ├── services/
│   │   ├── check_service.py
│   │   ├── file_generator.py
│   │   ├── external_api.py
│   │   ├── rate_limit.py
│   ├── bot/
│   │   ├── bot.py
│   │   ├── handlers/
│   │   │   ├── commands.py
│   │   │   ├── callbacks.py
│   ├── background/
│   │   ├── tasks.py
│   ├── utils/
│       ├── logger.py
│       ├── validators.py
├── data/
│   └── checks/
├── logs/
└── docs/
```

---

### 6. Технологический стек

- Python 3.11+
- FastAPI
- aiogram
- SQLAlchemy + PostgreSQL
- pandas + openpyxl (для XLSX)
- Docker + docker-compose
- Poetry для управления зависимостями

---

### 7. .env параметры

Пример:

```env
DEBUG=True
DATABASE_URL=postgresql://user:password@db:5432/mutual_followers
TELEGRAM_TOKEN=your_bot_token
EXTERNAL_API_URL=https://api.example.com
EXTERNAL_API_KEY=your_api_key
UPLOAD_DIR=./data/checks
MAX_CHECKS_PER_DAY=5
```

---

### 8. Docker Compose (схема)

Сервисы:

- `db` — PostgreSQL
- `redis` — Redis (опционально)
- `app` — FastAPI + background tasks
- `bot` — Telegram бот (aiogram)

---

### 9. Критерии приемки (Acceptance Criteria)

- `/check` создает проверку и возвращает пользователю сообщение с начатой проверкой.
- В течение разумного времени пользователь получает файл.
- История проверок доступна по `/my_checks`.
- Работа из Docker: `docker-compose up` поднимает полностью рабочую систему.

---

## Итого

Этот файл объединяет:

- Исследовательский промпт (что и как нужно изучить/уточнить)
- Формальные требования к проекту (что реализовать, какие endpoints, таблицы, поведение бота)

Дальше ты можешь:

1. Сохранить этот markdown в файл `mutual_followers_full_spec.md`.
2. Использовать его как:
   - ТЗ для себя
   - Документ для Deep Research/Claude/Perplexity и т.п.
   - Основание для генерации кода/boilerplate.
```