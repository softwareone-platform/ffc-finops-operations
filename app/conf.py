import pathlib

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

    system_jwt_token_max_lifespan_minutes: int = 5
    datasources_obsolete_after_months: int = 6

    optscale_auth_api_base_url: str
    optscale_rest_api_base_url: str
    optscale_cluster_secret: str

    azure_sa_container_name: str = "ffc-charges-files"
    azure_sa_url: str
    azure_sa_account_key: str
    azure_sa_max_block_size: int = 1024 * 1024 * 4  # 4 MiB
    azure_sa_max_single_put_size: int = 1024 * 1024 * 8  # 8 MiB
    azure_sa_max_concurrency: int = 4
    azure_sa_sas_expiration_token_mins: int = 5
    exchange_rate_api_base_url: str
    exchange_rate_api_token: str

    cli_rich_logging: bool = True
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


_settings = None


def get_settings() -> Settings:
    global _settings
    if not _settings:
        _settings = Settings()
    return _settings
