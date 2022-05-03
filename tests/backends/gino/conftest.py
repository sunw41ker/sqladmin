from curses import meta
import pytest

from sqladmin import Admin
from starlette.applications import Starlette
from typing import Generator, Callable

from tests.settings import Settings
from asyncio import AbstractEventLoop, new_event_loop, get_running_loop
from contextlib import suppress
from typing import Callable, Generator
from uuid import uuid4

from asyncpg import Connection
from asyncpg import connect as pg_adapter
from asyncpg import exceptions
from gino.exceptions import UninitializedError
# from fastapi_mail import FastMail
from gino.ext.starlette import Gino, GinoEngine  # type: ignore

# from app import Settings, get_settings
from tests.backends.gino.base import metadata
from .base import metadata as sa_gino


@pytest.fixture(autouse=True, scope="module")
def event_loop(settings: Settings):
    loop = new_event_loop()
    # loop = get_running_loop()
    loop.set_debug(settings.DEBUG)
    yield loop
    loop.close()


@pytest.fixture(autouse=True, scope="module")
async def database(
    settings: Settings, event_loop: AbstractEventLoop
) -> Generator[str, None, None]:
    async def connect(adapter: Callable) -> Connection:
        """Создаем подключение с сервером базы данных."""

        return await adapter(
            host=settings.DATABASE_SERVER,
            port=settings.DATABASE_PORT,
            user=settings.DATABASE_USER,
            password=settings.DATABASE_PASSWORD.get_secret_value(),
            # loop=event_loop,
        )

    #  Генерируем под каждый прогон тестов название базы
    DB_NAME = f"{settings.DATABASE_DB}__{uuid4().hex}"

    # Создаем новую базу под тестовую сессию.
    connection: Connection = await connect(pg_adapter)
    await connection.execute(
        f"CREATE DATABASE {DB_NAME} WITH OWNER {settings.DATABASE_USER};"
    )
    await connection.close()
    assert (
        connection.is_closed() is True
    ), "Fixture database hasn't closed the connection on startup"
    
    yield (
        f"postgresql://"
        f"{settings.DATABASE_USER}:"
        f"{settings.DATABASE_PASSWORD.get_secret_value()}@"
        f"{settings.DATABASE_SERVER}:"
        f"{settings.DATABASE_PORT}/"
        f"{DB_NAME}"
    )
    
    # Прибиваем базу после прохождения тестов
    connection = await connect(pg_adapter)
    with suppress(
        exceptions.PostgresConnectionError, 
        
        # is required???
        exceptions.ObjectInUseError):
        await connection.execute(f"DROP DATABASE IF EXISTS {DB_NAME};")
    await connection.close()
    assert (
        connection.is_closed() is True
    ), "Fixture database hasn't closed the connection on shutdown"


# @pytest.fixture(autouse=True, scope="session")
# async def migrations(settings: Settings, database: str) -> Generator[None, None, None]:
#     """Фикстура для применения миграций на всю сессию тестирования."""
#     cfg = Config(settings.PROJECT_PATH.joinpath("alembic.ini"))
#     cfg.set_main_option("sqlalchemy.url", database)
#     command.upgrade(cfg, "head")
#     yield
#     command.downgrade(cfg, "base")


@pytest.fixture(autouse=True, scope="module")
async def engine(
    settings: Settings,
    event_loop: AbstractEventLoop,
    database: str,
    app: Starlette,
    # migrations: None,
) -> Generator[Gino, None, None]:
    print('!!! *** metadata is starting... ***')

    # await db.set_bind('postgresql://localhost/gino')
    # await db.gino.create_all()

    # # further code goes here

    
    metadata.config["dsn"] = database
    config = metadata.config
    
    await metadata.set_bind(
                    config["dsn"],
                    echo=config["echo"],
                    min_size=config["min_size"],
                    max_size=config["max_size"],
                    ssl=config["ssl"],
                    **config["kwargs"],
                )
    metadata.init_app(app)
    await metadata.gino.create_all()
    yield metadata
    
    # await metadata.gino.delete_all()
    _bind = metadata.pop_bind()
    try: 
        await _bind.close()
    except UninitializedError:
        pass


# @pytest.fixture(autouse=True, scope="module")
# def gino_metadata() -> Gino:
#     return sa_gino


# @pytest.fixture(autouse=True, scope="module")
# async def engine(app: Starlette, gino_metadata: Gino) -> GinoEngine:
#     gino_db.init_app(app)
#     engine: GinoEngine = await bind_gino_db(gino_db)

#     yield engine

#     await unbind_gino_db(gino_db)


# @pytest.fixture(autouse=True, scope="module")
# def admin(app: Starlette, engine: GinoEngine) -> Admin:
#     return Admin(app=app, engine=engine)


# @pytest.fixture(autouse=True, scope="module")
# def base_model(db: Gino) -> Union[Model, ModelType]:
#     return declarative_base(db, (CRUDModel,))
