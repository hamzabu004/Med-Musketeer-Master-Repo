"""Runtime settings, read from MM_* environment variables. Missing required settings stop startup."""
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MM_", extra="ignore")

    # postgresql+psycopg://user:password@host:port/db; secret because it carries the password
    database_url: SecretStr
    zitadel_url: str
    emqx_status_url: str
    dependency_timeout_s: float = Field(default=3.0, gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Written by the zitadel-bootstrap job. Without it every authenticated endpoint answers 503.
    zitadel_config_file: Path = Path("/var/lib/medmusketeer/zitadel.json")
    # Written by the zitadel-bootstrap job: the mm-api service account's token, used to create
    # organisations and accounts in ZITADEL (app.zitadel). Without it those endpoints answer 503.
    zitadel_api_token_file: Path = Path("/var/lib/medmusketeer-secrets/zitadel-api.pat")
    # Shared with EMQX, which sends it with every hook call (app.broker). Unset: the hooks answer
    # 503, which EMQX treats as "ignore", so every client is refused.
    emqx_hook_secret: SecretStr | None = None
    # Password of the adapter's account (mm-adapter) on the internal listener.
    emqx_adapter_password: SecretStr | None = None
    # Browser origins that may call the API (the dashboard), comma-separated, e.g.
    # "http://localhost:3000,https://med-muskeeter.vercel.app". Empty: no CORS headers at all.
    cors_origins: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value
