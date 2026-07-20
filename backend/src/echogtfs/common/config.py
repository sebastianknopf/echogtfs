from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://echogtfs:echogtfs@db:5432/echogtfs"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # JWT – no default: startup fails explicitly if SECRET_KEY is not set
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # API docs – disable in production
    docs_enabled: bool = False

    # CORS – comma-separated list of allowed origins, e.g. "https://app.example.com"
    cors_origins: str = ""

    # Rate-limiting on the login endpoint (requests / time-window)
    login_rate_limit: str = "10/minute"

    # First superuser – created automatically if no users exist yet
    first_superuser: str = "admin"
    first_superuser_email: str = "admin@localhost"
    first_superuser_password: str = "admin"

    @property
    def cors_origins_list(self) -> list[str]:
        """Return origins as a list; empty string means no origins allowed."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
