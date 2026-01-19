# Промпт для доработки Telegram-бота анализа взаимных подписок

## Контекст проекта

Существующий проект: **Telegram-бот для анализа взаимных подписок Instagram** с FastAPI backend.

### Текущая архитектура:
- **Backend**: FastAPI + PostgreSQL + SQLAlchemy
- **Bot**: aiogram v3
- **Scraper**: Instagram GraphQL API (с session_id авторизацией)
- **Файлы**: XLSX отчёты с результатами проверок
- **Команды**: `/start`, `/check`, `/last`, `/help`

### Текущие модели БД:
- `users` - пользователи Telegram-бота
- `checks` - записи проверок (check_id, status, target_username, file_path)
- `non_mutual_users` - результаты проверки

---

## Задачи для доработки

### 1. Система покупки проверок и монетизация

#### 1.1 Баланс проверок у пользователя
- Добавить в модель `User` поле `checks_balance: int` (количество доступных проверок)
- При создании проверки списывать 1 проверку из баланса
- Если баланс = 0, блокировать создание новой проверки с сообщением о необходимости покупки

#### 1.2 Система тарифов/пакетов
Создать модель `Tariff`:
```python
- tariff_id: UUID
- name: str (например, "Базовый пакет")
- checks_count: int (количество проверок в пакете)
- price_rub: Decimal (цена в рублях)
- price_stars: int (цена в звездах Telegram, nullable)
- is_active: bool
- created_at: datetime
```

**Админ-управление тарифами:**
- API endpoint `POST /api/v1/admin/tariffs` - создание тарифа
- API endpoint `GET /api/v1/admin/tariffs` - список тарифов
- API endpoint `PUT /api/v1/admin/tariffs/{tariff_id}` - обновление
- API endpoint `DELETE /api/v1/admin/tariffs/{tariff_id}` - деактивация

**Временное решение:** Можно добавлять тарифы напрямую в БД через SQL или простой админ-эндпоинт.

#### 1.3 Интеграция с Робокассой (заготовка)
- Добавить модель `Payment`:
```python
- payment_id: UUID
- user_id: BigInt (FK → users)
- tariff_id: UUID (FK → tariffs, nullable)
- amount: Decimal
- currency: str (RUB)
- payment_method: Enum (ROBOKASSA, TELEGRAM_STARS)
- status: Enum (PENDING, COMPLETED, FAILED, CANCELLED)
- robokassa_invoice_id: str (nullable)
- robokassa_payment_url: str (nullable)
- created_at: datetime
- completed_at: datetime (nullable)
```

- API endpoints для Робокассы:
  - `POST /api/v1/payments/create` - создание платежа
  - `POST /api/v1/payments/robokassa/callback` - callback от Робокассы (webhook)
  - `GET /api/v1/payments/{payment_id}/status` - статус платежа

**Важно:** Пока не интегрируем реальную Робокассу, только структуру БД и API endpoints-заглушки.

#### 1.4 Оплата через Telegram Stars
- Использовать Telegram Stars API (aiogram поддерживает)
- Endpoint `POST /api/v1/payments/telegram-stars` - создание платежа через Stars
- Callback обработка успешной оплаты через Stars

#### 1.5 Команды бота для покупки
- `/buy` - показать доступные тарифы с кнопками покупки
- `/balance` - показать текущий баланс проверок
- Inline-кнопки для выбора тарифа и способа оплаты

---

### 2. Очередь задач для проверок

#### 2.1 Проблема
Сейчас проверки запускаются параллельно через FastAPI background tasks. Это может привести к:
- Блокировке Instagram аккаунта из-за слишком частых запросов
- Rate limiting от Instagram
- Перегрузке системы

#### 2.2 Решение: Очередь задач
Реализовать очередь проверок с последовательной обработкой.

**Варианты реализации:**
1. **Celery + Redis** (рекомендуется для продакшена)
2. **APScheduler** (проще для MVP)
3. **Простая очередь на PostgreSQL** (минималистичный вариант)

**Рекомендация для MVP:** Простая очередь на PostgreSQL + background worker.

#### 2.3 Модель очереди
Добавить в модель `Check`:
- `queue_position: int` - позиция в очереди
- `started_at: datetime` - когда началась обработка

Или создать отдельную модель `CheckQueue`:
```python
- queue_id: UUID
- check_id: UUID (FK → checks)
- position: int
- status: Enum (QUEUED, PROCESSING, COMPLETED, FAILED)
- created_at: datetime
```

#### 2.4 Worker для обработки очереди
- Отдельный процесс/сервис, который:
  - Берет следующую задачу из очереди (status = QUEUED)
  - Меняет статус на PROCESSING
  - Запускает проверку
  - После завершения берет следующую задачу

**Интеграция:**
- При создании проверки через `POST /check/initiate` - добавлять в очередь
- Worker обрабатывает по одной проверке за раз
- Можно добавить настройку `MAX_CONCURRENT_CHECKS = 1` в конфиг

---

### 3. Отложенные уведомления (Push notifications)

#### 3.1 Проблема
Долгие проверки (1000+ подписчиков) могут занимать 10-30 минут. Пользователь не должен ждать в боте.

#### 3.2 Решение
Система отложенных уведомлений через Telegram Bot API.

**Механизм:**
1. При создании проверки сохранять `user_id` и `check_id`
2. После завершения проверки (status = COMPLETED):
   - Отправить уведомление пользователю через `bot.send_message()`
   - Приложить файл с результатами через `bot.send_document()`
   - Показать статистику (подписчики, подписки, не взаимные)

#### 3.3 Реализация
В `check_service.py` после успешного завершения проверки:
```python
async def notify_user_on_completion(check_id: str):
    # Получить check из БД
    # Получить user_id
    # Отправить сообщение через bot.send_message()
    # Отправить файл через bot.send_document()
```

**Важно:** Нужен доступ к экземпляру бота из background task. Варианты:
- Общий экземпляр бота (singleton)
- Отдельный Telegram Bot API клиент для отправки уведомлений
- RabbitMQ/Redis для отправки задач на уведомления

**Рекомендация:** Использовать отдельный Telegram Bot API клиент (httpx/aiohttp) для отправки уведомлений из background task.

---

### 4. Реферальная программа

#### 4.1 Модель рефералов
Создать модель `Referral`:
```python
- referral_id: UUID
- referrer_user_id: BigInt (FK → users) - кто пригласил
- referred_user_id: BigInt (FK → users) - кого пригласили
- is_active: bool (пользователь зарегистрировался)
- created_at: datetime
```

Добавить в модель `User`:
- `referrer_user_id: BigInt` (nullable, FK → users) - кто пригласил этого пользователя
- `referral_code: str` - уникальный код для приглашения (например, user_id или UUID)

#### 4.2 Логика
- При регистрации пользователя (`/start`):
  - Проверять параметр `start_param` (если есть реферальная ссылка)
  - Сохранять связь referrer → referred
- При достижении 10 активных рефералов:
  - Автоматически начислять 1 проверку на баланс реферера
  - Отправлять уведомление о начислении

#### 4.3 Команды бота
- `/referral` - показать реферальную ссылку и статистику:
  - Количество приглашенных
  - Сколько осталось до следующей бесплатной проверки
  - Реферальная ссылка: `https://t.me/your_bot?start=REF{user_id}`

#### 4.4 API endpoints
- `GET /api/v1/referrals/stats?user_id=...` - статистика рефералов
- `GET /api/v1/referrals/list?user_id=...` - список рефералов

---

## Технические детали реализации

### База данных - новые таблицы

```sql
-- Тарифы
CREATE TABLE tariffs (
    tariff_id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    checks_count INTEGER NOT NULL,
    price_rub DECIMAL(10, 2) NOT NULL,
    price_stars INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Платежи
CREATE TABLE payments (
    payment_id UUID PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    tariff_id UUID REFERENCES tariffs(tariff_id),
    amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'RUB',
    payment_method VARCHAR(50) NOT NULL, -- ROBOKASSA, TELEGRAM_STARS
    status VARCHAR(20) NOT NULL, -- PENDING, COMPLETED, FAILED, CANCELLED
    robokassa_invoice_id VARCHAR(255),
    robokassa_payment_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Рефералы
CREATE TABLE referrals (
    referral_id UUID PRIMARY KEY,
    referrer_user_id BIGINT REFERENCES users(user_id),
    referred_user_id BIGINT REFERENCES users(user_id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(referred_user_id)
);

-- Очередь проверок (опционально, можно использовать поле в checks)
CREATE TABLE check_queue (
    queue_id UUID PRIMARY KEY,
    check_id UUID REFERENCES checks(check_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL, -- QUEUED, PROCESSING, COMPLETED, FAILED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE
);
```

### Обновление модели User

```python
class User(Base):
    # ... существующие поля ...
    checks_balance: Mapped[int] = mapped_column(Integer, default=0)
    referrer_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=True)
```

---

## Порядок реализации

### Этап 1: База данных и модели
1. Создать миграции Alembic для новых таблиц
2. Обновить модели SQLAlchemy
3. Обновить Pydantic schemas

### Этап 2: Система баланса и проверка доступа
1. Добавить проверку баланса при создании проверки
2. Обновить `/check` команду - проверять баланс перед запуском
3. Добавить команду `/balance`

### Этап 3: Очередь задач
1. Реализовать простую очередь на PostgreSQL
2. Создать worker для последовательной обработки
3. Обновить `check_service.py` для работы с очередью

### Этап 4: Отложенные уведомления
1. Создать сервис для отправки уведомлений
2. Интегрировать в `check_service.py` после завершения проверки
3. Протестировать отправку файлов через Bot API

### Этап 5: Тарифы и платежи (заготовка)
1. Создать модели Tariff и Payment
2. Создать API endpoints для тарифов (админ)
3. Создать API endpoints для платежей (заглушки)
4. Добавить команду `/buy` в бота

### Этап 6: Реферальная программа
1. Создать модель Referral
2. Обновить `/start` для обработки реферальных ссылок
3. Добавить команду `/referral`
4. Реализовать логику начисления проверок за 10 рефералов

---

## API Endpoints (новые)

### Платежи
- `POST /api/v1/payments/create` - создание платежа
- `GET /api/v1/payments/{payment_id}` - статус платежа
- `POST /api/v1/payments/robokassa/callback` - webhook от Робокассы
- `POST /api/v1/payments/telegram-stars` - оплата через Stars

### Тарифы
- `GET /api/v1/tariffs` - список активных тарифов
- `POST /api/v1/admin/tariffs` - создание тарифа (админ)
- `PUT /api/v1/admin/tariffs/{tariff_id}` - обновление тарифа
- `DELETE /api/v1/admin/tariffs/{tariff_id}` - деактивация тарифа

### Рефералы
- `GET /api/v1/referrals/stats?user_id=...` - статистика рефералов
- `GET /api/v1/referrals/list?user_id=...` - список рефералов

### Очередь
- `GET /api/v1/queue/status` - статус очереди
- `GET /api/v1/admin/queue` - управление очередью (админ)

---

## Команды бота (новые)

- `/balance` - показать баланс проверок
- `/buy` - показать тарифы и купить проверки
- `/referral` - реферальная программа (ссылка и статистика)
- `/admin` - админ-панель (если user_id в списке админов)

---

## Конфигурация

Добавить в `.env`:
```env
# Платежи
ROBOKASSA_MERCHANT_LOGIN=your_login
ROBOKASSA_PASSWORD_1=password1
ROBOKASSA_PASSWORD_2=password2
ROBOKASSA_TEST_MODE=True

# Очередь
MAX_CONCURRENT_CHECKS=1
QUEUE_PROCESSING_INTERVAL=5  # секунд

# Рефералы
REFERRAL_BONUS_CHECKS=1
REFERRAL_REQUIRED_COUNT=10

# Админы
ADMIN_USER_IDS=123456789,987654321
```

---

## Приоритеты реализации

1. **Высокий приоритет:**
   - Система баланса проверок
   - Очередь задач
   - Отложенные уведомления

2. **Средний приоритет:**
   - Реферальная программа
   - Команды `/balance`, `/buy`, `/referral`

3. **Низкий приоритет (заготовка):**
   - Интеграция с Робокассой (структура БД и API, без реальной интеграции)
   - Админ-панель для управления тарифами

---

## Важные замечания

1. **Очередь:** Обязательно реализовать, чтобы не блокировать Instagram аккаунт
2. **Уведомления:** Критично для UX - пользователи не должны ждать долгие проверки
3. **Баланс:** Простая проверка перед созданием проверки
4. **Платежи:** Пока только структура, реальную интеграцию делать отдельно
5. **Рефералы:** Автоматическое начисление при достижении 10 рефералов

---

## Тестирование

После реализации проверить:
1. Создание проверки при балансе = 0 (должна быть ошибка)
2. Очередь - проверки обрабатываются последовательно
3. Уведомление приходит после завершения проверки
4. Реферальная ссылка работает
5. Начисление проверок за 10 рефералов

