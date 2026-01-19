# Промпт для реализации интеграции Telegram Stars

## Контекст проекта

### 1. Описание проекта
Telegram-бот для анализа взаимных подписок в Instagram. Пользователи могут:
- Проверять аккаунты Instagram на невзаимные подписки
- Покупать пакеты проверок через Telegram Stars и Robokassa
- Приглашать друзей по реферальной программе
- Получать результаты в виде Excel-файлов

**Домен проекта:** `nofollowbot.parmenid.tech`  
**GitHub:** `https://github.com/MalikProtopopov/unfollower_bot`  
**Статус проекта:** Бета-версия (привлечение первых пользователей)

### 2. Технологический стек

**Backend:**
- Python 3.11
- FastAPI (REST API для бота и веб-хуков)
- SQLAlchemy + AsyncPG (асинхронная работа с PostgreSQL)
- Alembic (миграции БД)
- TaskIQ или Redis (для обработки задач с retry-механизмом)

**Telegram Bot:**
- aiogram 3.x (асинхронный фреймворк для Telegram Bot API)
- Telegram Bot API для обработки команд и callback-запросов

**Архитектура:**
- Bot → REST API Backend → БД
- Worker обрабатывает фоновые задачи через TaskIQ/Redis

---

## 3. Тарифы Telegram Stars (финальные цены)

**Пакеты проверок с фиксированными ценами в звёздах:**

| Пакет | Проверок | Цена звёзл | Стоимость за проверку |
|-------|----------|------------|----------------------|
| Маленький | 1 | 120 ⭐ | 120 ⭐ |
| Средний | 3 | 300 ⭐ | 100 ⭐ |
| Большой | 6 | 500 ⭐ | ~83 ⭐ |
| Огромный | 14 | 1000 ⭐ | ~71 ⭐ |

**Важно:**
- Цены только целые числа (звёзды не дробятся)
- Минимальная подписка: 100-150 звёзд
- Баланс пользователя хранится как целое число (Integer), не дробная часть
- Начисления проверок при платеже - целые числа (1, 3, 6, 14)

---

## 4. Архитектура платежей Telegram Stars

### Принцип работы

**Bot → REST API Backend → БД** (вместо Bot → прямо в БД)

**Поток:**
1. Пользователь нажимает кнопку "Оплатить Stars" в боте
2. Bot отправляет запрос в Backend API: `POST /api/v1/payments/telegram-stars/create`
3. API создаёт запись Payment в БД (status=PENDING) и возвращает payment_id
4. Bot отправляет инвойс через `bot.send_invoice()` с payload=payment_id
5. Пользователь оплачивает через встроенный интерфейс Telegram
6. Telegram отправляет события к боту: `pre_checkout_query` → `successful_payment`
7. Bot обрабатывает события локально (валидация), затем отправляет в API для финализации
8. API обновляет Payment (status=COMPLETED), начисляет проверки, логирует событие
9. Bot отправляет подтверждение пользователю
10. Система отправляет уведомление админу об успешной/неудачной оплате

---

## 5. Обновлённые модели данных (SQLAlchemy)

### Модель `Payment`

```python
class Payment(Base):
    __tablename__ = "payments"
    
    payment_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"))
    tariff_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("tariffs.tariff_id"), nullable=True)
    
    # Сумма платежа (Decimal для финансовых расчётов)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    
    # Количество проверок к начислению
    checks_count: Mapped[int] = mapped_column(Integer)
    
    # Валюта: RUB, XTR (Telegram Stars)
    currency: Mapped[str] = mapped_column(String(3))
    
    # Способ оплаты
    payment_method: Mapped[PaymentMethodEnum] = mapped_column(Enum(PaymentMethodEnum))
    
    # Статус платежа
    status: Mapped[PaymentStatusEnum] = mapped_column(Enum(PaymentStatusEnum))
    
    # Telegram Stars specific
    telegram_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Robokassa specific
    robokassa_invoice_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    robokassa_payment_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Отношения
    user: Mapped["User"] = relationship(back_populates="payments")
    tariff: Mapped[Optional["Tariff"]] = relationship()
    payment_events: Mapped[List["PaymentEvent"]] = relationship(back_populates="payment")
```

### Новая модель `PaymentEvent` (для аудита)

```python
class PaymentEvent(Base):
    __tablename__ = "payment_events"
    
    event_id: Mapped[UUID] = mapped_column(UUID, primary_key=True)
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("payments.payment_id"))
    
    # Тип события: CREATED, PROCESSING, COMPLETED, FAILED, CANCELLED
    event_type: Mapped[str] = mapped_column(String(50))
    
    # Статус до события
    status_before: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Статус после события
    status_after: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # Описание/детали события
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Ошибка (если была)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Когда произошло
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    
    # Связь
    payment: Mapped["Payment"] = relationship(back_populates="payment_events")
```

### Модель `Tariff` (обновлённая)

```python
class Tariff(Base):
    __tablename__ = "tariffs"
    
    tariff_id: Mapped[UUID] = mapped_column(UUID, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Количество проверок в пакете
    checks_count: Mapped[int] = mapped_column(Integer)
    
    # Цена в рублях (для Robokassa)
    price_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    
    # Цена в звёздах Telegram (целое число, обязательное)
    price_stars: Mapped[int] = mapped_column(Integer)  # 120, 300, 500, 1000
    
    # Активность
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Порядок сортировки в UI
    sort_order: Mapped[int] = mapped_column(Integer)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=datetime.now(timezone.utc))
```

---

## 6. REST API Endpoints (Backend)

### Создание платежа Telegram Stars
**Endpoint:** `POST /api/v1/payments/telegram-stars/create`

**Request:** `{ "user_id": 123456789, "tariff_id": "uuid-here" }`

**Response (200):**
```json
{
  "payment_id": "uuid",
  "user_id": 123456789,
  "tariff_id": "uuid",
  "amount": 120,
  "currency": "XTR",
  "checks_count": 1,
  "price_stars": 120,
  "payment_method": "TELEGRAM_STARS",
  "status": "PENDING",
  "created_at": "2026-01-19T23:07:00Z"
}
```

### Обработка успешного платежа (callback от бота)
**Endpoint:** `POST /api/v1/payments/telegram-stars/complete`

**Request:**
```json
{
  "payment_id": "uuid",
  "telegram_payment_charge_id": "123:456:789ABC",
  "total_amount": 120,
  "currency": "XTR"
}
```

**Response (200):**
```json
{
  "payment_id": "uuid",
  "status": "COMPLETED",
  "user_checks_balance": 25,
  "completed_at": "2026-01-19T23:10:00Z"
}
```

### Обработка ошибки платежа
**Endpoint:** `POST /api/v1/payments/telegram-stars/failed`

**Request:**
```json
{
  "payment_id": "uuid",
  "error_reason": "user_cancelled",
  "error_message": "Пользователь отменил платёж"
}
```

### Проверка статуса платежа
**Endpoint:** `GET /api/v1/payments/{payment_id}`

### История платежей пользователя
**Endpoint:** `GET /api/v1/payments/user/{user_id}?limit=50&offset=0&status=COMPLETED`

### История событий платежа (для администратора)
**Endpoint:** `GET /api/v1/payments/{payment_id}/events`

---

## 7. Обработчики Telegram Bot (aiogram 3.x)

### Callback обработчик для кнопки "Оплатить Stars"
```python
@router.callback_query(F.data.startswith("buy_tariff:"))
async def callback_buy_tariff(callback: CallbackQuery, ...):
    """
    Обработчик нажатия кнопки выбора тарифа и способа оплаты.
    
    Format: buy_tariff:{tariff_id}:stars
    
    Действия:
    1. Парсить callback.data и извлечь tariff_id и payment_type
    2. Вызвать GET /api/v1/tariffs/{tariff_id}
    3. Если Stars:
       - Вызвать POST /api/v1/payments/telegram-stars/create
       - Получить payment_id
       - Отправить инвойс через bot.send_invoice()
    """
```

### Обработчик pre_checkout_query
```python
@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout: PreCheckoutQuery, ...):
    """
    Валидация платежа перед оплатой.
    
    Действия:
    1. Извлечь payment_id из pre_checkout.invoice_payload
    2. Вызвать GET /api/v1/payments/{payment_id}
    3. Проверить: платеж существует, статус PENDING, сумма совпадает, валюта XTR
    4. Ответить bot.answer_pre_checkout_query(ok=True/False)
    """
```

### Обработчик successful_payment
```python
@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: Message, ...):
    """
    Обработка успешного платежа.
    
    Действия:
    1. Извлечь payment_id из message.successful_payment.invoice_payload
    2. Вызвать POST /api/v1/payments/telegram-stars/complete
    3. Если успех (200):
       - Отправить пользователю подтверждение
       - Отправить админу уведомление об оплате
    4. Если ошибка:
       - Логировать ошибку
       - Отправить сообщение об ошибке пользователю
       - Отправить админу alert
    """
```

---

## 8. Service Layer (Backend)

### PaymentService

```python
class PaymentService:
    """Бизнес-логика обработки платежей."""
    
    async def create_telegram_stars_payment(
        self,
        user_id: int,
        tariff_id: UUID,
        session: AsyncSession,
    ) -> PaymentResponse:
        """Создать платёж Telegram Stars."""
        # 1. Получить тариф и проверить его существование
        # 2. Создать запись Payment (status=PENDING)
        # 3. Логировать событие в payment_events
        # 4. Вернуть PaymentResponse
        
    async def complete_telegram_stars_payment(
        self,
        payment_id: UUID,
        telegram_charge_id: str,
        total_amount: int,
        session: AsyncSession,
    ) -> PaymentResponse:
        """Завершить платёж Telegram Stars."""
        # 1. Получить платёж из БД
        # 2. Проверить статус (идемпотентность)
        # 3. Проверить сумму
        # 4. Обновить статус на COMPLETED
        # 5. Начислить проверки пользователю
        # 6. Логировать событие в payment_events
        # 7. Вернуть обновлённый PaymentResponse
        
    async def fail_telegram_stars_payment(
        self,
        payment_id: UUID,
        error_reason: str,
        error_message: str,
        session: AsyncSession,
    ) -> PaymentResponse:
        """Отметить платёж как неудачный."""
```

---

## 9. Обработка ошибок и Retry-механизм (TaskIQ)

**При ошибке обновления БД в API:**

```python
@app.task
async def complete_payment_with_retry(
    payment_id: UUID,
    telegram_charge_id: str,
    total_amount: int,
    max_retries: int = 3,
):
    """Завершить платёж с автоматическим retry."""
    # Если fail → TaskIQ автоматически повторит задачу
    # Exponential backoff: 1s, 2s, 4s
```

**Идемпотентность:**
- Если платёж уже завершён с тем же charge_id → вернуть без изменений
- Если попытка обновить с другой суммой → ошибка

---

## 10. Уведомления Администратора

### События платежей для админа

**1. Успешный платёж Telegram Stars:**
```
💰 Новая оплата через Telegram Stars!

User: {user_id} (@{username})
Сумма: {amount} ⭐
Проверок: +{checks_count}
Новый баланс: {new_balance}
Дата: {completed_at}
```

**2. Неудачный платёж:**
```
⚠️ Ошибка при обработке платежа Telegram Stars

User: {user_id} (@{username})
Payment ID: {payment_id}
Причина: {error_reason}
Сообщение: {error_message}
```

---

## 11. Логирование и Аудит (PaymentEvent)

**Все важные события должны логироваться в таблицу `payment_events`:**

```python
async def log_payment_event(
    session: AsyncSession,
    payment_id: UUID,
    event_type: str,  # CREATED, PROCESSING, COMPLETED, FAILED, CANCELLED
    status_before: Optional[str],
    status_after: Optional[str],
    details: Optional[dict] = None,
    error_message: Optional[str] = None,
):
    """Логировать событие платежа в БД для аудита."""
```

**События:**
- `CREATED` - платёж создан
- `PRE_CHECKOUT` - запрос на подтверждение платежа
- `COMPLETED` - платёж успешно завершён
- `FAILED` - платёж не прошёл
- `RETRY_SCHEDULED` - запланирован retry
- `RETRY_EXECUTED` - retry выполнен

---

## 12. Unit-тесты и Integration-тесты

### Структура тестов

**Файлы:**
- `tests/unit/services/test_payment_service.py` - unit-тесты сервиса
- `tests/integration/api/test_payments_api.py` - интеграционные тесты API
- `tests/integration/bot/test_payment_handlers.py` - тесты обработчиков бота

### Примеры тестов

```python
@pytest.mark.asyncio
async def test_create_telegram_stars_payment(payment_service, user, tariff, session):
    """Тест создания платежа Telegram Stars."""
    payment = await payment_service.create_telegram_stars_payment(
        user_id=user.user_id,
        tariff_id=tariff.tariff_id,
        session=session,
    )
    
    assert payment.status == PaymentStatusEnum.PENDING
    assert payment.currency == "XTR"
    assert payment.amount == tariff.price_stars

@pytest.mark.asyncio
async def test_complete_telegram_stars_payment_idempotency(payment_service, payment, session):
    """Тест идемпотентности завершения платежа."""
    # Первый запрос
    result1 = await payment_service.complete_telegram_stars_payment(...)
    # Второй запрос с теми же данными
    result2 = await payment_service.complete_telegram_stars_payment(...)
    
    assert result1.payment_id == result2.payment_id
    assert result1.status == result2.status

@pytest.mark.asyncio
async def test_complete_payment_amount_mismatch(payment_service, payment, session):
    """Тест защиты от некорректной суммы."""
    with pytest.raises(PaymentAmountMismatchError):
        await payment_service.complete_telegram_stars_payment(
            payment_id=payment.payment_id,
            telegram_charge_id="123:456:789",
            total_amount=9999,  # Неверная сумма
            session=session,
        )
```

---

## 13. Миграция Alembic

**Файл:** `alembic/versions/xxx_add_telegram_stars_support.py`

Должна содержать:
1. Создание таблицы `payment_events` с полями
2. Добавление колонки `telegram_payment_charge_id` в таблицу `payments` (если её нет)
3. Убедиться, что поле `price_stars` в таблице `tariffs` существует и имеет тип INTEGER
4. Добавить индексы для оптимизации:
   - По `payment_id` в `payment_events`
   - По `telegram_payment_charge_id` в `payments`
   - По `status` в `payments`

---

## 14. Требования к реализации

### Обязательные требования

✅ **Асинхронность:** Весь код async/await, AsyncSession, httpx.AsyncClient

✅ **Type hints:** Все функции с параметрами и return type

✅ **Логирование:** Все важные события через logger

✅ **Обработка ошибок:** Try-except с логированием, специфичные исключения

✅ **Безопасность:** Валидация входных данных, проверка прав доступа, защита от SQL injection

✅ **Совместимость:** Интеграция с существующей Robokassa, не нарушение endpoints

✅ **Тестирование:** Unit + integration тесты

✅ **Документация:** Docstring для всех функций, примеры использования

### Файлы для реализации

**Backend API:**
1. `app/models/models.py` - обновить модели + PaymentEvent
2. `app/api/payments.py` - новые endpoints
3. `app/services/payment_service.py` - бизнес-логика
4. `app/tasks/payment_tasks.py` - TaskIQ tasks
5. `app/schemas/payments.py` - Pydantic schemas
6. `app/services/notification_service.py` - уведомления (обновить)

**Bot:**
1. `app/bot/handlers/payments.py` - обработчики платежей (новый файл)
2. `app/bot/main.py` - регистрация обработчиков

**Миграции:**
1. `alembic/versions/xxx_add_telegram_stars_support.py`

**Тесты:**
1. `tests/unit/services/test_payment_service.py`
2. `tests/integration/api/test_payments_api.py`
3. `tests/integration/bot/test_payment_handlers.py`

---

## 15. Порядок разработки (рекомендуемый)

1. ✅ Создать/обновить модели SQLAlchemy
2. ✅ Создать миграцию Alembic
3. ✅ Реализовать PaymentService (бизнес-логика)
4. ✅ Реализовать REST API endpoints
5. ✅ Реализовать обработчики бота (aiogram)
6. ✅ Реализовать NotificationService
7. ✅ Реализовать TaskIQ tasks
8. ✅ Написать unit-тесты
9. ✅ Написать integration-тесты
10. ✅ Написать тесты бота
11. ✅ Тестировать в test docker-compose
12. ✅ Развернуть в production

---

**Задача:** На основе этого промпта реализовать полную интеграцию Telegram Stars в систему платежей бота.
