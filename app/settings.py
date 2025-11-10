from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import EmailStr, Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Vape CRM"
    secret_key: str = Field("changeme", env="SECRET_KEY")
    database_url: str = Field(f"sqlite:///{Path(__file__).resolve().parent / 'vape_crm.db'}", env="DATABASE_URL")
    debug: bool = Field(False, env="DEBUG")
    google_maps_api_key: Optional[str] = Field(None, env="GOOGLE_MAPS_API_KEY")
    default_admin_email: EmailStr = Field("admin@example.com", env="DEFAULT_ADMIN_EMAIL")
    smtp_host: Optional[str] = Field(None, env="SMTP_HOST")
    smtp_port: int = Field(587, env="SMTP_PORT")
    smtp_username: Optional[str] = Field(None, env="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(None, env="SMTP_PASSWORD")
    smtp_from_email: EmailStr = Field("noreply@example.com", env="SMTP_FROM_EMAIL")
    allowed_origins: List[str] = Field(default_factory=lambda: ["*"])

    class Config:
        env_file = ".env"
        case_sensitive = False

    @validator("allowed_origins", pre=True)
    def parse_allowed_origins(cls, value: str | List[str]) -> List[str]:  # type: ignore[override]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
