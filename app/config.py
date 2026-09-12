from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_tg_ids: str = ""

    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "tarobot"
    postgres_user: str = "tarobot"
    postgres_password: str = ""

    redis_host: str = "redis"
    redis_port: int = 6379

    ai_provider: str = "openai"
    openai_api_key: str = ""
    ai_model_primary: str = "gpt-5.6-luna"
    ai_model_fallback: str = "gpt-5.4-nano"
    ai_max_input_tokens: int = 8000
    ai_max_output_tokens: int = 2048
    ai_temperature: float = 0.8
    ai_timeout_seconds: int = 60
    ai_max_retries: int = 3
    ai_daily_budget_usd: float = 5.0
    ai_monthly_budget_usd: float = 100.0
    ai_budget_action: str = "block"  # block | fallback

    admin_secret_key: str = "change-me"
    admin_session_ttl_minutes: int = 60
    admin_cookie_secure: bool = False
    admin_panel_host: str = "0.0.0.0"
    admin_panel_port: int = 8000

    geocoder_url: str = "https://nominatim.openstreetmap.org/search"

    timezone_display: str = "Europe/Moscow"
    environment: str = "production"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def admin_ids(self) -> list[int]:
        return [int(x) for x in self.admin_tg_ids.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
