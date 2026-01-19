# Диагностика проблем с реферальной программой

## Как проверить почему не начисляются приглашенные друзья:

### 1. Проверка через логи бота на сервере:

```bash
# Посмотреть логи бота при регистрации по реферальной ссылке
docker compose -f docker-compose.prod.yml --env-file .env.prod logs bot | grep -i referral

# Посмотреть логи backend API
docker compose -f docker-compose.prod.yml --env-file .env.prod logs backend | grep -i referral

# Посмотреть все логи за последние 10 минут
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --since 10m | grep -i referral
```

### 2. Проверка через базу данных:

```bash
# Подключиться к БД
docker compose -f docker-compose.prod.yml --env-file .env.prod exec postgres psql -U postgres mutual_followers

# Проверить таблицу referrals
SELECT * FROM referrals ORDER BY created_at DESC LIMIT 10;

# Проверить users с referral_code
SELECT user_id, username, referral_code FROM users WHERE referral_code IS NOT NULL LIMIT 10;

# Проверить кто кого пригласил
SELECT 
    r.referral_id,
    r.referrer_user_id as referrer_id,
    u1.username as referrer_username,
    r.referred_user_id as referred_id,
    u2.username as referred_username,
    r.bonus_granted,
    r.created_at
FROM referrals r
LEFT JOIN users u1 ON r.referrer_user_id = u1.user_id
LEFT JOIN users u2 ON r.referred_user_id = u2.user_id
ORDER BY r.created_at DESC
LIMIT 20;

# Проверить балансы пользователей
SELECT user_id, username, checks_balance, referral_code FROM users ORDER BY checks_balance DESC LIMIT 10;
```

### 3. Проверка через API (на сервере):

```bash
# Проверить статистику рефералов конкретного пользователя
curl -X GET "http://localhost:8000/api/v1/referrals/stats?user_id=YOUR_USER_ID"

# Проверить список рефералов
curl -X GET "http://localhost:8000/api/v1/referrals/list?user_id=YOUR_USER_ID"

# Проверить баланс пользователя
curl -X GET "http://localhost:8000/api/v1/users/YOUR_USER_ID/balance"
```

### 4. Возможные проблемы:

1. **Пользователь не существует в БД**
   - При регистрации по реферальной ссылке пользователь должен быть создан через `/users/ensure`
   - Проверьте логи: должна быть запись "Created new user" или "User ensured"

2. **Referral code не найден**
   - Код должен быть в формате `ref_123456789`
   - Проверьте что у реферера есть `referral_code` в БД

3. **Пользователь уже был приглашен ранее**
   - Система не позволяет менять реферера
   - Если пользователь уже регистрировался без реферальной ссылки, повторная регистрация не поможет

4. **Ошибка при регистрации реферала**
   - Проверьте логи backend на наличие ошибок
   - Ошибка может быть в `register_referral` функции

5. **Бонус не начислен**
   - Бонус начисляется только когда набирается 10 рефералов
   - Проверьте `bonus_granted` флаг в таблице referrals

### 5. Тестовая регистрация:

Для теста создайте нового пользователя (или используйте тестовый аккаунт Telegram):

1. Получите referral ссылку: `/referral` в боте
2. Используйте эту ссылку в другом Telegram аккаунте
3. Проверьте логи в реальном времени:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f bot backend
   ```
4. Затем проверьте в БД что referral записался

### 6. Проверка настроек:

```bash
# Проверить настройки реферальной программы в .env
grep REFERRAL .env.prod
```

Должны быть:
- `REFERRAL_REQUIRED_COUNT=10` (количество для бонуса)
- `REFERRAL_BONUS_CHECKS=1` (сколько проверок за бонус)

