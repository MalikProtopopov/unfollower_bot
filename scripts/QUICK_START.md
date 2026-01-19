# Быстрый старт на сервере

## 🧹 Очистка старого проекта

```bash
./scripts/cleanup_server.sh
```

## 🚀 Настройка нового проекта

```bash
# 1. Загрузите проект на сервер
git clone <repo_url> check_follows
cd check_follows

# 2. Настройте проект
./scripts/setup_server.sh

# 3. Отредактируйте .env файл (если нужно)
nano .env
```

## 📋 Основные команды

```bash
# Запуск проекта
docker-compose up -d

# Остановка проекта
docker-compose down

# Просмотр логов
docker-compose logs -f

# Перезапуск
docker-compose restart

# Пересборка
docker-compose up --build -d

# Статус контейнеров
docker-compose ps
```

## ⚙️ Настройка .env

Минимально необходимые переменные:

```env
TELEGRAM_TOKEN=your_token
POSTGRES_PASSWORD=strong_password
INSTAGRAM_SESSION_ID=your_session_id
ADMIN_USER_IDS=123456789
```

Подробнее: [docs/SERVER_SETUP.md](../docs/SERVER_SETUP.md)

