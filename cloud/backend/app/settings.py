"""Runtime settings, read from MM_* environment variables. Missing required settings stop startup."""
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MM_", extra="ignore")

    # postgresql+psycopg://user:password@host:port/db; secret because it carries the password
    database_url: SecretStr
    zitadel_url: str
    emqx_status_url: str
    dependency_timeout_s: float = Field(default=3.0, gt=0)
