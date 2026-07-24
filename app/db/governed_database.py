import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL


load_dotenv()


class GovernedDatabaseConfig(BaseModel):
    """
    AI Query Runtime 专用数据库配置。

    与现有 DDL / Seed Engine 分离，避免在线查询继续复用
    具备写权限的开发账户。
    """

    model_config = ConfigDict(frozen=True)

    username: str
    password: str
    host: str
    port: int = Field(ge=1, le=65_535)
    database: str

    pool_size: int = Field(default=5, ge=1, le=20)
    max_overflow: int = Field(default=5, ge=0, le=20)
    pool_timeout_seconds: int = Field(
        default=10,
        ge=1,
        le=60,
    )
    pool_recycle_seconds: int = Field(
        default=1_800,
        ge=60,
        le=7_200,
    )

    application_name: str = "beauty_bi_governed_query"

    @model_validator(mode="after")
    def validate_config(self):
        for field_name in (
            "username",
            "password",
            "host",
            "database",
            "application_name",
        ):
            value = getattr(self, field_name)

            if not value or not value.strip():
                raise ValueError(
                    f"{field_name} cannot be empty or whitespace."
                )

        return self


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Missing required governed database setting: {name}"
        )

    return value


def load_governed_database_config() -> GovernedDatabaseConfig:
    """
    加载 AI Query Runtime 专用凭据。

    用户名和密码不回退到 POSTGRES_USER / POSTGRES_PASSWORD，
    避免配置遗漏时意外复用 DDL / Seed 账户。
    """

    return GovernedDatabaseConfig(
        username=_required_env("AI_QUERY_POSTGRES_USER"),
        password=_required_env("AI_QUERY_POSTGRES_PASSWORD"),
        host=_required_env("POSTGRES_HOST"),
        port=int(_required_env("POSTGRES_PORT")),
        database=_required_env("POSTGRES_DB"),
        pool_size=int(
            os.getenv("AI_QUERY_POOL_SIZE", "5")
        ),
        max_overflow=int(
            os.getenv("AI_QUERY_MAX_OVERFLOW", "5")
        ),
        pool_timeout_seconds=int(
            os.getenv("AI_QUERY_POOL_TIMEOUT_SECONDS", "10")
        ),
        pool_recycle_seconds=int(
            os.getenv(
                "AI_QUERY_POOL_RECYCLE_SECONDS",
                "1800",
            )
        ),
        application_name=os.getenv(
            "AI_QUERY_APPLICATION_NAME",
            "beauty_bi_governed_query",
        ),
    )


def build_governed_database_url(
    config: GovernedDatabaseConfig,
) -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=config.username,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.database,
    )


def create_governed_engine(
    config: GovernedDatabaseConfig,
) -> Engine:
    return create_engine(
        build_governed_database_url(config),
        pool_pre_ping=True,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
        pool_timeout=config.pool_timeout_seconds,
        pool_recycle=config.pool_recycle_seconds,
        echo=False,
        connect_args={
            "application_name": config.application_name,
        },
    )


@lru_cache(maxsize=1)
def get_governed_engine() -> Engine:
    """
    延迟创建独立 Engine。

    这样普通 V1 模块导入时不会因为 Day70 环境变量未配置
    而破坏现有 Stable Graph。
    """

    config = load_governed_database_config()
    return create_governed_engine(config)
