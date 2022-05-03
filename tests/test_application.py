from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from starlette.applications import Starlette
from starlette import status

from sqladmin import Admin
from tests.settings import Settings
from tests.backends import used_backend, BackendEnum
from tests.backends.model import getMixinMetable, getMixinSurrogatePK
from httpx import AsyncClient

if used_backend == BackendEnum.GINO:
    from gino.ext.starlette import Gino as Engine  # type: ignore
    from tests.backends.gino import BaseModel, metadata as sa_gino

    sa_metadata = sa_gino
    
    model_base_classes = (
        BaseModel, 
        getMixinMetable(sa_engine=sa_metadata, default_options={'namespace': 'application'}), 
        getMixinSurrogatePK(sa_engine=sa_metadata), 
    )
elif used_backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
    from sqlalchemy.engine import Engine
    # Base = declarative_base()  # type: Any


pytestmark = pytest.mark.anyio


async def test_application_title(app_temp: Starlette, engine: Engine, client_temp: AsyncClient) -> None:
    Admin(app=app_temp, engine=engine)

    r = await client_temp.get(
        app_temp.url_path_for("admin:index")
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.text.count("<h3>Admin</h3>") == 1


async def test_application_logo(app_temp: Starlette, engine: Engine, client_temp: AsyncClient, settings: Settings) -> None:
    Admin(
        app=app_temp,
        engine=engine,
        logo_url=f"{settings.TEST_HOST}/logo.svg",
        base_url="/dashboard",
    )
    
    url = app_temp.url_path_for("admin:index")
    assert url == '/dashboard/'
    
    r = await client_temp.get(
        url
    )

    assert r.status_code == status.HTTP_200_OK
    
    assert (
        f'<img src="{settings.TEST_HOST}/logo.svg" width="64" height="64"'
        in r.text
    )
