# Taro Bot — Telegram-бот раскладов Таро и натальных карт

Телеграм-бот с оплатой в Telegram Stars, интерпретациями через Gemini API,
расчётом натальных карт (Swiss Ephemeris) и веб-админкой.

## Состав

| Компонент | Технология | Каталог |
|---|---|---|
| Telegram-бот | aiogram 3 (long polling) | `app/bot/` |
| Очередь генерации | arq + Redis | `app/worker/` |
| Админ-панель | FastAPI + Jinja2 | `app/admin/` |
| БД | PostgreSQL 16 + SQLAlchemy 2 + Alembic | `app/db/`, `alembic/` |
| Модуль Таро | серверный ГСЧ (`secrets`) | `app/tarot/` |
| Натальная карта | Swiss Ephemeris + IANA tzdata | `app/natal/` |
| ИИ | Google Gemini API (модель в настройках) | `app/ai/` |
| Бэкапы | pg_dump ежедневно, контейнер `backup` | `scripts/` |

## Быстрый старт

```bash
cp .env.example .env        # заполнить BOT_TOKEN, пароли, GEMINI_API_KEY
docker compose up -d --build
# Миграции и первичное заполнение карт/услуг выполняются автоматически.
docker compose run --rm bot python -m scripts.create_admin admin 'ПАРОЛЬ' 111111111
```

Админ-панель: `https://<домен>/` (Nginx проксирует на контейнер `admin`,
сертификаты — в `nginx/certs/`).

## Документация

- [docs/deploy.md](docs/deploy.md) — развёртывание на новом сервере и обновление
- [docs/backup.md](docs/backup.md) — резервное копирование и восстановление
- [docs/operations.md](docs/operations.md) — смена ИИ-модели, ключей, передача проекта
- [docs/database.md](docs/database.md) — структура базы данных

## Важные замечания

- **Swiss Ephemeris**: `pyswisseph` закомментирован в `requirements.txt`.
  Для коммерческого закрытого проекта требуется Swiss Ephemeris Professional
  License (приобретается Заказчиком). Без установленной библиотеки заказы
  натальной карты завершатся ошибкой генерации — услугу можно отключить в админке.
- **Gemini API**: ключ и платёжный профиль принадлежат Заказчику; расходы
  оплачиваются отдельно. Модель задаётся в `.env` (`AI_MODEL_PRIMARY`).
- **Telegram Stars**: цифровые услуги внутри Telegram оплачиваются только в XTR;
  возвраты — через `refundStarPayment` из карточки заказа в админке.
- Тексты `/terms` и `/privacy` — заглушки; финальные юридические тексты
  предоставляет Заказчик (правятся в админке, раздел «Тексты и настройки»).
