from functools import lru_cache
from enum import Enum
from .gino import can_use as can_use_gino

def can_use_sqlalchemy13():
    # TODO: implement
    return not can_use_gino()


def can_use_sqlalchemy14():
    # TODO: implement
    return False


class BackendEnum(Enum):
    SA_13 = 'sa_13'
    SA_14 = 'sa_14'
    GINO = 'gino'


_used_backend = None


if can_use_gino():
    from gino.ext.starlette import Gino  # type: ignore
    from .gino.base import *
    _used_backend = BackendEnum.GINO
elif can_use_sqlalchemy14():
    raise Exception('Backend SqlAlchemy 1.4 not implemented')
    from sqlalchemy.engine import Engine as SA_Engine
    from sqlalchemy.ext.asyncio import AsyncEngine as SA_AsyncEngine, AsyncSession as SA_AsyncSession
    EngineType = ClassVar[Union[SA_Engine, SA_AsyncEngine]]
    _used_backend = BackendEnum.SA_14
elif can_use_sqlalchemy13():
    raise Exception('Backend SqlAlchemy 1.3 not implemented')
    EngineType = ClassVar[Union[Engine, AsyncEngine]]
    _used_backend = BackendEnum.SA_13
else:
    raise Exception('Unknown backend')


@lru_cache
def get_used_backend() -> BackendEnum:
    return _used_backend
