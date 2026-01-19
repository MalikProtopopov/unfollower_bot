# Правильные URL для настройки Robokassa

## ⚠️ ВАЖНО: URL на скриншоте НЕПРАВИЛЬНЫЕ!

На скриншоте указаны:
- ❌ Result Url: `https://t.me/followcheckersbot`
- ❌ Success Url: `https://t.me/followcheckersbot`
- ❌ Fail Url: `https://t.me/followcheckersbot`

## ✅ Правильные URL:

### Result Url (Callback - обязательный):
```
https://ВАШ_ДОМЕН/api/v1/payments/robokassa/callback
```
**Метод:** POST (обязательно!)

**Примеры:**
- Если у вас есть домен: `https://api.yourdomain.com/api/v1/payments/robokassa/callback`
- Если используете ngrok: `https://abc123.ngrok.io/api/v1/payments/robokassa/callback`
- Для локальной разработки: используйте ngrok или другой туннель

### Success Url (после успешной оплаты):
```
https://ВАШ_ДОМЕН/api/v1/payments/robokassa/success
```
**Метод:** GET

### Fail Url (если оплата не удалась):
```
https://ВАШ_ДОМЕН/api/v1/payments/robokassa/fail
```
**Метод:** GET

## 🔧 Настройка для локальной разработки:

1. **Установите ngrok:**
   ```bash
   brew install ngrok  # macOS
   # или скачайте с https://ngrok.com
   ```

2. **Запустите туннель:**
   ```bash
   ngrok http 8080
   ```

3. **Скопируйте HTTPS URL** (например: `https://abc123.ngrok.io`)

4. **Используйте в Robokassa:**
   - Result Url: `https://abc123.ngrok.io/api/v1/payments/robokassa/callback`
   - Success Url: `https://abc123.ngrok.io/api/v1/payments/robokassa/success`
   - Fail Url: `https://abc123.ngrok.io/api/v1/payments/robokassa/fail`

## 📝 Пароли из скриншота:

- Password #1: `V204TEJgZyDbZptesPZ3` (для генерации URL оплаты)
- Password #2: `yU6ZEYJ4IgL375LriWYq` (для проверки callback)

**Добавьте их в `.env`:**
```bash
ROBOKASSA_PASSWORD_1=V204TEJgZyDbZptesPZ3
ROBOKASSA_PASSWORD_2=yU6ZEYJ4IgL375LriWYq
ROBOKASSA_MERCHANT_LOGIN=followcheckersbot
```

## ⚠️ ВАЖНО:

1. **Result Url ДОЛЖЕН быть доступен из интернета** (HTTPS обязательно!)
2. **Result Url ДОЛЖЕН принимать POST запросы**
3. Telegram бот НЕ может принимать POST запросы от Robokassa
4. Используйте ngrok или другой туннель для локальной разработки

