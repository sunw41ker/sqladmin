from functools import lru_cache
from gino.crud import CRUDModel
from gino.declarative import Model, ModelType, ColumnAttribute, declarative_base, inspect_model_type
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql.schema import Column
from sqlalchemy.orm import ColumnProperty, Mapper, RelationshipProperty, Session
from sqladmin.backends.gino.models import Gino, GinoEngine, GinoModelMapper 


from typing import Any, List, OrderedDict, Union, Optional, Dict, ClassVar
from pydantic import BaseSettings, SecretStr, validator, PostgresDsn
from uuid import uuid4

# from .base import get_gino_db, get_gino_base_model
from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy as sa


# sa_gino: Gino = get_gino_db()
# GinoBaseModel: Union[Model, ModelType] = get_gino_base_model(sa_gino=sa_gino)


@lru_cache
def Metable(sa_engine):
    class Metable:
        """Mixin which store meta data of a model.
        :param options: - meta options defined for a model
        """

        options: ClassVar[Dict[str, Any]] = {}

        @sa_engine.declared_attr
        def __tablename__(cls) -> str:
            # namespace for model name in order to prevent naming pollusion
            app_label = cls.options.get("namespace", "")
            model_name = cls.__name__.lower()
            return "_".join((app_label, model_name)).strip("_")
    return Metable


@lru_cache
def Mapper(sa_engine):
    class Mapper:
        """Mixin which adds custom gino mapper
        """
        
        @sa_engine.declared_attr
        def __mapper__(cls) -> GinoModelMapper:
            base = super()
            if hasattr(base, '__mapper__'):
                mapper = super().__mapper__()
            else:
                mapper = GinoModelMapper(model=cls)
            return mapper
    return Mapper

# # noinspection PyProtectedMember
# @sa.inspection._inspects(Metable)
# def inspect_model_type(target):
#     target._check_abstract()
#     return sa.inspection.inspect(target.__table__)


@lru_cache
def SurrogatePK(sa_engine):
    class SurrogatePK:
        """Mixin для добавления сурогатного первичного ключа."""

        id = sa_gino.Column(UUID(), primary_key=True, default=uuid4, unique=True)
    return SurrogatePK
