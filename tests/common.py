from functools import lru_cache
import os
from pydoc import doc
from typing import Any, List, OrderedDict, Union, Optional, Dict, ClassVar
from pydantic import BaseSettings, SecretStr, validator, PostgresDsn
from uuid import uuid4

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect
import sqlalchemy as sa

from sqladmin.backends import get_used_backend, BackendEnum


used_backend = get_used_backend()



TEST_DATABASE_URI_SYNC = os.environ.get("TEST_DATABASE_URI_SYNC", "sqlite:///test.db")
TEST_DATABASE_URI_ASYNC = os.environ.get(
    "TEST_DATABASE_URI_ASYNC", "sqlite+aiosqlite:///test.db"
)


class DummyData(dict):  # pragma: no cover
    def getlist(self, key: str) -> List[Any]:
        v = self[key]
        if not isinstance(v, (list, tuple)):
            v = [v]
        return v


# if is_used_gino():
#     async def unbind_gino_db(sa_gino: Gino):
#         # await sa_gino.gino.drop_all()
#         # _bind = sa_gino.pop_bind()
#         # await _bind.close()
#         pass

#     sa_gino: Gino = get_gino_db()
#     GinoBaseModel: Union[Model, ModelType] = get_gino_base_model(sa_gino=sa_gino)
    
