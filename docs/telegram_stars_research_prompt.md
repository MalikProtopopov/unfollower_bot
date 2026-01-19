# Промпт для исследования интеграции Telegram Stars

## Контекст проекта

### 1. Описание проекта
Telegram-бот для анализа взаимных подписок в Instagram. Пользователи могут:
- Проверять аккаунты Instagram на невзаимные подписки
- Покупать пакеты проверок через различные способы оплаты
- Приглашать друзей по реферальной программе
- Получать результаты в виде Excel-файлов

**Домен проекта:** `nofollowbot.parmenid.tech`  
**GitHub:** `https://github.com/MalikProtopopov/unfollower_bot`

### 2. Технологический стек

**Backend:**
- Python 3.11
- FastAPI (REST API для бота и веб-хуков)
- SQLAlchemy + AsyncPG (асинхронная работа с PostgreSQL)
- Alembic (миграции БД)

**Telegram Bot:**
- aiogram 3.x (асинхронный фреймворк для Telegram Bot API)
- Telegram Bot API для обработки команд и callback-запросов

**Инфраструктура:**
- Docker & Docker Compose для деплоя
- PostgreSQL (база данных)
- Nginx (reverse proxy с SSL)
- Redis (для очередей, опционально)

**Архитектура:**
- Разделение на микросервисы: `backend`, `bot`, `worker`
- Backend предоставляет REST API
- Bot обрабатывает команды пользователей
- Worker обрабатывает фоновые задачи (очередь проверок)

### 3. Текущая реализация платежей

#### 3.1 Модели данных (SQLAlchemy)

**Модель `Payment`:**
```python
class Payment(Base):
    payment_id: UUID (primary key)
    user_id: BigInteger (FK → users.user_id)
    tariff_id: UUID (FK → tariffs.tariff_id, nullable)
    amount: Decimal (сумма платежа)
    currency: String(3) (RUB, XTR для Stars)
    checks_count: Integer (количество проверок)
    payment_method: Enum (ROBOKASSA, TELEGRAM_STARS, MANUAL)
    status: Enum (PENDING, COMPLETED, FAILED, CANCELLED)
    telegram_payment_charge_id: String(255, nullable)  # ID платежа Telegram Stars
    robokassa_invoice_id: String(255, nullable)
    robokassa_payment_url: Text(nullable)
    created_at: DateTime
    completed_at: DateTime (nullable)
```

**Модель `Tariff`:**
```python
class Tariff(Base):
    tariff_id: UUID (primary key)
    name: String(255)
    description: Text (nullable)
    checks_count: Integer (количество проверок в пакете)
    price_rub: Decimal (цена в рублях)
    price_stars: Integer (nullable)  # Цена в Telegram Stars
    is_active: Boolean
    sort_order: Integer
    created_at: DateTime
    updated_at: DateTime
```

#### 3.2 API Endpoints (FastAPI)

**Существующие endpoints:**

1. `POST /api/v1/payments/create` - создание платежа
   - Принимает: `user_id`, `tariff_id`, `payment_method`
   - Возвращает: `PaymentResponse` с деталями платежа
   - Для Robokassa: возвращает `robokassa_payment_url`
   - Для Telegram Stars: **требует реализации** - должен возвращать данные для инициации платежа через Telegram Bot API

2. `POST /api/v1/payments/robokassa/callback` - webhook от Robokassa
   - Проверяет подпись
   - Обновляет статус платежа
   - Начисляет проверки на баланс пользователя
   - Отправляет уведомления

3. `GET /api/v1/payments/{payment_id}` - статус платежа

4. `POST /api/v1/payments/complete/{payment_id}` - ручное завершение платежа (для тестов)

5. `GET /api/v1/payments/user/{user_id}/history` - история платежей

**Что нужно добавить для Telegram Stars:**
- `POST /api/v1/payments/telegram-stars/callback` - webhook для обработки успешных платежей Stars
- Или использовать встроенный механизм aiogram для обработки `pre_checkout_query` и `successful_payment`

#### 3.3 Обработка в боте (aiogram 3.x)

**Текущая реализация:**

В файле `app/bot/handlers/commands.py`:
- Команда `/buy` показывает список тарифов
- Inline-кнопки для выбора тарифа и способа оплаты (`buy_tariff:{tariff_id}:stars` или `buy_tariff:{tariff_id}:rub`)
- Callback-обработчик `callback_buy_tariff` - **сейчас заглушка**, показывает сообщение "в разработке"

**Структура обработки:**
```python
@router.callback_query(F.data.startswith("buy_tariff:"))
async def callback_buy_tariff(callback: CallbackQuery):
    # Parse: buy_tariff:{tariff_id}:{payment_type}
    # payment_type = 'stars' or 'rub'
    # TODO: Implement actual payment flow
```

### 4. Что нужно реализовать

#### 4.1 Функционал для Telegram Stars

1. **Создание инвойса через Telegram Bot API**
   - При нажатии кнопки "Оплатить Stars" → создать платеж через `sendInvoice` метод Bot API
   - Использовать данные тарифа: `price_stars`, описание, количество проверок
   - Сохранить `payment_id` локально для связи с записью в БД

2. **Обработка `pre_checkout_query`**
   - Валидация платежа перед оплатой
   - Проверка наличия тарифа и актуальности цены
   - Ответить `answerPreCheckoutQuery` с `ok=True` или `error`

3. **Обработка `successful_payment`**
   - Получить данные платежа: `telegram_payment_charge_id`, `total_amount`, `invoice_payload`
   - Найти запись `Payment` в БД (по `payment_id` из `invoice_payload` или другим способом)
   - Обновить статус платежа на `COMPLETED`
   - Начислить проверки на баланс пользователя (`user.checks_balance += payment.checks_count`)
   - Отправить подтверждение пользователю

4. **Обработка ошибок и отмены**
   - Обработка `pre_checkout_query` с ошибками
   - Логирование неудачных попыток оплаты

#### 4.2 Интеграция с aiogram 3.x

**Handlers для aiogram:**

```python
# Обработка pre-checkout запроса
@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout: PreCheckoutQuery):
    # Валидация платежа
    # answer_pre_checkout_query()

# Обработка успешного платежа
@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: Message):
    # Обновление БД, начисление проверок
    # Отправка уведомления пользователю
```

#### 4.3 Связь между Bot API и Backend API

**Варианты архитектуры:**

**Вариант 1 (рекомендуемый):** Bot напрямую работает с БД и обрабатывает платежи
- Проще реализация
- Меньше запросов между сервисами
- Bot имеет доступ к сессии SQLAlchemy

**Вариант 2:** Bot вызывает Backend API
- Более строгое разделение ответственности
- Требует HTTP-запросы между bot и backend

**Рекомендация:** Использовать Вариант 1, так как:
- Bot уже имеет доступ к базе данных через `get_session()`
- Платежи Stars синхронные (мгновенные), не требуют webhook как Robokassa
- Меньше точек отказа

### 5. Технические детали Telegram Stars API

#### 5.1 Метод `sendInvoice`

**Параметры:**
- `chat_id` - ID чата (user_id)
- `title` - название товара (напр., "Пакет проверок: 10 проверок")
- `description` - описание (напр., "Получите 10 проверок для анализа аккаунтов Instagram")
- `payload` - уникальный идентификатор заказа (можно использовать `payment_id` как UUID строку)
- `provider_token` - **НЕ ТРЕБУЕТСЯ для Telegram Stars** (только для внешних платежных систем)
- `currency` - валюта: `"XTR"` для Telegram Stars
- `prices` - список объектов `LabeledPrice`:
  ```python
  [LabeledPrice(label="10 проверок", amount=100)]  # amount в звездах (100 = 1 звезда в минимальных единицах)
  ```
- `max_tip_amount` - опционально, максимальная сумма чаевых
- `suggested_tip_amounts` - опционально, предложенные суммы чаевых
- `start_parameter` - опционально, параметр для deep linking
- `provider_data` - опционально, дополнительные данные
- `photo_url` - опционально, URL фото
- `photo_size` - опционально, размер фото
- `photo_width` - опционально, ширина фото
- `photo_height` - опционально, высота фото
- `need_name` - запрашивать имя
- `need_phone_number` - запрашивать телефон
- `need_email` - запрашивать email
- `need_shipping_address` - запрашивать адрес доставки
- `send_phone_number_to_provider` - отправлять телефон провайдеру
- `send_email_to_provider` - отправлять email провайдеру
- `is_flexible` - гибкая цена доставки
- `disable_notification` - не отправлять уведомление
- `protect_content` - защита контента
- `reply_to_message_id` - ID сообщения для ответа
- `allow_sending_without_reply` - разрешить отправку без ответа
- `reply_markup` - клавиатура (обычно не нужна для invoice)

**Важно:** Для Telegram Stars `provider_token` не используется (оставить пустым или не передавать).

#### 5.2 Обработка `PreCheckoutQuery`

**Метод `answerPreCheckoutQuery`:**
- `pre_checkout_query_id` - ID запроса
- `ok` - `True` если все ОК, `False` если ошибка
- `error_message` - сообщение об ошибке (если `ok=False`)

**Что проверять:**
- Существует ли платеж в БД
- Не завершен ли уже платеж (idempotency)
- Соответствует ли сумма тарифу
- Активен ли тариф

#### 5.3 Обработка `Message` с `successful_payment`

**Структура `message.successful_payment`:**
- `currency` - валюта ("XTR")
- `total_amount` - общая сумма в минимальных единицах (100 = 1 звезда)
- `invoice_payload` - payload, переданный в `sendInvoice` (наш `payment_id`)
- `telegram_payment_charge_id` - уникальный ID платежа от Telegram
- `provider_payment_charge_id` - для внешних провайдеров (для Stars обычно пусто)
- `shipping_option_id` - для доставки (не используется)
- `order_info` - информация о заказе (если запрашивали)

**Действия после получения:**
1. Извлечь `payment_id` из `invoice_payload`
2. Найти запись `Payment` в БД
3. Проверить, что платеж еще не обработан (status != COMPLETED)
4. Обновить:
   - `status = COMPLETED`
   - `telegram_payment_charge_id = successful_payment.telegram_payment_charge_id`
   - `completed_at = datetime.now()`
5. Начислить проверки: `user.checks_balance += payment.checks_count`
6. Отправить подтверждение пользователю
7. Сохранить изменения в БД

### 6. Текущая структура файлов проекта

```
app/
├── api/
│   ├── payments.py          # REST API для платежей (Robokassa уже реализован)
│   ├── router.py            # Основные API endpoints
│   └── tariffs.py           # API для управления тарифами
├── bot/
│   ├── handlers/
│   │   └── commands.py      # Обработчики команд бота (TODO: реализовать Stars)
│   └── main.py              # Точка входа бота
├── models/
│   ├── models.py            # SQLAlchemy модели (Payment, Tariff уже есть)
│   └── schemas.py           # Pydantic схемы для API
├── services/
│   ├── notification_service.py  # Отправка уведомлений пользователям
│   └── ...
├── config.py                # Настройки приложения
└── ...
```

### 7. Примеры кода (заготовки)

#### 7.1 Отправка инвойса (aiogram)

```python
from aiogram.types import LabeledPrice
from aiogram import Bot

async def send_stars_invoice(
    bot: Bot,
    user_id: int,
    tariff: Tariff,
    payment_id: UUID,
):
    """Отправить инвойс для оплаты через Telegram Stars."""
    prices = [
        LabeledPrice(
            label=f"{tariff.checks_count} проверок",
            amount=tariff.price_stars * 100,  # Конвертация в минимальные единицы
        )
    ]
    
    await bot.send_invoice(
        chat_id=user_id,
        title=f"Пакет проверок: {tariff.name}",
        description=tariff.description or f"Получите {tariff.checks_count} проверок",
        payload=str(payment_id),  # Используем payment_id как payload
        currency="XTR",  # Telegram Stars
        prices=prices,
        # provider_token не нужен для Stars
    )
```

#### 7.2 Обработка pre-checkout

```python
from aiogram.types import PreCheckoutQuery

@router.pre_checkout_query()
async def process_pre_checkout_query(
    pre_checkout: PreCheckoutQuery,
    session: Annotated[AsyncSession, Depends(get_session)],
    bot: Bot,
):
    """Обработать запрос на подтверждение платежа."""
    payment_id_str = pre_checkout.invoice_payload
    try:
        payment_id = UUID(payment_id_str)
    except ValueError:
        await bot.answer_pre_checkout_query(
            pre_checkout_query_id=pre_checkout.id,
            ok=False,
            error_message="Неверный идентификатор платежа",
        )
        return
    
    # Найти платеж в БД
    result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_id)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        await bot.answer_pre_checkout_query(
            pre_checkout_query_id=pre_checkout.id,
            ok=False,
            error_message="Платеж не найден",
        )
        return
    
    if payment.status == PaymentStatusEnum.COMPLETED:
        await bot.answer_pre_checkout_query(
            pre_checkout_query_id=pre_checkout.id,
            ok=False,
            error_message="Платеж уже был обработан",
        )
        return
    
    # Проверить сумму
    expected_amount = payment.amount * 100  # В минимальных единицах
    if pre_checkout.total_amount != expected_amount:
        await bot.answer_pre_checkout_query(
            pre_checkout_query_id=pre_checkout.id,
            ok=False,
            error_message="Сумма платежа не совпадает",
        )
        return
    
    # Все проверки пройдены
    await bot.answer_pre_checkout_query(
        pre_checkout_query_id=pre_checkout.id,
        ok=True,
    )
```

#### 7.3 Обработка успешного платежа

```python
from aiogram.types import Message, ContentType

@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(
    message: Message,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Обработать успешный платеж через Telegram Stars."""
    payment_data = message.successful_payment
    payment_id_str = payment_data.invoice_payload
    
    try:
        payment_id = UUID(payment_id_str)
    except ValueError:
        logger.error(f"Invalid payment_id in successful_payment: {payment_id_str}")
        await message.answer("❌ Ошибка обработки платежа. Обратитесь в поддержку.")
        return
    
    # Найти платеж
    result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_id)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        logger.error(f"Payment not found: {payment_id}")
        await message.answer("❌ Платеж не найден. Обратитесь в поддержку.")
        return
    
    # Проверка idempotency
    if payment.status == PaymentStatusEnum.COMPLETED:
        logger.warning(f"Payment {payment_id} already completed")
        await message.answer(
            "✅ Этот платеж уже был обработан ранее.\n\n"
            f"Ваш баланс: {payment.user.checks_balance} проверок"
        )
        return
    
    # Обновить платеж
    payment.status = PaymentStatusEnum.COMPLETED
    payment.telegram_payment_charge_id = payment_data.telegram_payment_charge_id
    payment.completed_at = datetime.now(timezone.utc)
    
    # Начислить проверки
    user_result = await session.execute(
        select(User).where(User.user_id == payment.user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if user:
        old_balance = user.checks_balance
        user.checks_balance += payment.checks_count
        
        await session.commit()
        
        logger.info(
            f"Stars payment completed: {payment_id}, "
            f"user {user.user_id}, +{payment.checks_count} checks, "
            f"balance: {old_balance} -> {user.checks_balance}"
        )
        
        # Уведомление пользователю
        await message.answer(
            f"✅ <b>Оплата успешно получена!</b>\n\n"
            f"Сумма: {payment.amount} ⭐\n"
            f"Начислено проверок: {payment.checks_count}\n"
            f"Ваш баланс: {user.checks_balance} проверок\n\n"
            f"Теперь вы можете использовать команду /check для проверки аккаунтов."
        )
        
        # Уведомление админу
        await notify_admin(
            f"💰 Новая оплата через Stars!\n\n"
            f"User: {user.user_id} (@{user.username or 'N/A'})\n"
            f"Сумма: {payment.amount} ⭐\n"
            f"Проверок: +{payment.checks_count}\n"
            f"Новый баланс: {user.checks_balance}"
        )
    else:
        logger.error(f"User {payment.user_id} not found for payment {payment_id}")
        await session.rollback()
        await message.answer("❌ Ошибка обработки платежа. Обратитесь в поддержку.")
```

### 8. Вопросы для исследования

1. **Конвертация цены:**
   - Правильно ли множить `price_stars` на 100 для получения минимальных единиц?
   - Или Stars всегда в целых числах?

2. **Idempotency:**
   - Может ли Telegram отправить `successful_payment` дважды?
   - Как обеспечить безопасную обработку повторных запросов?

3. **Обработка ошибок:**
   - Что делать, если платеж прошел, но не удалось обновить БД?
   - Нужен ли механизм повторной обработки?

4. **Тестирование:**
   - Как тестировать Telegram Stars в тестовом режиме?
   - Есть ли тестовые боты или специальные условия?

5. **Лимиты и ограничения:**
   - Есть ли лимиты на суммы платежей через Stars?
   - Требования к описанию товара?

6. **Совместимость с aiogram 3.x:**
   - Какие методы использовать для отправки инвойса?
   - Как правильно обработать `pre_checkout_query` и `successful_payment`?

7. **Безопасность:**
   - Нужно ли проверять подпись платежа (как в Robokassa)?
   - Как защититься от подделки `invoice_payload`?

### 9. Ожидаемый результат исследования

**Документ должен содержать:**
1. Пошаговую инструкцию по интеграции Telegram Stars
2. Полный код обработчиков для aiogram 3.x
3. Обновления в существующие файлы (если нужны)
4. Примеры тестирования
5. Ответы на вопросы выше
6. Рекомендации по безопасности и обработке ошибок
7. Описание edge cases и их обработки

### 10. Дополнительные требования

- Код должен быть асинхронным (async/await)
- Использовать типизацию (type hints)
- Логирование всех важных событий через `logger`
- Обработка всех возможных ошибок
- Сохранение совместимости с существующим кодом
- Соответствие стилю кода проекта (Black, isort)

---

**Задача:** Изучить документацию Telegram Bot API для Stars и aiogram 3.x, подготовить полную реализацию функционала покупки через Telegram Stars, интегрированную с существующей системой платежей проекта.

