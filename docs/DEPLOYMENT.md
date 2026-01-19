# Инструкция по развертыванию на удаленном сервере

## Предварительные требования

На сервере должны быть установлены:
- **Git** - для клонирования репозитория
- **Docker** - версия 20.10 или выше
- **Docker Compose** - версия 2.0 или выше

Проверка установки:
```bash
git --version
docker --version
docker-compose --version
# или для новых версий
docker compose version
```

## Шаг 1: Подключение к серверу

Подключитесь к серверу по SSH:
```bash
ssh user@your-server-ip
# или
ssh user@your-domain.com
```

## Шаг 2: Очистка старого проекта (если нужно)

Если на сервере был другой проект и нужно его удалить:

### Вариант 1: Использование скрипта (после клонирования)

```bash
# После клонирования проекта (см. Шаг 3)
cd unfollower_bot
chmod +x scripts/cleanup_server.sh
./scripts/cleanup_server.sh
```

### Вариант 2: Ручная очистка

```bash
# Остановить все контейнеры
docker stop $(docker ps -aq) 2>/dev/null || true

# Удалить все контейнеры
docker rm $(docker ps -aq) 2>/dev/null || true

# Удалить все образы
docker rmi $(docker images -q) 2>/dev/null || true

# Очистить неиспользуемые ресурсы
docker system prune -af --volumes

# Удалить неиспользуемые сети
docker network prune -f
```

## Шаг 3: Клонирование проекта

### 3.1. Выберите директорию для проекта

```bash
# Перейдите в домашнюю директорию или создайте директорию для проектов
cd ~
# или
mkdir -p ~/projects
cd ~/projects
```

### 3.2. Клонируйте репозиторий

```bash
git clone https://github.com/MalikProtopopov/unfollower_bot.git
```

Или если используете SSH ключ:
```bash
git clone git@github.com:MalikProtopopov/unfollower_bot.git
```

### 3.3. Перейдите в директорию проекта

```bash
cd unfollower_bot
```

## Шаг 4: Настройка переменных окружения

### 4.1. Создайте файл .env

```bash
cp env.example .env
```

### 4.2. Отредактируйте .env файл

```bash
nano .env
# или
vim .env
# или используйте любой другой редактор
```

### 4.3. Настройте обязательные переменные

Минимально необходимые переменные:

```env
# Telegram Bot Token (получить у @BotFather)
TELEGRAM_TOKEN=your_telegram_bot_token_here

# PostgreSQL (ОБЯЗАТЕЛЬНО измените пароль!)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=strong_secure_password_here
POSTGRES_DB=mutual_followers

# Instagram Session ID (для авторизованных запросов)
INSTAGRAM_SESSION_ID=your_session_id_here

# Admin Bot Token (если используется отдельный бот для админов)
ADMIN_BOT_TOKEN=your_admin_bot_token_here

# Admin User IDs (через запятую, без пробелов)
ADMIN_USER_IDS=123456789,987654321

# Bot Username (без @)
BOT_USERNAME=your_bot_username

# Manager Username (для поддержки пользователей)
MANAGER_USERNAME=issue_resolver
```

**Важно:** 
- Обязательно измените `POSTGRES_PASSWORD` на надежный пароль!
- Не коммитьте `.env` файл в Git (он уже в .gitignore)

## Шаг 5: Запуск проекта

### Вариант 1: Использование скрипта автоматической настройки (рекомендуется)

```bash
# Сделайте скрипт исполняемым
chmod +x scripts/setup_server.sh

# Запустите настройку
./scripts/setup_server.sh
```

Скрипт автоматически:
- Проверит наличие Docker и Docker Compose
- Создаст необходимые директории
- Соберет и запустит контейнеры
- Применит миграции базы данных

### Вариант 2: Ручной запуск

```bash
# Создайте необходимые директории
mkdir -p data/checks logs

# Соберите образы
docker-compose build
# или для новых версий Docker
docker compose build

# Запустите контейнеры в фоновом режиме
docker-compose up -d
# или
docker compose up -d

# Примените миграции базы данных
docker-compose exec app alembic upgrade head
# или
docker compose exec app alembic upgrade head
```

## Шаг 6: Проверка работы

### 6.1. Проверьте статус контейнеров

```bash
docker-compose ps
# или
docker compose ps
```

Должны быть запущены 4 сервиса:
- `mutual_followers_db` - база данных
- `mutual_followers_app` - FastAPI приложение
- `mutual_followers_bot` - Telegram бот
- `mutual_followers_worker` - воркер для обработки очереди

### 6.2. Проверьте логи

```bash
# Все сервисы
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f app
docker-compose logs -f bot
docker-compose logs -f worker

# Последние 100 строк
docker-compose logs --tail=100 app
```

### 6.3. Проверьте доступность API

```bash
# Если есть доступ к серверу извне
curl http://localhost:8080/docs

# Или проверьте изнутри контейнера
docker-compose exec app curl http://localhost:8000/docs
```

## Шаг 7: Настройка автозапуска (опционально)

### 7.1. Использование systemd (для Linux)

Создайте файл `/etc/systemd/system/unfollower-bot.service`:

```ini
[Unit]
Description=Unfollower Bot Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/user/unfollower_bot
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Активируйте сервис:
```bash
sudo systemctl daemon-reload
sudo systemctl enable unfollower-bot.service
sudo systemctl start unfollower-bot.service
```

### 7.2. Использование cron для автоматического перезапуска

Добавьте в crontab (`crontab -e`):
```bash
# Перезапуск каждый день в 3:00
0 3 * * * cd /home/user/unfollower_bot && docker-compose restart
```

## Управление проектом

### Остановка проекта

```bash
docker-compose down
```

### Перезапуск проекта

```bash
docker-compose restart
```

### Пересборка после изменений

```bash
# Остановить, пересобрать и запустить
docker-compose down
docker-compose build
docker-compose up -d

# Или одной командой
docker-compose up --build -d
```

### Обновление проекта

```bash
# Перейти в директорию проекта
cd ~/unfollower_bot

# Получить последние изменения
git pull origin main

# Пересобрать и перезапустить
docker-compose down
docker-compose build
docker-compose up -d

# Применить новые миграции (если есть)
docker-compose exec app alembic upgrade head
```

## Резервное копирование

### Бэкап базы данных

```bash
# Создать бэкап
docker-compose exec db pg_dump -U postgres mutual_followers > backup_$(date +%Y%m%d_%H%M%S).sql

# Восстановить из бэкапа
docker-compose exec -T db psql -U postgres mutual_followers < backup_file.sql
```

### Бэкап данных приложения

```bash
# Архивировать директорию с данными
tar -czf data_backup_$(date +%Y%m%d_%H%M%S).tar.gz data/checks/
```

## Устранение проблем

### Проблема: Порт уже занят

```bash
# Найти процесс, использующий порт
sudo lsof -i :8080
sudo lsof -i :5432

# Остановить процесс или измените порт в docker-compose.yml
```

### Проблема: Контейнер не запускается

```bash
# Проверить логи
docker-compose logs app

# Проверить статус
docker-compose ps

# Пересобрать контейнеры
docker-compose up --build --force-recreate
```

### Проблема: Ошибки миграций

```bash
# Проверить текущую версию миграций
docker-compose exec app alembic current

# Откатить последнюю миграцию
docker-compose exec app alembic downgrade -1

# Применить все миграции заново
docker-compose exec app alembic upgrade head
```

### Проблема: Недостаточно места на диске

```bash
# Очистить неиспользуемые ресурсы Docker
docker system prune -af --volumes

# Удалить старые образы
docker image prune -a

# Проверить использование диска
df -h
docker system df
```

## Безопасность

1. **Обязательно измените пароль PostgreSQL** в `.env` файле
2. **Не коммитьте `.env` файл** в Git репозиторий
3. **Используйте сильные пароли** для всех сервисов
4. **Настройте firewall** для ограничения доступа к портам:
   ```bash
   # Разрешить только SSH и необходимые порты
   sudo ufw allow 22/tcp
   sudo ufw enable
   ```
5. **Регулярно обновляйте** Docker образы и зависимости
6. **Используйте HTTPS** для доступа к API (настройте reverse proxy с nginx)

## Мониторинг

### Проверка использования ресурсов

```bash
# Использование ресурсов контейнерами
docker stats

# Использование дискового пространства
docker system df
```

### Проверка здоровья сервисов

```bash
# Проверка здоровья БД
docker-compose exec db pg_isready -U postgres

# Проверка API (если есть health endpoint)
curl http://localhost:8080/health
```

## Быстрая справка

```bash
# Перейти в директорию проекта
cd ~/unfollower_bot

# Просмотр логов
docker-compose logs -f

# Перезапуск всех сервисов
docker-compose restart

# Остановка всех сервисов
docker-compose down

# Обновление проекта
git pull && docker-compose up --build -d
```

## Дополнительные ресурсы

- [Подробная инструкция по настройке сервера](SERVER_SETUP.md)
- [Быстрый старт](../scripts/QUICK_START.md)
- [Структура проекта](../PROJECT_STRUCTURE.md)

