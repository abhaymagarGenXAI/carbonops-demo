from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Values come from environment variables, then `.env`, then `.env.local`
    (later files win), so the `.env.local` you already use for the Node app
    (which holds MONGODB_URI) works unchanged when placed in `backend/`.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- database -------------------------------------------------------
    mongodb_uri: str = Field(..., min_length=1)
    mongodb_db_name: str = "carbon_ops"  # same DB name the Mongoose code used

    # --- JWT ------------------------------------------------------------
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- HTTP -----------------------------------------------------------
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_name: str = "carbonops_refresh"

    # --- file storage / import (local disk; nothing leaves the server) ---
    upload_dir: str = "data/uploads"
    max_upload_mb: int = 20
    max_import_mb: int = 5
    max_import_rows: int = 500

    # --- misc -----------------------------------------------------------
    app_timezone: str = "Asia/Kolkata"
    seed_default_password: str = "ChangeMe!2026"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        # allow CORS_ORIGINS=http://a,http://b as well as a JSON list
        if isinstance(v, str) and not v.strip().startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
