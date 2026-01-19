# 📌 ШПАРГАЛКА ROBOKASSA - БЫСТРЫЙ СПРАВОЧНИК

## ⚡ ФОРМУЛЫ (запомните!)

### Для ссылки на оплату:
```python
signature = MD5(MerchantLogin:OutSum:InvId:Password1:Shp_*).upper()
```

### Для callback:
```python
signature = MD5(OutSum:InvId:Password2:Shp_*).upper()
```

**Важно:** Shp_* параметры добавляются в алфавитном порядке!

## 🔗 ГЛАВНЫЕ URL

```
Платежная страница: https://auth.robokassa.ru/Merchant/Index.aspx
Result URL (callback): https://your-api.ru/api/v1/payments/robokassa/callback (POST)
Success URL: https://your-api.ru/api/v1/payments/robokassa/success (GET)
Fail URL: https://your-api.ru/api/v1/payments/robokassa/fail (GET)
```

## 📦 ПАРАМЕТРЫ URL

```
Обязательные:
- MerchantLogin=xxx
- OutSum=199.00 (ТОЧКА не запятая!)
- InvId=550e8400
- Description=text
- SignatureValue=abc123

Custom (вернутся в callback):
- Shp_payment_id=UUID
- Shp_user_id=123456
- Shp_tariff_id=UUID

Опциональные:
- IsTest=1 (тестовый режим)
- Culture=ru (язык)
- Encoding=utf-8
```

## 📨 ПАРАМЕТРЫ CALLBACK

```
OutSum, InvId, SignatureValue
Shp_payment_id, Shp_user_id, Shp_tariff_id
```

## ✅ ЧЕК-ЛИСТ ОБРАБОТКИ CALLBACK

```
1. ✓ Получить параметры из Form Data
2. ✓ Проверить подпись (ОБЯЗАТЕЛЬНО!)
3. ✓ Найти платеж по payment_id
4. ✓ Проверить что платеж еще не COMPLETED
5. ✓ Проверить что сумма совпадает
6. ✓ Обновить статус на COMPLETED
7. ✓ Начислить проверки на баланс
8. ✓ Уведомить админа
9. ✓ Уведомить пользователя
10. ✓ Вернуть OK{InvId}\n
```

## 🔒 БЕЗОПАСНОСТЬ

```
✓ HTTPS для Result URL
✓ Всегда проверять подпись
✓ Проверять idempotency (статус != COMPLETED)
✓ Проверять сумму платежа
✓ Логировать все платежи
✓ Password #1 и #2 только в .env
```

## 🧪 ТЕСТОВАЯ КАРТА

```
Номер: 4111111111111111
Срок: 12/25
CVV: 123
Имя: TEST TEST
```

## 🐛 САМЫЕ ЧАСТЫЕ ОШИБКИ

```
❌ Password #1 вместо #2 в callback
❌ HTTP вместо HTTPS для Result URL (в production)
❌ Забыли Shp_payment_id в ссылке
❌ Неправильный формат ответа (должен быть OK{InvId}\n)
❌ Нет проверки подписи
❌ OutSum с запятой вместо точки
❌ Обработка платежа дважды
❌ Неправильный порядок Shp_* параметров в подписи
```

## 📝 ИСПОЛЬЗОВАНИЕ В ПРОЕКТЕ

### Генерация URL оплаты:
```python
from app.utils.robokassa import generate_payment_url

url = generate_payment_url(
    merchant_login="followcheckersbot",
    password_1="your_password_1",
    inv_id=str(payment.payment_id),
    out_sum=Decimal("199.00"),
    description="Пакет '10 проверок' - 10 проверок",
    user_id=123456789,
    tariff_id=str(tariff.tariff_id),
    test_mode=True,
)
```

### Проверка подписи callback:
```python
from app.utils.robokassa import verify_callback_signature

shp_params = {
    "Shp_payment_id": payment_id,
    "Shp_tariff_id": tariff_id,
    "Shp_user_id": str(user_id),
}

is_valid = verify_callback_signature(
    out_sum=OutSum,
    inv_id=InvId,
    signature=SignatureValue,
    password_2="your_password_2",
    shp_params=shp_params,
)
```

### Формирование ответа:
```python
from app.utils.robokassa import format_callback_response

return format_callback_response(InvId)  # "OK{InvId}\n"
```

## 🔧 НАСТРОЙКИ В .env

```bash
ROBOKASSA_MERCHANT_LOGIN=followcheckersbot
ROBOKASSA_PASSWORD_1=your_password_1_here
ROBOKASSA_PASSWORD_2=your_password_2_here
ROBOKASSA_TEST_MODE=true
```

## 🔗 ПОЛЕЗНЫЕ ССЫЛКИ

- [Документация Robokassa](https://docs.robokassa.ru)
- [Примеры кода](https://docs.robokassa.ru/code-examples/)
- [Тестовый режим](https://docs.robokassa.ru/test-mode/)
- [Личный кабинет](https://partner.robokassa.ru/)

## 📊 СХЕМА ВЗАИМОДЕЙСТВИЯ

```
User → Bot: Нажимает "Купить"
Bot → API: POST /payments/create
API → DB: Создает Payment (PENDING)
API → Bot: payment_url
Bot → User: Кнопка "Оплатить"
User → Robokassa: Переход по ссылке
User → Robokassa: Оплата картой
Robokassa → API: POST /payments/robokassa/callback
API: Проверка подписи (Password2)
API → DB: Payment → COMPLETED
API → DB: User.checks_balance += N
API → Admin: Уведомление о платеже
API → User: Уведомление об успехе
API → Robokassa: OK{InvId}
Robokassa → User: Редирект на Success URL
```

