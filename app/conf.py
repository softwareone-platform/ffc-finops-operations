import pathlib
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = pathlib.Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="ffc_operations_",
        extra="ignore",
    )

    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int

    api_modifier_base_url: str
    api_modifier_jwt_secret: str
    secrets_encryption_key: str
    auth_access_jwt_secret: str
    auth_access_jwt_lifespan_minutes: int = 5
    auth_refresh_jwt_secret: str
    auth_refresh_jwt_lifespan_days: int = 7
    invitation_token_length: int = 64
    invitation_token_expires_days: int = 7
    pwd_reset_token_length: int = 64
    pwd_reset_token_length_expires_minutes: int = 15

    optscale_auth_api_base_url: str
    optscale_rest_api_base_url: str
    optscale_cluster_secret: str

    debug: bool = False

    @computed_field
    def postgres_async_url(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )

    @computed_field
    def postgres_url(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


AppSettings = Annotated[Settings, Depends(get_settings)]
