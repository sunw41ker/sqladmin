
from functools import lru_cache
from sqlalchemy import Integer
from typing import Any, List, OrderedDict, Union, Optional, Dict, ClassVar
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4


# @lru_cache
def getMixinMetable(sa_engine, default_options={}):
    class Metable:
        """Mixin which store meta data of a model.
        :param options: - meta options defined for a model
        """

        options: ClassVar[Dict[str, Any]] = default_options

        @sa_engine.declared_attr
        def __tablename__(cls) -> str:
            # namespace for model name in order to prevent naming pollusion
            app_label = cls.options.get("namespace", "")
            model_name = cls.__name__.lower()
            return "_".join((app_label, model_name)).strip("_")

    return Metable


@lru_cache
def getMixinSurrogatePK(sa_engine):
    class SurrogatePK:
        """Mixin для добавления сурогатного первичного ключа."""
        
        id = sa_engine.Column(Integer, primary_key=True, unique=True)
    return SurrogatePK
