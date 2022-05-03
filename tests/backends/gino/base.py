from functools import lru_cache
from typing import Union

from gino.crud import CRUDModel
from gino.declarative import Model, ModelType, declarative_base
from gino.ext.starlette import Gino  # type: ignore

from tests.settings import get_settings

__all__ = ("metadata", "BaseModel", "get_database")


settings = get_settings()
metadata = Gino(
    dsn=settings.DATABASE_URI,
    pool_min_size=settings.DATABASE_POOL_MIN_SIZE,
    pool_max_size=settings.DATABASE_POOL_MAX_SIZE,
    echo=settings.DATABASE_ECHO,
    ssl=settings.DATABASE_SSL,
    use_connection_for_request=settings.DATABASE_USE_CONN_FOR_REQUEST,
    retry_limit=settings.DATABASE_RETRY_LIMIT,
    retry_interval=settings.DATABASE_RETRY_INTERVAL,
)

BaseModel: Union[Model, ModelType] = declarative_base(metadata, (CRUDModel,))

@lru_cache
def get_database():
    return metadata
