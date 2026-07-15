from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-this-secret-in-production"
INSECURE_DB_MARKERS = (":root@", ":password@", ":postgres:postgres@")


class Settings(BaseSettings):
    app_name: str = "ConjunApp API"
    environment: Literal["development", "production"] = "development"
    database_url: str = "postgresql+psycopg://postgres:root@localhost:5432/conjunapp"
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 720
    allow_admin_register: bool = True
    seed_on_startup: bool = True
    # Phase 4 integration adapters (swap without changing domain services)
    payment_adapter: Literal["stub"] = "stub"
    notification_adapter: Literal["logging"] = "logging"
    access_adapter: Literal["local"] = "local"
    image_storage_adapter: Literal["url_only", "stub"] = "url_only"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate_runtime_security(self) -> None:
        """Fail fast when production runs with unsafe defaults."""
        if not self.is_production:
            return

        if self.jwt_secret_key.strip() in {"", DEFAULT_JWT_SECRET}:
            raise RuntimeError(
                "ENVIRONMENT=production requiere JWT_SECRET_KEY seguro "
                "(no uses el valor por defecto)."
            )

        lowered = self.database_url.lower()
        if any(marker in lowered for marker in INSECURE_DB_MARKERS):
            raise RuntimeError(
                "ENVIRONMENT=production exige DATABASE_URL con credenciales fuertes "
                "(evita passwords debiles como 'root' o 'password')."
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime_security()
    return settings
