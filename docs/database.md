# Структура базы данных (PostgreSQL)

Все таблицы описаны в `app/db/models.py`; изменения — только через миграции Alembic.

| Таблица | Назначение | Ключевые ограничения |
|---|---|---|
| users | пользователи бота (PK = Telegram ID) | |
| user_consents | принятие terms/privacy/pd_consent с версией и датой | |
| services | каталог услуг (цена, карты, поля, лимиты) | uq: code; архивирование вместо удаления |
| service_prompts | версии промптов ИИ по услугам | версия фиксируется в заказе |
| orders | заказы: входные данные, цена, статус, модель | |
| payments | платежи Stars | **uq: telegram_payment_charge_id** — защита от двойной выдачи |
| refunds | возвраты | uq: payment_id — повторный возврат невозможен |
| generation_jobs | очередь генерации (queued→processing→completed/retrying/failed/cancelled) | **uq: order_id** |
| ai_requests | учёт обращений к ИИ: модель, токены, стоимость | |
| results | готовые результаты (повторная выдача без оплаты) | uq: order_id |
| tarot_cards | справочник 78 карт | id 0..77 |
| tarot_draws | выпавшие карты: позиция, положение, время | |
| daily_cards | бесплатная карта дня | **uq: (user_id, day)** — день по UTC+3 |
| birth_profiles | данные рождения: дата/время/точность, координаты, tz IANA, использованный UTC-сдвиг | |
| natal_calculations | рассчитанные натальные данные + предупреждения | uq: order_id |
| promo_codes | промокоды: скидка, период, лимиты | uq: code |
| promo_activations | активации промокодов | |
| broadcasts | рассылки и их статистика | |
| broadcast_recipients | получатели рассылки по статусам | |
| admin_users | администраторы панели (bcrypt-хеш) | uq: login |
| admin_audit_log | журнал действий администратора | |
| error_log | журнал ошибок (без секретов) | |
| settings | редактируемые тексты, кнопки, флаги | PK = key |

## Статусы заказа

`created → invoiced → paid → completed`, ветки: `failed`, `refunded`, `cancelled`.

## Идемпотентность оплаты

Обработка `successful_payment` выполняется одной транзакцией: вставка платежа
(уникальный `telegram_payment_charge_id`) + перевод заказа в `paid` + создание
задания (уникальный `order_id`). Повторное уведомление Telegram приводит к
IntegrityError → rollback → никаких повторных списаний, заданий и выдач.
