import enum
from typing import Any

import pytest
from sqlalchemy import create_engine, String, Text, Boolean, DateTime, Numeric, Integer
from sqlalchemy_utils import ChoiceType
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from starlette.applications import Starlette
from starlette import status

from sqladmin import Admin
from sqladmin.backends.gino.models import GinoRelationshipsLoader
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

from sqladmin.filters import ListFilterItem, ListOrderingItem, ListViewParams, ClauseEnum, SortDirectionEnum
from sqladmin.filters import ParametrizedColumnsManager, FilteredOrderedAdminColumn


pytestmark = pytest.mark.anyio


base_classes = (
    BaseModel,
    getMixinMetable(sa_engine=sa_metadata, default_options=({'namespace': 'filters'})), 
    getMixinSurrogatePK(sa_engine=sa_metadata),
)

loader = GinoRelationshipsLoader.get_or_init(base_model=BaseModel)

class Status(int, enum.Enum):
    REGISTERED = 1
    ACTIVE = 2


class User(*base_classes):
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



async def test_list_view_columns(app_temp: Starlette, engine: Engine, client_temp: AsyncClient) -> None:
    cols_identity = (
        ('User name', User.name, ), 
        ('E-mail', User.email, ),
        ('Biography', User.bio, ),
    )
    
    cols_mgr = ParametrizedColumnsManager()
    cols_mgr.update_columns_list_display(cols_identity)
    assert len(cols_mgr.columns) == len(cols_identity)
    
    assert cols_mgr.columns[0].label == cols_identity[0][0]
    assert cols_mgr.columns[1].label == cols_identity[1][0]
    assert cols_mgr.columns[2].label == cols_identity[2][0]
    
    sort_options = list(cols_mgr.get_sort_options(cols_mgr.columns[0]))
    assert len(sort_options) == len(list(SortDirectionEnum))
    
    for o in sort_options:
        assert o['label'] is not None
        assert o['value'] is not None
        assert o['is_active'] is not None
        assert o['urlencode'] is not None
        assert len(o['urlencode']) > 1
    
    
    filter_form = await cols_mgr.get_filter_form(cols_mgr.columns[0], engine=engine, backend=used_backend)
    assert filter_form is not None
    filter_form_fields = list(filter_form)
    assert len(filter_form.full_clause.choices) == len(list(ClauseEnum))
    
    form_data = {k:v for k, v in cols_mgr.columns_form_data(cols_mgr.columns)}
    assert len(form_data) == 0
    
    cols_mgr.columns[0].sort = SortDirectionEnum.ASCENDING
    
    form_data = {k:v for k, v in cols_mgr.columns_form_data(cols_mgr.columns)}
    assert len(form_data) == 1
    sort = form_data.get(FilteredOrderedAdminColumn._SORT_KEY)
    assert sort is not None
    assert len(sort) == 1
    assert sort[0] == cols_mgr.columns[0]._form_key_prefix + SortDirectionEnum.ASCENDING
    
    assert cols_mgr.columns[0].sort == SortDirectionEnum.ASCENDING
    cols_mgr.update_columns_list_display(cols_identity, url_query_str='o=User__name__d')
    assert cols_mgr.columns[0].sort == SortDirectionEnum.DESCENDING
    
    cols_mgr.update_columns_list_display(cols_identity, url_query_str='o=User__name__a&o=User__email__d')
    assert cols_mgr.columns[0].sort == SortDirectionEnum.ASCENDING
    assert cols_mgr.columns[1].sort == SortDirectionEnum.DESCENDING
    
    sort_options = list(cols_mgr.get_sort_options(cols_mgr.columns[0]))
    assert len(sort_options) == len(list(SortDirectionEnum))
    
    # if sort_options[0].value == SortDirectionEnum.ASCENDING
    assert sort_options[0]['urlencode'] == 'o=User__name__a&o=User__email__d'
    
    cols_mgr.columns[1].where.append((ClauseEnum.ILIKE, '%.com%'))
    sort_options = list(cols_mgr.get_sort_options(cols_mgr.columns[1]))
    assert 'o=User__name__a' in sort_options[0]['urlencode']
    # assert 'o=User__email__d' in sort_options[0]['urlencode']  why not work?
    assert 'User__email__ilike=%25.com%25' in sort_options[0]['urlencode']
    
    # Admin(app=app_temp, engine=engine)

    # r = await client_temp.get(
    #     app_temp.url_path_for("admin:index")
    # )
    
    
    # """
    # 1. Сделать сортировку и фильтрацию по колонкам
    # 1.1. ... генерацию урл по фильтрам, получение фильтров по урл
    # 1.2. ... изменение фильтра / сортировки
    # """
    
    
    


async def test_list_view_params(app_temp: Starlette, engine: Engine, client_temp: AsyncClient) -> None:
    # Admin(app=app_temp, engine=engine)

    # r = await client_temp.get(
    #     app_temp.url_path_for("admin:index")
    # )
    
    filters = [
        ListFilterItem(model="Model", field='fileld_with_1', clause=ClauseEnum.EXACT, operand=1),
        ListFilterItem(model="Model", field='fileld_with_2', clause=ClauseEnum.EXACT, operand=2),
        ListFilterItem(model="Model", field='fileld_with_3', clause=ClauseEnum.EXACT, operand=3),
    ]
    ordering = [
        ListOrderingItem(model="Model", field='fileld_with_1', direction=SortDirectionEnum.DESCENDING),
        ListOrderingItem(model="Model", field='fileld_with_3', direction=SortDirectionEnum.ASCENDING)
    ]
    view_params = ListViewParams(filters=filters, ordering=ordering)
    
    params_dict = view_params.dict()
    # print('View params: ', str(params_dict))
    encoded_str = view_params.urlencode()
    # assert 
    target_encoded = (
     'Model__fileld_with_1__exact=1'
     '&Model__fileld_with_2__exact=2'
     '&Model__fileld_with_3__exact=3'
     '&_o=Model__fileld_with_1__d'
     '&_o=Model__fileld_with_3__a'   
    )
    assert encoded_str == target_encoded
    
    view_params2 = ListViewParams.from_url_str(encoded_str)
    assert view_params2 is not None
    encoded2 = view_params.urlencode()
    assert encoded2 == target_encoded
    
    
    """
    1. Сделать сортировку и фильтрацию по колонкам
    1.1. ... генерацию урл по фильтрам, получение фильтров по урл
    1.2. ... изменение фильтра / сортировки
    """
    
    
    # assert r.status_code == status.HTTP_200_OK
    # assert r.text.count("<h3>Admin</h3>") == 1


# async def test_application_logo(app_temp: Starlette, engine: Engine, client_temp: AsyncClient, settings: Settings) -> None:
#     Admin(
#         app=app_temp,
#         engine=engine,
#         logo_url=f"{settings.TEST_HOST}/logo.svg",
#         base_url="/dashboard",
#     )
    
#     url = app_temp.url_path_for("admin:index")
#     assert url == '/dashboard/'
    
#     r = await client_temp.get(
#         url
#     )

#     assert r.status_code == status.HTTP_200_OK
    
#     assert (
#         f'<img src="{settings.TEST_HOST}/logo.svg" width="64" height="64"'
#         in r.text
#     )
