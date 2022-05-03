import os
from typing import Optional, Union, Dict, Any
from pydantic import BaseSettings, AnyHttpUrl, BaseSettings, EmailStr, Field, PostgresDsn, RedisDsn, SecretStr, validator


__all__ = (
    'Settings',
    'get_settings'
)


class GinoSettings(BaseSettings):
    
    DATABASE_SERVER: str = "localhost"
    DATABASE_PORT: str = "5432"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: SecretStr = SecretStr("postgres")
    # DATABASE_PASSWORD: str = "postgres"
    DATABASE_DB: str = "test_sqladmin"

    # @validator("DATABASE_DB", pre=True)
    # def define_db_name(cls, v: str, values: Dict[str, Any]) -> str:
    #     if values.get("ENV") == Env.TESTING:
    #         v = f"test_{v}"
    #     return v

    DATABASE_URI: Optional[Union[PostgresDsn, str]] = None

    @validator("DATABASE_URI", pre=True)
    def assemble_db_connection(
        cls, v: Optional[str], values: Dict[str, Any]
    ) -> Union[PostgresDsn, str]:
        if isinstance(v, str):
            return v

        return PostgresDsn.build(
            scheme="postgresql",
            user=values["DATABASE_USER"],
            password=values["DATABASE_PASSWORD"].get_secret_value(),
            host=values["DATABASE_SERVER"],
            port=values["DATABASE_PORT"],
            path=f"/{values['DATABASE_DB']}",
        )

    DATABASE_ECHO: bool = False
    DATABASE_SSL: Optional[Any] = None
    DATABASE_USE_CONN_FOR_REQUEST: bool = True
    DATABASE_RETRY_LIMIT: int = 3
    DATABASE_RETRY_INTERVAL: int = 60
    DATABASE_POOL_MIN_SIZE: int = 4
    DATABASE_POOL_MAX_SIZE: int = 16


class SA_Settings(BaseSettings):
    TEST_DATABASE_URI_SYNC: str = os.environ.get("TEST_DATABASE_URI_SYNC", "sqlite:///test.db")
    TEST_DATABASE_URI_ASYNC: str = os.environ.get(
        "TEST_DATABASE_URI_ASYNC", "sqlite+aiosqlite:///test.db"
    )


class Settings(GinoSettings, SA_Settings, BaseSettings):
    DEBUG: bool = True
    TEST_HOST: str = "http://127.0.0.1:8080"


settings: Settings = Settings()


def get_settings() -> Settings:
    return settings
