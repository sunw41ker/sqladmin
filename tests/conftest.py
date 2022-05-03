import pytest
from functools import lru_cache
from typing import AsyncGenerator, Tuple, Union
from asgi_lifespan import LifespanManager
from starlette.applications import Starlette
from httpx import AsyncClient

from .backends.conftest import *


@pytest.fixture(scope="session")
def anyio_backend() -> Tuple[str, dict]:
    return ("asyncio", {"debug": True})


@pytest.fixture(autouse=True, scope="session")
def settings() -> Settings:
    return get_settings()


@lru_cache
def get_app() -> Starlette:
    return Starlette()


@pytest.fixture(autouse=True, scope="module")
def app() -> Starlette:
    app = get_app()
    # Увеличил timeout, иначе приложение не успевает пройти этап инициализации
    yield app
    # from asgi_lifespan import LifespanManager
    # async with LifespanManager(app, 60, 60):
    #     yield app

@pytest.fixture(autouse=True, scope="function")
def app_temp() -> Starlette:
    yield Starlette()


# @pytest.fixture(autouse=True, scope="function")
# def app_clean() -> Starlette:
#     app = get_app()
#     # Увеличил timeout, иначе приложение не успевает пройти этап инициализации
#     yield app
#     # from asgi_lifespan import LifespanManager
#     # async with LifespanManager(app, 60, 60):
#     #     yield app

@pytest.fixture(autouse=True, scope="module")
async def client(
    settings: Settings, app: Starlette
) -> AsyncGenerator[AsyncClient, None]:
    # @see: https://github.com/tiangolo/fastapi/issues/2003
    async with AsyncClient(
        app=app,
        base_url=str(settings.TEST_HOST),
        # cookies={settings.CSRF_COOKIE_NAME: app.csrf.encode(app.csrf.secret)},  # type: ignore
    ) as c:
        yield c


@pytest.fixture(autouse=True, scope="function")
async def client_temp(
    settings: Settings, app_temp: Starlette
) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        app=app_temp,
        base_url=str(settings.TEST_HOST),
    ) as c:
        yield c
