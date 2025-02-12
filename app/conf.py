import pathlib
import sys

from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = pathlib.Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="ffc_operations_",
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

    opt_auth_base_url: str
    opt_api_base_url: str
    opt_cluster_secret: str

    debug: bool = False

    def get_db_name(self) -> str:
        db = self.postgres_db

        if "pytest" in sys.modules:
            db = f"{db}_test"

        return db

    @computed_field
    def postgres_async_url(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.get_db_name(),
        )

    @computed_field
    def postgres_url(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.get_db_name(),
        )
