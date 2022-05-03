
from typing import Any, AsyncGenerator

import pytest
from sqlalchemy import Column, Date, ForeignKey, Integer, String, func, select

from sqlalchemy.orm import selectinload, relationship
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.testclient import TestClient
from starlette import status
from httpx import AsyncClient

from sqlalchemy.dialects.postgresql import UUID
from sqladmin import Admin, ModelAdmin
from sqladmin.backends.gino.models import GinoEngine  #, relationship
from sqlalchemy.ext.hybrid import hybrid_property

from gino.ext.starlette import Gino  # type: ignore 
from sqladmin.backends.gino.models import get_many2one_query, get_one2many_query  # type: ignore
from tests.backends.gino import BaseModel, metadata as sa_gino
from tests.backends.model import getMixinMetable, getMixinSurrogatePK
from tests.settings import Settings

pytestmark = pytest.mark.anyio

# Metable, SurrogatePK = 

base_classes = (
    BaseModel,
    getMixinMetable(sa_engine=sa_gino, default_options={'namespace': 'admin'}), 
    getMixinSurrogatePK(sa_engine=sa_gino),
)


class User(*base_classes):
    name = sa_gino.Column(String(length=16))
    email = sa_gino.Column(String)
    date_of_birth = sa_gino.Column(Date)
    
    addresses = relationship('Address', back_populates="user")
    
    @hybrid_property
    def name_name(self):
        return self.name + ' ' + self.name

    def __str__(self) -> str:
        return f"User {self.id}"

# User._init_sa_class_manager()


class Address(*base_classes):
    user: Any = relationship(
        User,
        back_populates='addresses',
        uselist=False,
    )
    user_id = sa_gino.Column(
        Integer,
        sa_gino.ForeignKey('admin_user.id', ondelete="cascade"),
    )
    
    # @property
    # def user(self):
    #     return User.query.where(User.id==self.user_id).gino.one

    def __str__(self) -> str:
        return f"Address {self.id}"

# Address._init_sa_class_manager()


class Movie(*base_classes):
    pass

# Movie._init_sa_class_manager()


@pytest.fixture(scope="module", autouse=True)
def admin_with_models(
        app: Starlette,
        engine: GinoEngine):
    admin = Admin(app=app, engine=engine)
    admin.register_model(UserAdmin)
    admin.register_model(AddressAdmin)
    admin.register_model(MovieAdmin)
    return admin


class UserAdmin(ModelAdmin, model=User):
    column_list = [User.id, User.name, User.email, User.addresses]
    column_labels = {User.email: "Email"}


class AddressAdmin(ModelAdmin, model=Address):
    column_list = ["id", "user_id", "user"]
    name_plural = "Addresses"


class MovieAdmin(ModelAdmin, model=Movie):
    can_edit = False
    can_delete = False
    can_view_details = False

    def is_accessible(self, request: Request) -> bool:
        return False

    def is_visible(self, request: Request) -> bool:
        return False


async def test_root_view(app: Starlette, client: AsyncClient) -> None:
    r = await client.get(
        app.url_path_for("admin:index"),
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.text.count('<span class="nav-link-title">Users</span>') == 1
    assert r.text.count('<span class="nav-link-title">Addresses</span>') == 1


@pytest.mark.asyncio
async def test_invalid_list_page(
    app: Starlette, client: AsyncClient
) -> None:
    r = await client.get(
        app.url_path_for("admin:list", identity='* NOT EXISTS *'),
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND


async def test_list_view_single_page(app: Starlette, client: AsyncClient, settings: Settings) -> None:
    await User.delete.gino.status()
    for _ in range(5):
        await User.create(name="John Doe")
    #     await user.create()
    #     session.add(user)
    # await session.commit()

    # with TestClient(app) as client:
    #     r = client.get("/admin/user/list")
    r = await client.get(
        app.url_path_for("admin:list", identity='user'),
    )
    assert r.status_code == status.HTTP_200_OK
    assert (
        "Showing <span>1</span> to <span>5</span> of <span>5</span> items</p>"
        in r.text
    )

    # Showing active navigation link
    assert (
        '<a class="nav-link active" href="{}{}"'.format(
            settings.TEST_HOST,
            app.url_path_for("admin:list", identity='user')
        )
        in r.text
    )

    # Next/Previous disabled
    assert r.text.count('<li class="page-item disabled">') == 2


# @pytest.mark.asyncio
async def test_list_view_multi_page(
    app: Starlette,
    client: AsyncClient
) -> None:
    await User.delete.gino.status()
    for _ in range(45):
        await User.create(name="John Doe")

    r = await client.get(
        app.url_path_for("admin:list", identity='user'),
    )
    assert r.status_code == status.HTTP_200_OK

    assert (
        "Showing <span>1</span> to <span>10</span> of <span>45</span> items</p>"
        in r.text
    )

    # Previous disabled
    assert r.text.count('<li class="page-item disabled">') == 1
    assert r.text.count('<li class="page-item ">') == 5

    r = await client.get(
        "{}?page={}".format(app.url_path_for("admin:list", identity='user'), 3),
    )
    assert r.status_code == status.HTTP_200_OK

    assert (
        "Showing <span>21</span> to <span>30</span> of <span>45</span> items</p>"
        in r.text
    )
    assert r.text.count('<li class="page-item ">') == 6

    r = await client.get(
        "{}?page={}".format(app.url_path_for("admin:list", identity='user'), 5),
    )
    assert r.status_code == status.HTTP_200_OK

    assert (
        "Showing <span>41</span> to <span>45</span> of <span>45</span> items</p>"
        in r.text
    )

    # Next disabled
    assert r.text.count('<li class="page-item disabled">') == 1
    assert r.text.count('<li class="page-item ">') == 5


async def test_list_page_permission_actions(app: Starlette, client: AsyncClient) -> None:
    await User.delete.gino.status()
    await Address.delete.gino.status()
    for _ in range(10):
        user = await User.create(name="John Doe")

        await Address.create(user_id=user.id)

    r = await client.get(
        app.url_path_for("admin:list", identity='user')
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.text.count('<i class="fas fa-eye"></i>') == 10
    assert r.text.count('<i class="fas fa-trash"></i>') == 10

    r = await client.get(
        app.url_path_for("admin:list", identity='address')
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.text.count('<i class="fas fa-eye"></i>') == 10
    assert r.text.count('<i class="fas fa-pencil"></i>') == 0
    assert r.text.count('<i class="fas fa-trash"></i>') == 10


async def test_unauthorized_detail_page(app: Starlette, client: AsyncClient) -> None:
    r = await client.get(
        app.url_path_for("admin:details", identity='movie', pk=1)
    )
    assert r.status_code == status.HTTP_403_FORBIDDEN


async def test_not_found_detail_page(app: Starlette, client: AsyncClient) -> None:
    r = await client.get(
        app.url_path_for("admin:details", identity='user', pk=1)
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND


async def test_detail_page(app: Starlette, client: AsyncClient, settings: Settings) -> None:
    user = await User.create(name="Amin Alaee")

    for _ in range(2):
        await Address.create(user_id=user.id)

    r = await client.get(
        app.url_path_for("admin:details", identity='user', pk=user.id)
    )
    assert r.status_code == status.HTTP_200_OK

    assert r.text.count('<th class="w-1">Column</th>') == 1
    assert r.text.count('<th class="w-1">Value</th>') == 1
    assert r.text.count("<td>id</td>") == 1
    assert r.text.count(f"<td>{user.id}</td>") == 1
    assert r.text.count("<td>name</td>") == 1
    assert r.text.count("<td>Amin Alaee</td>") == 1
    # assert r.text.count("<td>addresses</td>") == 1
    # TODO: add relationships content 
    # assert r.text.count("<td>Address 1, Address 2</td>") == 1

    # Action Buttons
    assert r.text.count("{}{}".format(
        settings.TEST_HOST,
        app.url_path_for("admin:list", identity='user')
    )) == 2
    assert r.text.count("Go Back") == 1

    # Delete modal
    assert r.text.count("Cancel") == 1
    assert r.text.count("Delete") == 2


async def test_column_labels(app: Starlette, client: AsyncClient) -> None:
    await User.delete.gino.all()
    user = await User.create(name="Foo")
    # session.add(user)
    # await session.commit()

    # with TestClient(app) as client:
    #     r = client.get("/admin/user/list")

    r = await client.get(
        app.url_path_for("admin:list", identity='user')
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.text.count("<th>Email</th>") == 1

    # with TestClient(app) as client:
    #     r = client.get("/admin/user/details/1")

    r = await client.get(
        app.url_path_for("admin:details", identity='user', pk=user.id)
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.text.count("<td>Email</td>") == 1


async def test_delete_endpoint_unauthorized_response(app: Starlette, client: AsyncClient) -> None:
    await Movie.delete.gino.status()
    r = await client.delete(
        app.url_path_for("admin:delete", identity='movie', pk=1)
    )
    assert r.status_code == status.HTTP_403_FORBIDDEN


async def test_delete_endpoint_not_found_response(
    app: Starlette,
    client: AsyncClient
) -> None:
    await User.delete.gino.status()
    r = await client.delete(
        app.url_path_for("admin:delete", identity='user', pk=1)
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND

    users_count = await sa_gino.func.count(User.id).gino.scalar()
    assert users_count == 0

    # stmt = select(func.count(User.id))
    # result = await engine.execute(stmt)
    # assert result.scalar_one() == 0


async def test_delete_endpoint(
    app: Starlette,
    client: AsyncClient
) -> None:
    await User.delete.gino.status()
    user = await User.create(name="Bar")
    # session.add(user)
    # await session.commit()

    # users = sa_gino.func.count(User.id)
    # stmt = select(func.count(User.id))
    users_count = await sa_gino.func.count(User.id).gino.scalar()

    # result = await session.execute(stmt)
    assert users_count == 1

    # with TestClient(app) as client:
    #     r = client.delete("/admin/user/delete/1")

    # assert r.status_code == 200
    
    r = await client.delete(
        app.url_path_for("admin:delete", identity='user', pk=user.id)
    )
    assert r.status_code == status.HTTP_200_OK

    users_count = await sa_gino.func.count(User.id).gino.scalar()
    assert users_count == 0


async def test_create_endpoint_unauthorized_response(app: Starlette, client: AsyncClient) -> None:
    # with TestClient(app) as client:
    #     r = client.get("/admin/movie/create")

    # assert r.status_code == 403
    r = await client.get(
        app.url_path_for("admin:create", identity='movie')
    )
    assert r.status_code == status.HTTP_403_FORBIDDEN


async def test_create_endpoint_get_form(app: Starlette, client: AsyncClient) -> None:
    # with TestClient(app) as client:
    #     r = client.get("/admin/user/create")

    # assert r.status_code == 200
    
    r = await client.get(
        app.url_path_for("admin:create", identity='user')
    )
    assert r.status_code == status.HTTP_200_OK
    
    # # TODO: implement relationships
    # assert (
    #     '<select class="form-control" id="addresses" multiple name="addresses">'
    #     in r.text
    # )
    assert (
        '<input class="form-control" id="name" maxlength="16" name="name"'
        in r.text
    )
    assert (
        '<input class="form-control" id="email" name="email" type="text" value="">'
        in r.text
    )


async def test_create_endpoint_post_form(app: Starlette, client: AsyncClient) -> None:
    await User.delete.gino.status()
    await Address.delete.gino.status()
    
    data: dict = {"date_of_birth": "Wrong Date Format"}
    r = await client.post(
        app.url_path_for("admin:create", identity='user'), 
        data=data
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        '<div class="invalid-feedback">Not a valid date value.</div>' in r.text
    )
    
    # ====================================================================

    #
    # Creating User with  name SQLAlchemy
    data = {"name": "SQLAlchemy"}
    r = await client.post(
        app.url_path_for("admin:create", identity='user'), 
        data=data
    )
    assert r.status_code == status.HTTP_302_FOUND
    assert await sa_gino.func.count(User.id).gino.scalar() == 1  # created ONLY ONE User entity
    
    user = await User.query.where(User.name == 'SQLAlchemy').gino.first()
    assert user.name == "SQLAlchemy"
    assert user.email is None
    
    user_addresses = await get_many2one_query(user, user.addresses).gino.all()
    assert user_addresses == []
    
    #
    # Creating Address #1 of user with name SQLAlchemy
    data = {"user": user.id}
    r = await client.post(
        app.url_path_for("admin:create", identity='address'), 
        data=data
    )
    assert r.status_code == status.HTTP_302_FOUND
    assert await sa_gino.func.count(Address.id).gino.scalar() == 1  # created ONLY ONE Address entity

    address = await Address.query.where(Address.user_id==user.id).gino.first()
    assert address.user_id == user.id

    #
    # Creating User #2 with name SQLAdmin and changing relation of Address #1 to User #2 (from User #1)
    data = {"name": "SQLAdmin", "addresses": [address.id]}
    r = await client.post(
        app.url_path_for("admin:create", identity='user'), 
        data=data
    )
    assert r.status_code == status.HTTP_302_FOUND
    # created ONLY ONE User entity +1 created before (tolal: 2 entity)
    assert await sa_gino.func.count(User.id).gino.scalar() == 2
    
    user_2 = await User.query.offset(1).limit(1).gino.one()  # fetching entity User #2 
    assert user_2.name == "SQLAdmin"
    
    all_addrs = await Address.query.gino.all()
    all_users = await User.query.gino.all()

    user_2_addresses = set(await get_many2one_query(user_2, user_2.addresses).gino.all())
    assert user_2_addresses
    user_2_address = set(user_2_addresses).pop()
    assert user_2_address.id == address.id
    # TODO: implement comparing sets of gino model instances 
    # assert user_2_addresses == set([address])


async def test_list_view_page_size_options(app: Starlette, client: AsyncClient, settings: Settings) -> None:
    # with TestClient(app) as client:
    #     r = client.get("/admin/user/list")
    # assert r.status_code == 200
    
    r = await client.get(
        app.url_path_for("admin:list", identity='user')
    )
    assert r.status_code == status.HTTP_200_OK

    base_url = '{}{}'.format(
        settings.TEST_HOST,
        app.url_path_for("admin:list", identity='user')
    )
    for count in [10, 25, 50, 100]:
        assert f'{base_url}?page_size={count}' in r.text
    # assert "http://testserver/admin/user/list?page_size=10" in r.text
    # assert "http://testserver/admin/user/list?page_size=25" in r.text
    # assert "http://testserver/admin/user/list?page_size=50" in r.text
    # assert "http://testserver/admin/user/list?page_size=100" in r.text


async def test_is_accessible_method(app: Starlette, client: AsyncClient) -> None:
    # with TestClient(app) as client:
    #     r = client.get("/admin/movie/list")

    # assert r.status_code == 403
    
    r = await client.get(
        app.url_path_for("admin:list", identity='movie')
    )
    assert r.status_code == status.HTTP_403_FORBIDDEN



async def test_is_visible_method(app: Starlette, client: AsyncClient) -> None:
    await Movie.delete.gino.status()
    
    r = await client.get(
        app.url_path_for("admin:index")
    )
    assert r.status_code == status.HTTP_200_OK
    
    assert r.text.count('<span class="nav-link-title">Users</span>') == 1
    assert r.text.count('<span class="nav-link-title">Addresses</span>') == 1
    assert r.text.count("Movie") == 0


async def test_edit_endpoint_unauthorized_response(app: Starlette, client: AsyncClient) -> None:
    # with TestClient(app) as client:
    #     r = client.get("/admin/movie/edit/1")

    # assert r.status_code == 403
    
    r = await client.get(
        app.url_path_for("admin:edit", identity='movie', pk=1)
    )
    assert r.status_code == status.HTTP_403_FORBIDDEN


async def test_not_found_edit_page(app: Starlette, client: AsyncClient) -> None:
    # with TestClient(app) as client:
    #     r = client.get("/admin/user/edit/1")

    # assert r.status_code == 404
    r = await client.get(
        app.url_path_for("admin:edit", identity='user', pk=1)
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND


async def test_update_get_page(app: Starlette, client: AsyncClient) -> None:
    # await User.delete.gino.all()
    # await Address.delete.gino.all()
    user = await User.create(name="Joe")
    # session.add(user)
    # await session.flush()

    address = await Address.create(user_id=user.id)
    # session.add(address)
    # await session.commit()

    # with TestClient(app) as client:
    #     r = client.get("/admin/user/edit/1")

    # assert r.status_code == 200
    
    r = await client.get(
        app.url_path_for("admin:edit", identity='user', pk=user.id)
    )
    assert r.status_code == status.HTTP_200_OK
    
    assert (
        r.text.count(
            '<select class="form-control" id="addresses" multiple name="addresses">'
        )
        == 1
    )
    assert r.text.count(f'<option selected value="{address.id}">Address {address.id}</option>') == 1
    assert (
        r.text.count(
            'id="name" maxlength="16" name="name" type="text" value="Joe">'
        )
        == 1
    )

    r = await client.get(
        app.url_path_for("admin:edit", identity='address', pk=address.id)
    )
    assert r.status_code == status.HTTP_200_OK

    assert r.text.count('<select class="form-control" id="user" name="user">')
    assert r.text.count('<option value="__None"></option>')
    assert r.text.count(f'<option selected value="{user.id}">User {user.id}</option>')


async def test_update_submit_form(app: Starlette, client: AsyncClient) -> None:
    # await User.delete.gino.all()
    # await Address.delete.gino.all()
    
    user = await User.create(name="Joe")
    address = await Address.create(user_id=user.id)
    
    
    data = {"name": "Jack", 'addresses': []}
    r = await client.post(
        app.url_path_for("admin:edit", identity='user', pk=user.id),
        data=data
    )
    assert r.status_code == status.HTTP_302_FOUND

    user = await User.query.where(User.id==user.id).gino.one()
    assert user.name == "Jack"
    user_addresses = await get_many2one_query(user, user.addresses).gino.all()
    assert user_addresses == []
    address = await Address.query.where(Address.id==address.id).gino.one()
    assert address.user_id is None
    
    data = {"name": "Jim", "addresses": [address.id]}
    
    r = await client.post(
        app.url_path_for("admin:edit", identity='user', pk=user.id),
        data=data
    )
    user = await User.query.where(User.id==user.id).gino.one()
    assert user.name == data['name']
    assert r.status_code == status.HTTP_302_FOUND    
    address = await Address.query.where(Address.id==address.id).gino.one()
    assert address.user_id == user.id
    
    data = {"name": "Jack" * 10}
    
    r = await client.post(
        app.url_path_for("admin:edit", identity='user', pk=user.id),
        data=data
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
