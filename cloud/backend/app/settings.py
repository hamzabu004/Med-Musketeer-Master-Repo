"""Runtime settings, read from MM_* environment variables. Missing required settings stop startup."""
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def parse_origins(value: str) -> list[str]:
    """Comma-separated browser origins, without a trailing slash. Shared by the CORS allow-list and
    the dashboard app's redirect URIs (zitadel_bootstrap), which come from the same setting."""
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


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
    # EMQX's REST API (app.emqx_api), e.g. http://emqx:18083/api/v5, with the API key EMQX loads
    # from its bootstrap file (cloud/emqx/mm-entrypoint.sh). Unset: the revocation list is not
    # published and revoked gateways are not disconnected at once (both logged).
    emqx_api_url: str | None = None
    emqx_api_key: str = "mm-api"
    emqx_api_secret: SecretStr | None = None
    # The revocation list (app.revocation): how often unpublished versions are retried, and how
    # often the whole list is published again.
    revocation_poll_s: float = Field(default=5.0, gt=0)
    revocation_republish_s: float = Field(default=300.0, gt=0)
    # Shared with the MQTT adapter, which sends it with every ingest-v1 message (app.ingest).
    # Unset: ingestion answers 503 and the adapter keeps its messages until it is set.
    ingest_secret: SecretStr | None = None
    # Browser origins that may call the API (the dashboard), comma-separated, e.g.
    # "https://med-muskeeter.vercel.app" or "http://localhost:3000". Empty: no CORS headers at all.
    cors_origins: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value):
        return parse_origins(value) if isinstance(value, str) else value
