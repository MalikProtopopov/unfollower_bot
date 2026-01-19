# Инструкция по настройке сервера

## Очистка сервера от старого проекта

### Вариант 1: Использование скрипта (рекомендуется)

```bash
# Сделайте скрипт исполняемым
chmod +x scripts/cleanup_server.sh

# Запустите очистку
./scripts/cleanup_server.sh
```

### Вариант 2: Ручная очистка

```bash
# 1. Остановить все контейнеры
docker stop $(docker ps -aq)

# 2. Удалить все контейнеры
docker rm $(docker ps -aq)

# 3. Удалить все образы
docker rmi $(docker images -q)

# 4. Очистить неиспользуемые ресурсы
docker system prune -af --volumes

# 5. Удалить неиспользуемые сети
docker network prune -f
```

### Вариант 3: Очистка только конкретного проекта

Если на сервере несколько проектов и нужно удалить только старый:

```bash
# Остановить и удалить контейнеры старого проекта
docker-compose -f /path/to/old/project/docker-compose.yml down -v

# Удалить образы старого проекта
docker images | grep old_project_name | awk '{print $3}' | xargs docker rmi
```

## Настройка нового проекта

### Шаг 1: Загрузка проекта на сервер

```bash
# Если проект в Git репозитории
git clone <repository_url> check_follows
cd check_follows

# Или загрузите проект через scp/sftp
```

### Шаг 2: Настройка переменных окружения

```bash
# Создайте .env файл из примера
cp env.example .env

# Отредактируйте .env файл
nano .env  # или используйте ваш любимый редактор
```

**Обязательные переменные для настройки:**

```env
# Telegram Bot Token (получить у @BotFather)
TELEGRAM_TOKEN=your_telegram_bot_token_here

# PostgreSQL (ОБЯЗАТЕЛЬНО измените пароль!)
POSTGRES_PASSWORD=strong_password_here

# Instagram Session ID (для авторизованных запросов)
INSTAGRAM_SESSION_ID=your_session_id_here

# Admin Bot Token (если используется отдельный бот для админов)
ADMIN_BOT_TOKEN=your_admin_bot_token_here

# Admin User IDs (через запятую)
ADMIN_USER_IDS=123456789,987654321
```

### Шаг 3: Запуск проекта

#### Вариант 1: Использование скрипта (рекомендуется)

```bash
# Сделайте скрипт исполняемым
chmod +x scripts/setup_server.sh

# Запустите настройку
./scripts/setup_server.sh
```

#### Вариант 2: Ручной запуск

```bash
# Создайте необходимые директории
mkdir -p data/checks logs

# Соберите и запустите контейнеры
docker-compose build
docker-compose up -d

# Примените миграции базы данных
docker-compose exec app alembic upgrade head

# Проверьте статус
docker-compose ps
```

### Шаг 4: Проверка работы

```bash
# Просмотр логов всех сервисов
docker-compose logs -f

# Просмотр логов конкретного сервиса
docker-compose logs -f app
docker-compose logs -f bot
docker-compose logs -f worker

# Проверка статуса контейнеров
docker-compose ps

# Проверка доступности API
curl http://localhost:8080/docs
```

## Управление проектом

### Остановка проекта

```bash
docker-compose down
```

### Остановка с удалением volumes (удалит данные БД!)

```bash
docker-compose down -v
```

### Перезапуск проекта

```bash
docker-compose restart
```

### Пересборка после изменений

```bash
docker-compose up --build -d
```

### Просмотр логов

```bash
# Все сервисы
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f app
docker-compose logs -f bot
docker-compose logs -f worker
docker-compose logs -f db
```

### Выполнение команд внутри контейнера

```bash
# Зайти в контейнер приложения
docker-compose exec app bash

# Выполнить миграции
docker-compose exec app alembic upgrade head

# Создать новую миграцию
docker-compose exec app alembic revision --autogenerate -m "description"
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
lsof -i :8080
lsof -i :5432

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
```

## Безопасность

1. **Обязательно измените пароль PostgreSQL** в `.env` файле
2. **Не коммитьте `.env` файл** в Git репозиторий
3. **Используйте сильные пароли** для всех сервисов
4. **Настройте firewall** для ограничения доступа к портам
5. **Регулярно обновляйте** Docker образы и зависимости

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

# Проверка API
curl http://localhost:8080/health  # если есть health endpoint
```

