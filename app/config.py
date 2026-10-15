from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vehicle Sales Service"
    app_version: str = "1.0.0"
    environment: str = "development"
    database_url: str = "mysql+aiomysql://vehicle_sales:vehicle_sales@localhost:3307/vehicle_sales"
    service_token: SecretStr = SecretStr("change-me-in-production")
    core_base_url: str = "http://localhost:8000"
    core_request_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    docs_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("core_base_url")
    @classmethod
    def strip_core_base_url(cls, value: str) -> str:
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
