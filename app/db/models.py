import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def now_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------- Пользователи ----------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram ID
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = now_col()
    last_active_at: Mapped[datetime] = now_col()
    is_blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False)  # заблокировал бота
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)  # отключён админом
    subscribed: Mapped[bool] = mapped_column(Boolean, default=True)  # рассылки
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserConsent(Base):
    __tablename__ = "user_consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    document: Mapped[str] = mapped_column(String(32))  # terms | privacy
    version: Mapped[str] = mapped_column(String(16))
    accepted_at: Mapped[datetime] = now_col()


# ---------- Услуги ----------

class ServiceType(str, enum.Enum):
    tarot = "tarot"
    natal = "natal"


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[ServiceType] = mapped_column(Enum(ServiceType), default=ServiceType.tarot)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    image_file_id: Mapped[str | None] = mapped_column(String(256))
    price_stars: Mapped[int] = mapped_column(Integer)
    cards_count: Mapped[int] = mapped_column(Integer, default=1)
    positions: Mapped[list] = mapped_column(JSON, default=list)  # ["Прошлое", "Настоящее", ...]
    requires_question: Mapped[bool] = mapped_column(Boolean, default=True)
    required_fields: Mapped[list] = mapped_column(JSON, default=list)  # question|name|birth_date|...
    allow_reversed: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_duplicates: Mapped[bool] = mapped_column(Boolean, default=False)
    max_output_chars: Mapped[int] = mapped_column(Integer, default=4000)
    per_user_daily_limit: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class ServicePrompt(Base):
    __tablename__ = "service_prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    user_prompt_template: Mapped[str] = mapped_column(Text, default="")
    forbidden_topics: Mapped[str] = mapped_column(Text, default="")
    style_requirements: Mapped[str] = mapped_column(Text, default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = now_col()


# ---------- Заказы и оплата ----------

class OrderStatus(str, enum.Enum):
    created = "created"
    invoiced = "invoiced"
    paid = "paid"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"
    cancelled = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.created, index=True)
    input_data: Mapped[dict] = mapped_column(JSON, default=dict)  # вопрос, имя, дата рождения...
    price_stars: Mapped[int] = mapped_column(Integer)
    final_price_stars: Mapped[int] = mapped_column(Integer)
    promo_code_id: Mapped[int | None] = mapped_column(ForeignKey("promo_codes.id"))
    prompt_version_id: Mapped[int | None] = mapped_column(ForeignKey("service_prompts.id"))
    model_used: Mapped[str | None] = mapped_column(String(64))
    admin_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = now_col()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service: Mapped[Service] = relationship(lazy="joined")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("telegram_payment_charge_id", name="uq_payment_charge"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    amount_stars: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="XTR")
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(256))
    invoice_payload: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="paid")  # paid | refunded
    created_at: Mapped[datetime] = now_col()
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_reason: Mapped[str | None] = mapped_column(Text)


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), unique=True)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = now_col()


# ---------- Очередь генерации ----------

class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    retrying = "retrying"
    failed = "failed"
    cancelled = "cancelled"


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (UniqueConstraint("order_id", name="uq_job_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AIRequest(Base):
    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    status: Mapped[str] = mapped_column(String(32))  # ok | error | timeout
    is_free_service: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = now_col()


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = now_col()


# ---------- Таро ----------

class TarotCard(Base):
    __tablename__ = "tarot_cards"

    id: Mapped[int] = mapped_column(primary_key=True)  # 0..77
    name_ru: Mapped[str] = mapped_column(String(64))
    name_en: Mapped[str] = mapped_column(String(64))
    arcana: Mapped[str] = mapped_column(String(16))  # major | minor
    suit: Mapped[str | None] = mapped_column(String(16))
    image_file_id: Mapped[str | None] = mapped_column(String(256))
    upright_meaning: Mapped[str] = mapped_column(Text, default="")
    reversed_meaning: Mapped[str] = mapped_column(Text, default="")


class TarotDraw(Base):
    __tablename__ = "tarot_draws"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("tarot_cards.id"))
    position_index: Mapped[int] = mapped_column(Integer)
    position_name: Mapped[str] = mapped_column(String(128), default="")
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False)
    drawn_at: Mapped[datetime] = now_col()

    card: Mapped[TarotCard] = relationship(lazy="joined")


class DailyCard(Base):
    __tablename__ = "daily_cards"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_daily_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date)  # календарная дата по UTC+3
    card_id: Mapped[int] = mapped_column(ForeignKey("tarot_cards.id"))
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = now_col()

    card: Mapped[TarotCard] = relationship(lazy="joined")


# ---------- Натальная карта ----------

class BirthProfile(Base):
    __tablename__ = "birth_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(128), default="")
    birth_date: Mapped[date] = mapped_column(Date)
    birth_time: Mapped[str | None] = mapped_column(String(8))  # HH:MM
    time_accuracy: Mapped[str] = mapped_column(String(16))  # exact | approx_hour | unknown
    place_name: Mapped[str] = mapped_column(String(256))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    tz_id: Mapped[str | None] = mapped_column(String(64))  # IANA
    utc_offset_used: Mapped[float | None] = mapped_column(Float)  # исторический сдвиг в часах
    created_at: Mapped[datetime] = now_col()


class NatalCalculation(Base):
    __tablename__ = "natal_calculations"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    birth_profile_id: Mapped[int] = mapped_column(ForeignKey("birth_profiles.id"))
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # планеты, дома, аспекты
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = now_col()


# ---------- Промокоды ----------

class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    discount_percent: Mapped[int | None] = mapped_column(Integer)
    discount_stars: Mapped[int | None] = mapped_column(Integer)
    service_ids: Mapped[list] = mapped_column(JSON, default=list)  # [] = все услуги
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_activations: Mapped[int | None] = mapped_column(Integer)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1)
    min_order_stars: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PromoActivation(Base):
    __tablename__ = "promo_activations"

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    created_at: Mapped[datetime] = now_col()


# ---------- Рассылки ----------

class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    image_file_id: Mapped[str | None] = mapped_column(String(256))
    buttons: Mapped[list] = mapped_column(JSON, default=list)  # [{"text":..,"url":..}]
    audience_filter: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft|running|done
    total: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[int] = mapped_column(Integer, default=0)
    unsubscribed_skipped: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = now_col()


class BroadcastRecipient(Base):
    __tablename__ = "broadcast_recipients"

    id: Mapped[int] = mapped_column(primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|sent|blocked|error
    error: Mapped[str | None] = mapped_column(Text)


# ---------- Администрирование ----------

class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now_col()


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"))
    action: Mapped[str] = mapped_column(String(64))  # login|price_change|refund|...
    entity: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = now_col()


class ErrorLog(Base):
    __tablename__ = "error_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    component: Mapped[str] = mapped_column(String(64))
    error_type: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text)
    traceback: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    order_id: Mapped[int | None] = mapped_column(Integer)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = now_col()


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
