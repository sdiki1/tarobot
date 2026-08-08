# Развёртывание и обновление

## Требования к серверу

VPS за пределами РФ (доступность Gemini API), 1–2 CPU, 2 ГБ RAM, 20 ГБ диск,
Ubuntu 22.04+, Docker + Docker Compose plugin, домен для админ-панели.

## Развёртывание на новом сервере

```bash
git clone <репозиторий> tarobot && cd tarobot
cp .env.example .env
nano .env                      # BOT_TOKEN, POSTGRES_PASSWORD, GEMINI_API_KEY,
                               # ADMIN_SECRET_KEY (openssl rand -hex 32), ADMIN_TG_IDS

# HTTPS-сертификат (пример с certbot standalone):
apt install certbot
certbot certonly --standalone -d admin.example.com
mkdir -p nginx/certs
cp /etc/letsencrypt/live/admin.example.com/fullchain.pem nginx/certs/
cp /etc/letsencrypt/live/admin.example.com/privkey.pem  nginx/certs/

docker compose up -d --build   # миграции применяются сервисом migrate
docker compose run --rm bot python scripts/seed.py
docker compose run --rm bot python scripts/create_admin.py admin 'ПАРОЛЬ' <ваш_tg_id>
```

Контейнеры имеют `restart: unless-stopped` — бот автоматически поднимается
после перезагрузки сервера (docker.service должен быть в автозапуске:
`systemctl enable docker`).

## Проверка работоспособности

- `docker compose ps` — все сервисы `running/healthy`;
- `https://домен/health` — `{"status":"ok"}`;
- в боте `/start` → главное меню.

## Обновление

```bash
cd tarobot
git pull
docker compose up -d --build      # migrate применит новые миграции
```

## Миграции

Изменение структуры БД — только через Alembic:

```bash
docker compose run --rm bot alembic revision --autogenerate -m "описание"
docker compose run --rm bot alembic upgrade head
```
