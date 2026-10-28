"""Settings, from the environment (``KUNTUR_`` prefix) or a ``.env`` file. Secrets are ``SecretStr``:
they never show in a repr, a log line or an error message."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KUNTUR_",
        env_file=(".env", "../.env"),
        extra="ignore",
        validate_by_name=True,
        validate_by_alias=True,
    )

    database_url: SecretStr | None = None
    """SQL Server, e.g. ``mssql+pymssql://user:password@host:1433/kuntur``. Unset: everything in memory."""
    fleet_file: Path = Path("config/fleet.json")

    collector_enabled: bool = True
    poll_interval_s: float = Field(5.0, gt=0)
    poll_timeout_s: float = Field(5.0, gt=0)
    """Hard limit for one poll; the drivers' own timeout is shorter so they can classify the failure."""
    driver_timeout_s: float = Field(3.0, gt=0)
    max_concurrent_polls: int = Field(16, ge=1, le=256)

    camera_user: str = Field(
        "admin", validation_alias=AliasChoices("KUNTUR_CAMERA_USER", "KUNTUR_SIM_CAMERA_USER")
    )
    camera_password: SecretStr | None = Field(
        None, validation_alias=AliasChoices("KUNTUR_CAMERA_PASSWORD", "KUNTUR_SIM_CAMERA_PASSWORD")
    )

    token_secret: SecretStr | None = None
    """Signs the access tokens: 32 bytes or more. Required to run the API."""
    token_ttl_minutes: int = Field(60, ge=5, le=24 * 60)
    operator_password: SecretStr | None = None
    """When set, the account ``operador`` (OPERATOR) exists with this password."""
    viewer_password: SecretStr | None = None
    """When set, the account ``visitante`` (VIEWER) exists with this password."""

    host: str = "127.0.0.1"
    port: int = Field(8000, ge=1, le=65535)
    cors_origins: list[str] = ["http://localhost:4200"]
    expose_docs: bool = True

    ai_provider: Literal["template", "gemini"] = "template"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
