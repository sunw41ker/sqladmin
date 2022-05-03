import enum
from typing import Any, AsyncGenerator

import pytest
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import relationship
from sqlalchemy_utils.types import ChoiceType
from starlette.applications import Starlette
from sqladmin.backends import BackendEnum
from sqladmin.forms import get_model_form

from .backends.gino import BaseModel, metadata as sa_gino
from .backends.model import getMixinSurrogatePK, getMixinMetable

from gino.ext.starlette import Gino, GinoEngine  # type: ignore


pytestmark = pytest.mark.anyio


base_classes = (
    BaseModel,
    getMixinMetable(sa_engine=sa_gino, default_options=({'namespace': 'forms'})), 
    getMixinSurrogatePK(sa_engine=sa_gino),
)


class Status(int, enum.Enum):
    REGISTERED = 1
    ACTIVE = 2


class User(*base_classes):
    # __tablename__ = 'user_forms'
    name = sa_gino.Column(String(32), default="SQLAdmin")
    email = sa_gino.Column(String, nullable=False)
    bio = sa_gino.Column(Text)
    active = sa_gino.Column(Boolean)
    registered_at = sa_gino.Column(DateTime)
    status = sa_gino.Column(
        ChoiceType(Status, impl=sa_gino.Integer()), nullable=True, default=None,
    )
    balance = sa_gino.Column(Numeric)
    number = sa_gino.Column(Integer)

    addresses = relationship('Address', back_populates="user")


class Address(*base_classes):
    # __tablename__ = 'address_forms'
    user: Any = relationship(
        User,
        back_populates='addresses',
        uselist=False,
    )
    user_id = sa_gino.Column(
        Integer,
        sa_gino.ForeignKey(User.id, ondelete="cascade"),
    )

async def test_model_form_converter_with_defau(engine: GinoEngine) -> None:
    class Point(*base_classes):
        user = User()

    await get_model_form(model=Point, engine=engine, backend=BackendEnum.GINO)


async def test_model_form_only(engine: GinoEngine) -> None:
    Form = await get_model_form(model=User, engine=engine, only=["status"], backend=BackendEnum.GINO)
    assert len(Form()._fields) == 1


async def test_model_form_exclude(engine: GinoEngine) -> None:
    Form = await get_model_form(model=User, engine=engine, exclude=["status"], backend=BackendEnum.GINO)
    assert len(Form()._fields) == 8
