import json
from fastapi import HTTPException
from sqladmin.backends.gino.models import prepare_gino_model_data, process_gino_model_post_create
from sqladmin.filters import ModelAdminParamsMixin
from sqladmin.pagination import Pagination
from sqladmin.helpers import prettify_class_name, sa_inspect, slugify_class_name
from sqladmin.forms import get_model_form
from sqladmin.exceptions import InvalidColumnError, InvalidModelError
from wtforms import Form
from starlette.requests import Request
from starlette import status 
from sqlalchemy import Column, and_, all_
from sqlalchemy.engine import RowProxy
# from sqlalchemy.sql.elements import Cast
from sqlalchemy.orm.attributes import QueryableAttribute
from sqlalchemy.sql.elements import ClauseElement, Cast
from sqlalchemy.orm.attributes import InstrumentedAttribute
from typing import (
    Any,
    ClassVar,
    Dict,
    List,
    Optional,
    OrderedDict,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
    no_type_check,
)

import anyio
from sqlalchemy import Column, func, inspect, select
import sqlalchemy as sa
from sqlalchemy.engine.base import Engine
from sqlalchemy.exc import NoInspectionAvailable

from sqlalchemy.orm import (
    ColumnProperty,
    RelationshipProperty,
    selectinload,
    sessionmaker,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.engine.result import RowProxy
from collections.abc import Mapping as PythonMapping
from sqladmin import backends
from sqladmin.backends import BackendEnum, get_used_backend
from pydantic import BaseModel
from pydantic.error_wrappers import ValidationError

used_backend: BackendEnum = get_used_backend()

if used_backend == BackendEnum.GINO:
    from sqladmin.backends.gino.models import Gino
    EngineType = ClassVar[Gino]
    from sqladmin.backends.gino.models import get_related_property_gino_loader
    from sqladmin.backends.gino.models import RelationshipProperty as GinoRelationshipProperty
    from gino.declarative import ModelType as GinoModelType
elif used_backend in (BackendEnum.SA_13, BackendEnum.SA_14):
    from sqlalchemy.ext.asyncio import AsyncEngine  # type: ignore
    EngineType = ClassVar[Union[Engine, AsyncEngine]]


__all__ = [
    "ModelAdmin",
    "BaseRelationshipsLoader",
    "BaseModelRelationshipsLoader"
]


class ModelAdminMeta(type):
    """Metaclass used to specify class variables in ModelAdmin.

    Danger:
        This class should almost never be used directly.
    """

    @no_type_check
    def __new__(mcls, name, bases, attrs: dict, **kwargs: Any):
        cls: Type["ModelAdmin"] = super().__new__(mcls, name, bases, attrs)

        model = kwargs.get("model")

        if not model:
            return cls

        mapper = mcls._get_model_mapper(model)

        pk_columns = list(mapper.primary_key)
        cls.pk_column = None
        if len(pk_columns) == 1 or kwargs.get("first_of_multiple", False):
            cls.pk_column = pk_columns[0]
        else:
            cls.pk_column = attrs.get("pk_column")
            
        # if not kwargs.get("first_of_multiple", False):
        #     assert len(pk_columns) == 1, "Multiple PK columns not supported."
        
        assert cls.pk_column is not None
        
        cls.identity = attrs.get(
            "identity", slugify_class_name(model.__name__))
        cls.model = model

        cls.name = attrs.get("name", prettify_class_name(cls.model.__name__))
        cls.name_plural = attrs.get("name_plural", f"{cls.name}s")
        cls.icon = attrs.get("icon")

        mcls._check_conflicting_options(
            ["column_list", "column_exclude_list"], attrs)
        mcls._check_conflicting_options(
            ["column_details_list", "column_details_exclude_list"], attrs
        )

        return cls

    @classmethod
    def _check_conflicting_options(mcls, keys: List[str], attrs: dict) -> None:
        if all(k in attrs for k in keys):
            raise AssertionError(f"Cannot use {' and '.join(keys)} together.")

    @classmethod
    def _get_model_mapper(mcls, model):
        try:
            return inspect(model)
        except NoInspectionAvailable:
            raise InvalidModelError(
                f"Class {model.__name__} is not a SQLAlchemy model."
            )


class BaseModelAdmin:
    def is_visible(self, request: Request) -> bool:
        """Override this method if you want dynamically
        hide or show administrative views from SQLAdmin menu structure
        By default, item is visible in menu.
        Both is_visible and is_accessible to be displayed in menu.
        """
        return True

    def is_accessible(self, request: Request) -> bool:
        """Override this method to add permission checks.
        SQLAdmin does not make any assumptions about the authentication system
        used in your application, so it is up to you to implement it.
        By default, it will allow access for everyone.
        """
        return True


def getattrwalk(root, path=[], default=None):
    if not path:
        return root
    current, *rest_path = path
    current_root = getattr(root, current, default=default)
    if rest_path:
        return walk(current_root, rest_path, default=default)
    else:
        return current_root


class ModelAdmin(BaseModelAdmin, ModelAdminParamsMixin, metaclass=ModelAdminMeta):
    """Base class for defining admnistrative behaviour for the model.

    ???+ usage
        ```python
        from sqladmin import ModelAdmin

        from mymodels import User # SQLAlchemy model

        class UserAdmin(ModelAdmin, model=User):
            can_create = True
        ```
    """

    model: ClassVar[type]
    schema: Optional[BaseModel] = None

    # Internals
    pk_column: ClassVar[Column]
    identity: ClassVar[str]
    sessionmaker: ClassVar[sessionmaker]
    engine: EngineType
    backend: BackendEnum
    async_engine: ClassVar[bool]

    # Metadata
    name: ClassVar[str] = ""
    """Name of ModelAdmin to display.
    Default value is set to Model class name.
    """

    name_plural: ClassVar[str] = ""
    """Plural name of ModelAdmin.
    Default value is Model class name + `s`.
    """

    icon: ClassVar[str] = ""
    """Display icon for ModelAdmin in the sidebar.
    Currently only supports FontAwesome icons.

    ???+ example
        ```python
        class UserAdmin(ModelAdmin, model=User):
            icon = "fas fa-user"
        ```
    """

    # Permissions
    can_create: ClassVar[bool] = True
    """Permission for creating new Models. Default value is set to `True`."""

    can_edit: ClassVar[bool] = True
    """Permission for editing Models. Default value is set to `True`."""

    can_delete: ClassVar[bool] = True
    """Permission for deleting Models. Default value is set to `True`."""

    can_view_details: ClassVar[bool] = True
    """Permission for viewing full details of Models.
    Default value is set to `True`.
    """

    # List page
    column_list: ClassVar[Sequence[Union[str, InstrumentedAttribute]]] = []
    """List of columns to display in `List` page.
    Columns can either be string names or SQLAlchemy columns.

    ???+ note
        By default only Model primary key is displayed.

    ???+ example
        ```python
        class UserAdmin(ModelAdmin, model=User):
            column_list = [User.id, User.name]
        ```
    """

    column_exclude_list: ClassVar[Sequence[Union[str,
                                                 InstrumentedAttribute]]] = []
    """List of columns to exclude in `List` page.
    Columns can either be string names or SQLAlchemy columns.

    ???+ example
        ```python
        class UserAdmin(ModelAdmin, model=User):
            column_exclude_list = [User.id, User.name]
        ```
    """

    page_size: ClassVar[int] = 10
    """Default number of items to display in `List` page pagination.
    Default value is set to `10`.

    ???+ example
        ```python
        class UserAdmin(ModelAdmin, model=User):
            page_size = 25
        ```
    """

    page_size_options: ClassVar[Sequence[int]] = [10, 25, 50, 100]
    """Pagination choices displayed in `List` page.
    Default value is set to `[10, 25, 50, 100]`.

    ???+ example
        ```python
        class UserAdmin(ModelAdmin, model=User):
            page_size_options = [50, 100]
        ```
    """

    # Details page
    column_details_list: ClassVar[Sequence[Union[str,
                                                 InstrumentedAttribute]]] = []
    """List of columns to display in `Detail` page.
    Columns can either be string names or SQLAlchemy columns.

    ???+ note
        By default all columns of Model are displayed.

    ???+ example
        ```python
        class UserAdmin(ModelAdmin, model=User):
            column_details_list = [User.id, User.name, User.mail]
        ```
    """

    column_details_exclude_list: ClassVar[
        Sequence[Union[str, InstrumentedAttribute]]
    ] = []
    """List of columns to exclude from displaying in `Detail` page.
    Columns can either be string names or SQLAlchemy columns.

    ???+ example
        ```python
        class UserAdmin(ModelAdmin, model=User):
            column_details_exclude_list = [User.mail]
        ```
    """

    column_labels: ClassVar[Dict[Union[str, InstrumentedAttribute], str]] = {}
    """A mapping of column labels, used to map column names to new names.
    Dictionary keys can be string names or SQLAlchemy columns with string values.

    ???+ example
        ```python
        class UserAdmin(ModelAdmin, model=User):
            column_labels = {User.mail: "Email"}
        ```
    """

    # Templates
    list_template: ClassVar[str] = "list.html"
    """List view template. Default is `list.html`."""

    create_template: ClassVar[str] = "create.html"
    """Create view template. Default is `create.html`."""

    details_template: ClassVar[str] = "details.html"
    """Details view template. Default is `details.html`."""

    edit_template: ClassVar[str] = "edit.html"
    """Edit view template. Default is `edit.html`."""

    def _run_query_sync(self, stmt: ClauseElement) -> Any:
        if self.backend == BackendEnum.GINO:
            raise Exception('Cant use Gino syncronously')
        with self.sessionmaker(expire_on_commit=False) as session:
            result = session.execute(stmt)
            return result.scalars().all()

    async def _run_query(self, stmt: ClauseElement) -> Any:
        if self.backend == BackendEnum.GINO:
            # return await self._select_stmt
            return await self.model.__metadata__.all(stmt)
        if self.backend in (BackendEnum.SA_14, BackendEnum.SA_13):
            if self.async_engine:
                async with self.sessionmaker(expire_on_commit=False) as session:
                    result = await session.execute(stmt)
                    return result.scalars().all()
            else:
                return await anyio.to_thread.run_sync(self._run_query_sync, stmt)

    def _add_object_sync(self, obj: Any) -> None:
        with self.sessionmaker.begin() as session:
            session.add(obj)

    def _delete_object_sync(self, obj: Any) -> None:
        with self.sessionmaker.begin() as session:
            session.delete(obj)

    def _update_modeL_sync(self, pk: Any, data: Dict[str, Any]) -> None:
        stmt = select(self.model).where(self.pk_column == pk)
        relationships = inspect(self.model).relationships

        with self.sessionmaker.begin() as session:
            result = session.execute(stmt).scalars().first()
            for name, value in data.items():
                if name in relationships and isinstance(value, list):
                    # Load relationship objects into session
                    session.add_all(value)
                setattr(result, name, value)

    async def count(self) -> int:
        # @todo: fix statement generation for count function
        # try to use get_list_statement()
        if self.backend == BackendEnum.GINO:
            ids = await self.model.select(self.pk_column.name).gino.all()
            return len(ids)
        elif self.backend in (BackendEnum.SA_14, BackendEnum.SA_13):
            stmt = select(func.count(self.pk_column))
            rows = await self._run_query(stmt)
            return rows[0]
    
    def _get_select_model_extra_columns(self, select_model: Any):
        if not isinstance(select_model, (list, tuple, )):
            select_model = [select_model]
            
        for m in select_model:
            for key in dir(m):
                ecol = getattr(m, key, None) 
                if isinstance(ecol, (Cast, )):
                    yield ecol, key
    
    def _select_stmt(self, *args, **kwargs):
        if used_backend == BackendEnum.GINO:
            return select(*args, **kwargs)
        elif used_backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
            return self.model.__metadata__.select(*args, **kwargs)
    
    async def get_list_statement(self, *, select_model, order_by, page_size, page, where=None, select_from=None):
        if not isinstance(select_model, (list, tuple, )):
            select_model = [select_model]
        select_full = [*select_model]
        for ecol, key in self._get_select_model_extra_columns(select_model):
            select_full.append(ecol.label(key))
        stmt = self._select_stmt(select_full)
        if select_from is not None:
            stmt = stmt.select_from(select_from)
        where = [w for w in ([where] + (self.get_list_params_where() or [])) if w is not None]
        if len(where) > 1:
            stmt = stmt.where(and_(*where))
        elif len(where) == 1:
            stmt = stmt.where(where[0])
        order_by = self.get_list_params_order_by() or order_by
        stmt = stmt.order_by(*order_by).limit(page_size).offset((page - 1) * page_size)
        return stmt

    async def get_query_order_by(self, *args, **kwargs):
        return [self.pk_column]
    
    async def get_query_where(self, *args, **kwargs):
        return None
    
    async def get_query_select(self, *args, **kwargs):
        return self.model
    
    async def get_query_select_from(self, *args, **kwargs):
        return None

    async def list(self, page: int, page_size: int, **kwargs) -> Pagination:
        page_size = min(page_size or self.page_size,
                        max(self.page_size_options))

        count = await self.count()
        stmt = await self.get_list_statement(
            select_model=await self.get_query_select(**kwargs.get('select', {})),
            select_from=await self.get_query_select_from(**kwargs.get('select_from', {})), 
            order_by = await self.get_query_order_by(**kwargs.get('order_by', {})),  
            where=await self.get_query_where(**kwargs.get('where', {})),
            page_size=page_size, 
            page=page,
        )

        if used_backend == BackendEnum.GINO:
            for label, attr in self.get_list_columns():
                if isinstance(attr, RelationshipProperty):
                    loader = self._get_related_gino_loader(attr)
                    stmt = stmt.execution_options(loader=loader)
        elif used_backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
            for _, attr in self.get_list_columns():
                if isinstance(attr, RelationshipProperty):
                    stmt = stmt.options(selectinload(self.get_key(attr)))
        
        # sa_gino: Gino = self.engine
        # test = await sa_gino.scalar(select([sa_gino.JSON.NULL]))
        
        rows = await self._run_query(stmt)
        pagination = Pagination(
            rows=rows,
            page=page,
            page_size=page_size,
            count=count,
        )

        return pagination

    def _try_cast_pk(self, pk):
        try:
            if not isinstance(pk, self.pk_column.type.python_type):
                pk = self.pk_column.type.python_type(pk)
        except NotImplementedError:
            pass
        return pk

    def _get_related_gino_loader(self, attr):
        return get_related_property_gino_loader(self.model, self.pk_column, self.get_key(attr, obj=self.model), attr)

    def get_model_pk_select_statement(self, select_model, pk_column, pk_column_value):
        return select(select_model).where(pk_column == pk_column_value)

    async def get_edit_context(self, base_context, **kwargs) -> dict:
        return base_context
    
    async def get_model_by_pk(self, value: Any) -> Any:
        # cast value to column pk_column type
        try:
            if not isinstance(value, self.pk_column.type.python_type):
                value = self.pk_column.type.python_type(value)
        except NotImplementedError:
            pass
        stmt = self.get_model_pk_select_statement(
            self.model, self.pk_column, value)

        if used_backend == BackendEnum.GINO:
            for label, attr in self.get_details_columns():
                if isinstance(attr, RelationshipProperty):
                    loader = self._get_related_gino_loader(attr)
                    stmt = stmt.execution_options(loader=loader)
        elif used_backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
            for _, attr in self.get_details_columns():
                if isinstance(attr, RelationshipProperty):
                    stmt = stmt.options(selectinload(self.get_key(attr)))

        rows = await self._run_query(stmt)
        if rows:
            return rows[0]
        return None

    def get_key(self, attr: Union[Column, ColumnProperty, RelationshipProperty], obj: Optional[type] = None, default: Any = None):
        if isinstance(attr, Column):
            return attr.name
        elif isinstance(attr, ColumnProperty):
            return attr.columns[0].name
        else:
            try:
                if hasattr(attr, 'key'):
                    key = attr.key
                elif obj is not None:
                    key = self.get_attr_key_by_obj(obj, attr)
                else:
                    return default
            except AttributeError:
                return default
            return key

    def get_attr_key_by_obj(self, obj: type, attr: Union[Column, ColumnProperty, RelationshipProperty]):
        for ikey, iattr in obj.__dict__.items():
            if iattr == attr:
                return ikey
        raise AttributeError(f'Object {obj} dont have attribute {attr}')

    def get_attr_value(
        self, obj: type, attr: Union[Column, ColumnProperty, RelationshipProperty],
        placeholder_not_implemented: Any = None,
        placeholder_none: Any = None,
        placeholder_no_attr: Any = None,
    ) -> Any:
        if isinstance(attr, Column):
            if isinstance(obj, RowProxy):
                try:
                    return obj[attr]
                except Exception as e:
                    # attr.table.element.name
                    return placeholder_none
            else:
                return getattr(obj, attr.name)
        elif isinstance(attr, ColumnProperty):
            return getattr(obj, attr.columns[0].name)
        elif isinstance(attr, str):
            *path, key = attr.split('.')
            if len(path) == 1 and hasattr(obj, key):
                return getattr(obj, key, placeholder_none) 
            model, *path = path
            
            try:
                return getattrwalk(obj, [*path, key])
            except AttributeError:
                return placeholder_none
            mapper = sa_inspect(model)
            model_class = mapper.class_
            attr = getattr(model_class, key)
            
            return getattr(obj, key, None)
        else:
            try:
                if hasattr(attr, 'key'):
                    key = attr.key
                else:
                    key = self.get_attr_key_by_obj(obj, attr)
            except AttributeError:
                return placeholder_no_attr

            # remove this!
            try:
                if isinstance(obj, RowProxy):
                    value = getattr(obj, key, placeholder_no_attr)
                elif isinstance(attr, (RelationshipProperty, )):
                    value = getattr(obj, key, placeholder_no_attr)
                else:
                    value = getattr(obj, key, placeholder_no_attr)

            except NotImplementedError:
                value = placeholder_not_implemented

            if isinstance(value, list):
                return ", ".join(map(str, value))
            return value


    def get_attr_value_display(
        self, obj: type, attr: Union[Column, ColumnProperty, RelationshipProperty],
        placeholder_not_implemented: Any = 'Not implemented',
        placeholder_none: Any = '-',
        placeholder_no_attr: Any = 'No attr',
    ) -> Any:
        value = self.get_attr_value(
            obj=obj, 
            attr=attr, 
            placeholder_none=placeholder_none,
            placeholder_no_attr=placeholder_no_attr,
            placeholder_not_implemented=placeholder_not_implemented,
        )
        if value is None:
            return placeholder_none
        return value


    def get_model_attr(
        self, attr: Union[str, InstrumentedAttribute, Column, RelationshipProperty]
    ) -> Union[ColumnProperty, RelationshipProperty]:
        assert attr is not None
        assert isinstance(attr, (str, InstrumentedAttribute, RelationshipProperty,
                          Column, property, hybrid_property))

        if isinstance(attr, str):
            key = attr
        elif isinstance(attr, Column):
            key = attr.name
        # elif isinstance(attr, RelationshipProperty):
        #     # if hasattr(attr, 'parent'):
        #     #     attr.set_parent()
        #     key = attr.name
        elif isinstance(attr, (property, RelationshipProperty)):
            model_attr_match = [
                a
                for a in dir(self.model)
                if hasattr(self.model, a) and getattr(self.model, a) == attr
            ]
            key = model_attr_match[0]
            if not hasattr(attr, 'key') or attr.key is None:
                attr.key = key
        # elif isinstance(attr, QueryableAttribute):
        #      # TODO: QueryableAttribute key
        #     model_attr_match = [
        #         a
        #         for a in dir(self.model)
        #         if getattr(self.model, a, None) == attr
        #     ]
        #     key = model_attr_match[0]
        #     if not hasattr(attr, 'key') or attr.key is None:
        #         attr.key = key
        elif hasattr(attr, 'prop') and isinstance(attr.prop, ColumnProperty):
            key = attr.name
        elif hasattr(attr, 'prop') and isinstance(attr.prop, (RelationshipProperty, )):
            key = attr.prop.key
        try:
            insp = inspect(self.model)
            hasattr(insp, 'attrs')  # DO NOT REMOVE
            insp.attrs
            return insp.attrs[key]
        except KeyError:
            try:
                attr = str(attr)
            except AttributeError as e:
                # raise e
                attr = '*attr*'
            raise InvalidColumnError(
                f"Model '{self.model.__name__}' has no attribute '{attr}'."
            )

    def get_model_attributes(self) -> List[Column]:
        attrs = inspect(self.model).attrs
        if isinstance(attrs, OrderedDict):
            return list(attrs.values())
        if attrs is None:
            print()
            return list()
        return list(attrs)

    def get_list_columns(self) -> List[Tuple[str, Column]]:
        """Get list of columns to display in List page."""

        column_list = getattr(self, "column_list", None)
        column_exclude_list = getattr(self, "column_exclude_list", None)

        if column_list:
            attrs = [self.get_model_attr(attr) for attr in self.column_list]
        elif column_exclude_list:
            exclude_columns = [
                self.get_model_attr(attr) for attr in column_exclude_list
            ]
            all_attrs = self.get_model_attributes()
            attrs = list(set(all_attrs) - set(exclude_columns))
        else:
            pk_attr = getattr(self.model, self.pk_column.name)
            if hasattr(pk_attr, 'prop'):
                attrs = [pk_attr.prop]
            else:
                attrs = [pk_attr]

        labels = self.get_column_labels()
        return [(labels.get(attr, self.get_key(attr)), attr) for attr in attrs]
    
    # def get_list_filters

    def get_details_columns(self) -> List[Tuple[str, Column]]:
        """Get list of columns to display in Detail page."""

        column_details_list = getattr(self, "column_details_list", None)
        column_details_exclude_list = getattr(
            self, "column_details_exclude_list", None)

        if column_details_list:
            attrs = [self.get_model_attr(attr) for attr in column_details_list]
        elif column_details_exclude_list:
            exclude_columns = [
                self.get_model_attr(attr) for attr in column_details_exclude_list
            ]
            all_attrs = self.get_model_attributes()
            attrs = list(set(all_attrs) - set(exclude_columns))
        else:
            attrs = self.get_model_attributes()

        labels = self.get_column_labels()

        lst = []

        for attr in attrs:
            default = self.get_key(attr, default='key_not_found')
            # default = getattr(attr, 'key', 'key_not_found')
            keyname = labels.get(attr, default)
            lst.append((keyname, attr, ))

        return lst
        # return [(labels.get(attr, getattr(attr, 'key', 'key_not_found')), attr) for attr in attrs]

    def get_column_labels(self) -> Dict[Column, str]:
        return {
            self.get_model_attr(column_label): value
            for column_label, value in self.column_labels.items()
        }

    async def delete_model(self, obj: Any) -> None:
        if self.backend == BackendEnum.GINO:
            try:
                await obj.delete()
            except Exception as e:
                pk_value = self._try_cast_pk(getattr(obj, self.pk_column.name))
                await self.model.delete.where(
                    self.pk_column == pk_value).gino.status()
                
        elif self.backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
            if self.async_engine:
                async with self.sessionmaker.begin() as session:
                    await session.delete(obj)
            else:
                await anyio.to_thread.run_sync(self._delete_object_sync, obj)

    async def init_model_instance(self, data:Dict, **kwargs):
        if self.schema is not None:
            try:
                _data = {}
                for k, v in data.items():
                    if v is None:
                        continue
                    if k == self.pk_column.key:
                        continue
                    if isinstance(v, str):
                        if v.isnumeric():
                            v = int(v)
                    _data[k] = v
                data = _data
                data = self.schema.parse_obj(data).dict()
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
        if used_backend == BackendEnum.GINO:
            data, non_cols_data = await prepare_gino_model_data(self.model, data)
        model = self.model(**data)
        model._post_create_model_data = non_cols_data
        return model

    async def insert_model(self, obj: type, obj_extra: Optional[Dict] = None) -> Any:
        if self.backend == BackendEnum.GINO:
            if getattr(obj.__class__, '__class__', None) == GinoModelType:
                await obj.create()
                post_create_data = getattr(
                    obj, '_post_create_model_data', None)
                if post_create_data:
                    await process_gino_model_post_create(instance=obj, data=post_create_data)
                await self.post_insert_model(obj=obj, obj_extra=obj_extra)
                return obj
            else:
                if not isinstance(obj, PythonMapping):
                    obj: dict = obj.to_dict()
                    obj.pop(self.pk_column.key, None)
                obj = await self.model.create(**obj)
                post_create_data = getattr(
                    obj, '_post_create_model_data', None)
                if post_create_data:
                    await process_gino_model_post_create(instance=obj, data=post_create_data)
                return obj
        elif self.backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
            if self.async_engine:
                async with self.sessionmaker.begin() as session:
                    session.add(obj)
            else:
                await anyio.to_thread.run_sync(self._add_object_sync, obj)
    
    async def post_insert_model(self, obj, obj_extra):
        pass
    
    async def prepare_update_data(
        self, 
        # pk: Any, 
        # data: Dict[str, Any], 
        # files:Optional[Dict]=None,
        **kwargs,
    ) -> Dict:
        data = await self.schema_cast(**kwargs)
        return data
    
    async def schema_cast(
        self, *,
        data: Dict,
        form: Form,
        request: Request,
        **kwargs,
    ) -> Dict:
        if hasattr(self, 'schema'):
            # req_body = await request.body()
            # pydantic = self.schema.parse_raw(req_body)
            # schema.parse_obj()
            # data = self.model(**data).to_dict()
            # pydantic_model = form.as_pydantic(self.schema)
            # data = pydantic_model.dict()
            pass
        return data
    
    async def update_model(self, pk: Any, data: Dict[str, Any]) -> None:
        extra_data_keys = await self.get_scaffold_form_extra()
        extra_data = { k: v for k, v in data.items() if k in extra_data_keys}
        data = { k: v for k, v in data.items() if k not in extra_data_keys}
        if self.backend == BackendEnum.GINO:
            # data = self.model(**data).to_dict()
            _data = {}
            for k, v in data.items():
                if v is None or v == '':
                    continue
                if k == self.pk_column.key:
                    continue
                if isinstance(v, str):
                    if v.isnumeric():
                        v = int(v)
                    else: 
                        try:
                            v = json.loads(v)
                        except Exception as e:
                            pass  # TODO: FIX THIS!!!!!!!!!!
                _data[k] = v
            data = _data
            pk = self._try_cast_pk(pk)
            data[self.pk_column.name] = pk
            if self.schema is not None:
                # schema.parse_obj()
                # parse_data = {**data, **non_cols_data}
                try:
                    data = self.schema.parse_obj(data).dict()
                except ValidationError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=str(exc),
                    ) from exc
            else:
                # model_data = self.model(**data).to_dict()
                pass
            data, non_cols_data = await prepare_gino_model_data(self.model, data)
            _data = {}
            for k, v in data.items():
                # if v is None or v == '':
                #     continue
                
                # if k == self.pk_column.key:
                #     continue
                # if isinstance(v, str):
                #     if v.isnumeric():
                #         v = int(v)
                #     else: 
                #         try:
                #             v = json.loads(v)
                #         except Exception as e:
                #             pass  # TODO: FIX THIS!!!!!!!!!!
                _data[k] = v
            data = _data
            await self.model.update.values(**data).where(
                self.pk_column == pk).gino.status()
            await process_gino_model_post_create(data=non_cols_data, instance_id=pk, Model=self.model)
        elif self.backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
            if self.async_engine:
                stmt = select(self.model).where(self.pk_column == pk)
                relationships = inspect(self.model).relationships

                for name in relationships.keys():
                    stmt = stmt.options(selectinload(name))

                async with self.sessionmaker.begin() as session:
                    result = await session.execute(stmt)
                    result = result.scalars().first()
                    for name, value in data.items():
                        if name in relationships and isinstance(value, list):
                            # Load relationship objects into session
                            session.add_all(value)
                        setattr(result, name, value)
            else:
                await anyio.to_thread.run_sync(self._update_modeL_sync, pk, data)
    
    async def get_scaffold_form_extra(self):
        return dict()
    
    async def get_field_options_objects(self, *args, **kwargs):
        return None
    
    async def scaffold_form(self) -> Type[Form]:
        return await get_model_form(
            model=self.model, 
            engine=self.engine, 
            backend=self.backend, 
            extra_fields=await self.get_scaffold_form_extra(),
            objects_getter=self.get_field_options_objects,
            model_admin=self,
        )
