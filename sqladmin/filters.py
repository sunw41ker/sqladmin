from csv import DictReader
from uuid import UUID, uuid4
from functools import lru_cache
from itertools import chain
from types import FunctionType
from typing import ClassVar, Iterator, Tuple, Type, Union, Set
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, OrderedDict, Set, Union
from urllib.parse import urlencode, quote_plus, parse_qs, parse_qsl
from loguru import logger
# from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import ColumnProperty, RelationshipProperty
from sqlalchemy import Column
import sqlalchemy as sa
from sqlalchemy_utils.types import ChoiceType
from sqladmin.backends.gino.models import find_model_class
from sqladmin.forms import ModelConverter
from sqladmin.helpers import sa_inspect
from pydantic import BaseModel
from starlette.requests import Request
from wtforms import Form, StringField, HiddenField, SubmitField
from sqladmin.fields import Select2Field
from .columns import BaseModelAdminColumn
from .utils.enum import LocalizedEnum


URL_KEY_SEPARATOR = '__'
URL_ARRAY_SEPARATOR = ','


class FunctionalEnum(LocalizedEnum):
    def fn(self, field, arg, **kwargs):
        return getattr(self, f'_fn_{self.value}')(field, arg, **kwargs)


class ClauseEnum(str, FunctionalEnum):
    ILIKE = 'ilike', 'Содержит'
    EXACT = 'exact', 'Точно равно'
    GT = 'gt', 'Больше'
    GTE = 'gte', 'Больше или равно'
    LT = 'lt', 'Меньше'
    LTE = 'lte', 'Меньше или равно'
    # IN = 'in'
    # NOT_IN = 'notin'

    def _fn_exact(self, field, arg):
        return field == arg

    def _fn_ilike(self, field, arg: str):
        if isinstance(arg, str):
            return field.ilike(f'%{arg.strip()}%')
        
        logger.warning(f"Non str ilike statement {arg=} for {field=}. Ignoring.")
        return True  # sqlalchemy will ignore this arg in filter 

    def _fn_in(self, field, arg):
        return field.in_(arg)

    def _fn_notin(self, field, arg):
        return field.notin_(arg)

    def _fn_gt(self, field, arg):
        return field > arg

    def _fn_gte(self, field, arg):
        return field >= arg

    def _fn_lt(self, field, arg):
        return field < arg

    def _fn_lte(self, field, arg):
        return field <= arg


class BaseListParamItem(BaseModel):
    _IDENTITY_FIELDS = ('model', 'field', )
    model: Union[str, None]
    model_class: Optional[Type]
    field: str
    field_prop: Optional[Any]

    @property
    def identity(self) -> str:
        base = self.dict()
        return self.get_identity(**base)

    @identity.setter
    def _identity_setter(self, value: str) -> None:
        self.model, self.field = value.split(URL_KEY_SEPARATOR)

    @classmethod
    def get_identity(cls, **kwargs):
        return URL_KEY_SEPARATOR.join(
            [str(kwargs[attr])
             for attr in cls._IDENTITY_FIELDS
             if kwargs.get(attr, None) is not None]
        )

    def match(self, **kwargs):
        for k, v in kwargs.items():
            if getattr(self, k, None) != v:
                return False
        return True

    def get_prop(self, default=None):
        mapper = sa_inspect(self.model)
        return getattr(mapper.class_, self.field, default)

    def get_class_n_prop(
        self,
        default: Optional[Any] = None
    ) -> Tuple[Type, Union[ColumnProperty, RelationshipProperty]]:
        if self.model_class is None:
            mapper = sa_inspect(self.model)
            self.model_class = mapper.class_
        if self.field_prop is None:
            self.field_prop = getattr(mapper.class_, self.field, default)
        return self.model_class, self.field_prop

    def get_stmt(self, *, default=None, **kwargs):
        raise NotImplementedError()


class ListFilterItem(BaseListParamItem):
    _URL_QPARAMS_IDENTITY_FIELDS = ('model', 'field', 'clause', )
    clause: ClauseEnum = ClauseEnum.EXACT
    operand: Optional[Any] = None

    def get_full_clause(self, **kwargs) -> str:
        base = self.dict(**kwargs)
        key = [base[attr]
               for attr in self._URL_QPARAMS_IDENTITY_FIELDS
               if base.get(attr, None) is not None]
        return URL_KEY_SEPARATOR.join(key)

    def as_url_dict_param(self, **kwargs) -> Dict:
        base = self.dict(**kwargs)
        key = [base[attr]
               for attr in self._URL_QPARAMS_IDENTITY_FIELDS
               if base.get(attr, None) is not None]
        key = URL_KEY_SEPARATOR.join(key)
        return {key: base.get('operand', None)}

    def _update_operand_type(self):
        model_class, prop = self.get_class_n_prop()
        if prop.type.python_type != type(self.operand):
            self.operand = prop.type.python_type(self.operand)

    @classmethod
    def from_url_dict_params(cls, url_dict_params: Dict[str, Any]):
        data = {}
        key, data['operand'] = next(iter(url_dict_params.items()))
        # if operand_type is not None and not isinstance(data['operand'], operand_type) :
        #     data['operand'] = operand_type(data['operand'])
        if len(key.split(URL_KEY_SEPARATOR)) != 3:
            raise AttributeError()
        data['model'], data['field'], data['clause'] = key.split(URL_KEY_SEPARATOR)
        inst = cls(**data)
        inst._update_operand_type()
        return inst

    def __eq__(self, operand) -> bool:
        # if not isinstance(operand, ListFilterItem):
        #     return False
        return (
            self.model == operand.model
            and self.field == operand.filter
            # and self.clause == operand.clause
            # and self.operand == operand.operand
        )

    def get_stmt(self, *, default=None):
        prop = self.get_prop(default=default)
        return self.clause.fn(prop, self.operand)


class SortDirectionEnum(str, FunctionalEnum):
    ASCENDING = 'a', 'По возрастанию'
    DESCENDING = 'd', 'По убыванию'

    def _fn_a(self, field, arg=None):
        return field

    def _fn_d(self, field, arg=None):
        return field.desc()


class ListOrderingItem(BaseListParamItem):
    _URL_QPARAMS_IDENTITY_FIELDS = ('model', 'field', 'direction', )
    direction: SortDirectionEnum = SortDirectionEnum.ASCENDING

    def as_url_param(self, **kwargs):
        base = self.dict(**kwargs)
        key = [base[attr]
               for attr in self._URL_QPARAMS_IDENTITY_FIELDS
               if base.get(attr, None) is not None]
        return URL_KEY_SEPARATOR.join(key)

    @classmethod
    def from_url_param(cls, url_param: str):
        data = {}
        data['model'], data['field'], data['direction'] = url_param.split(
            URL_KEY_SEPARATOR)
        return cls(**data)

    def get_stmt(self, default=None):
        prop = self.get_prop(default=default)
        if self.direction == SortDirectionEnum.DESCENDING:
            return prop.desc()
        return prop


class ListViewParams(BaseModel):
    _ORDERING_PARAMS_KEY = 'o'
    filters: List[ListFilterItem]
    ordering: List[ListOrderingItem]

    def as_url_params(self, **kwargs):
        filters = {}
        for filter_item in self.filters:
            filters.update(filter_item.as_url_dict_param(**kwargs))
        return {
            'filters': filters,
            'ordering': [i.as_url_param(**kwargs) for i in self.ordering],
        }

    def get_requests_query_params(self, quote_via=quote_plus, doseq=True, **kwargs):
        params = self.as_url_params(**kwargs)
        url_params = {}
        if params.get('filters'):
            url_params.update(params.get('filters'))
        if params.get('ordering'):
            url_params[self._ORDERING_PARAMS_KEY] = URL_ARRAY_SEPARATOR.join(
                params['ordering'])
        # params = {**params.get('filters', {}), self._ORDERING_PARAMS_KEY: params.get('ordering', [])}
        return url_params

    def urlencode(self, quote_via=quote_plus, doseq=True, **kwargs):
        url_params = self.get_requests_query_params(
            quote_via=quote_via, doseq=doseq, **kwargs)
        return urlencode(url_params, quote_via=quote_via, doseq=doseq)

    @classmethod
    def from_url_str(cls, url_params_str: str):
        def val_prepare(key, v):
            if isinstance(v, list):
                lenv = len(v)
                if lenv == 1:
                    v = v[0]
                elif lenv == 0:
                    v = None

            if key == cls._ORDERING_PARAMS_KEY:
                if isinstance(v, str):
                    if URL_ARRAY_SEPARATOR in v:
                        v = v.split(URL_ARRAY_SEPARATOR)
                    else:
                        v = [v]
            return v
        params = {
            k: val_prepare(k, v)
            for k, v in parse_qs(url_params_str).items()
            if k not in ('page', 'page_size', )
        }
        # ordering_data = params.get(cls._ORDERING_PARAMS_KEY, [])
        # if not isinstance(ordering_data, str):
        #     [
        #         ListOrderingItem.from_url_param(oi)
        #         for oi in params.get(cls._ORDERING_PARAMS_KEY, [])
        #     ]
        data = {
            'filters': [
                ListFilterItem.from_url_dict_params({key: val})
                for key, val in params.items()
                if key != cls._ORDERING_PARAMS_KEY
            ],
            'ordering': [
                ListOrderingItem.from_url_param(oi)
                for oi in params.get(cls._ORDERING_PARAMS_KEY, [])
            ]
        }
        return cls(**data)

    def override(self, item: Union[ListFilterItem, ListOrderingItem], remove=False):
        params = ListViewParams(**self.dict())
        if item is None:
            return params
        if remove:
            if isinstance(item, ListFilterItem):
                params.filters = [
                    f for f in params.filters if f.identity != item.identity]
            elif isinstance(item, ListOrderingItem):
                params.ordering = [
                    o for o in params.ordering if o.identity != item.identity]
            else:
                raise TypeError()
        else:
            if isinstance(item, ListFilterItem):
                params.filters = [
                    item] + [f for f in params.filters if f.identity != item.identity]
            elif isinstance(item, ListOrderingItem):
                params.ordering = [
                    item] + [o for o in params.ordering if o.identity != item.identity]
            else:
                raise TypeError()
        return params

    def get_filter(self, **kwargs) -> Optional[ListFilterItem]:
        match = [f for f in self.filters if f.match(**kwargs)]
        if match:
            return match[0]
        return None

    def get_ordering(self, **kwargs) -> Optional[ListOrderingItem]:
        match = [o for o in self.ordering if o.match(**kwargs)]
        if match:
            return match[0]
        return None

    def get_item(self, ItemType, **kwargs) -> Union[ListFilterItem, ListOrderingItem, None]:
        if ItemType == ListFilterItem:
            return self.get_filter(**kwargs)
        elif ItemType == ListOrderingItem:
            return self.get_ordering(**kwargs)
        raise TypeError()


WHERE_ITEM_TYPE = Tuple[ClauseEnum, Optional[Any]]


class FilteredOrderedAdminColumn(BaseModelAdminColumn):
    _MODEL_FIELD_PATH_SEPARATOR = '.'
    _MODEL_FIELD_SUBPATH_SEPARATOR = ':'
    _PARAMS_SEPARATOR = BaseModelAdminColumn._IDENTITY_SEPARATOR
    _SORT_KEY = 'o'

    where: List[WHERE_ITEM_TYPE] = []
    sort: Optional[SortDirectionEnum] = None

    @property
    def _where_clauses(self):
        return [w[0] for w in self.where]

    def where_stmt(self, *, default=None, **kwargs):
        for clause, operand in self.where:
            yield clause.fn(self.field_prop, operand, **kwargs)

    def sort_stmt(self, *, default=None, **kwargs):
        if self.sort:
            yield self.sort.fn(self.field_prop, arg=None)

    def cast(self, value):
        is_convertable = False
        try:
            is_convertable = self.field_prop.type.python_type == type(value)
        except Exception as e:
            pass
        
        if is_convertable:
            return self.field_prop.type.python_type(value)
        return sa.func.cast(value, self.field_prop.type)

    def _cast_operands(self):
        self.where = [
            (cl, self.cast(operand))
            for cl, operand in self.where
        ]

    @classmethod
    def _get_form_key_prefix(cls, **identity_kwargs):
        return cls.get_identity(**identity_kwargs) + cls._PARAMS_SEPARATOR

    @property
    def _form_key_prefix(self):
        return self._get_form_key_prefix(**self.get_identity_dict())

    def is_form_key_match(self, form_key: str):
        return form_key.startswith(self._form_key_prefix)

    @classmethod
    def parse_field_path(
        cls, 
        identity: str
    ) -> Tuple[Optional[List[str]], str, Optional[List[str]]]:
        parts = identity.split(cls._MODEL_FIELD_SUBPATH_SEPARATOR)
        parts_len = len(parts)
        if parts_len == 1:
            *path, field = identity.split(cls._MODEL_FIELD_PATH_SEPARATOR)
            return path, field, None
        elif parts_len == 2:
            pathnfield, subpath = parts
            *path, field = pathnfield
            return path, field, subpath.split(cls._MODEL_FIELD_PATH_SEPARATOR)
        raise AttributeError(f'Too much parts of field path: {identity}')
    
    @classmethod
    def from_identity(cls, identity: Any, **data: Dict):
        # Union[ColumnProperty, RelationshipProperty]
        model = None
        field = None
        label = None
        model_class = None
        if isinstance(identity, str):
            # TODO: add string column configuration
            # *path, field = identity.split(cls._MODEL_FIELD_PATH_SEPARATOR)
            path, field, subpath = cls.parse_field_path(identity)
            # TODO: add subpath support (for jsonb fields
            if path:
                model = path[-1]
                field = field
            else:
                raise AttributeError(f'Bad column identity: {identity}')
            raise NotImplemented()
        elif isinstance(identity, tuple):  # admin column config
            label, col, *_ = identity
            if _:
                raise AttributeError(f'Bad column identity: {identity}')
            if isinstance(col, (Column, ColumnProperty, RelationshipProperty, )):    
                model_class = find_model_class(col)
                model, field = model_class.__name__, col.key
            elif isinstance(col, str):
                path, field, subpath = cls.parse_field_path(col)
                # *path, field = col.split(cls._MODEL_FIELD_PATH_SEPARATOR)
                # TODO: add subpath support (for jsonb fields)
                if path:
                    model = path[-1]
                    field = field
                else:
                    raise AttributeError(f'Bad column identity: {identity}')
                model_class_mapper = sa_inspect(cls._MODEL_FIELD_PATH_SEPARATOR.join(path))
                model_class = model_class_mapper.class_
            elif getattr(col, 'class_', None) is not None and getattr(col, 'key', None) is not None:
                model_class = col.class_
                field = col.key
                model = model_class.__name__
                # path, field, subpath = cls.parse_field_path(col)
                # *path, field = col.split(cls._MODEL_FIELD_PATH_SEPARATOR)
                # TODO: add subpath support (for jsonb fields)
                # if path:
                #     model = path[-1]
                #     field = field
                # else:
                    # raise AttributeError(f'Bad column identity: {identity}')
                # model_class_mapper = sa_inspect(cls._MODEL_FIELD_PATH_SEPARATOR.join(path))
                # model_class = model_class_mapper.class_
            
        identity_dict = dict(model=model, field=field)

        for ic in BaseModelAdminColumn._IDENTITY_FIELDS:
            if identity_dict.get(ic) is None :
                raise AttributeError(f'Identity recognition failed : {ic} not found.')

        if label is None:
            label = field.replace('_', ' ').capitalize()

        return cls.from_form_data(
            **data,
            model_class=model_class,
            identity_dict=identity_dict,
            label=label
        )

    @classmethod
    def from_form_data(cls, identity_dict: Dict = {}, label: Optional[str] = None, model_class=None, key_must_starts_with=None, **data):
        key_must_starts_with = key_must_starts_with or cls._get_form_key_prefix(
            **{f: identity_dict[f] for f in BaseModelAdminColumn._IDENTITY_FIELDS}
        )
        key_slice_len = len(key_must_starts_with)
        form_filter_clauses = {
            key[key_slice_len:]: v
            for key, v in data.items()
            if key.startswith(key_must_starts_with)}
        form_sort = data.get(cls._SORT_KEY, [])
        if not isinstance(form_sort, (list, tuple, )):
            form_sort = [form_sort]
        form_sort = [
            key[key_slice_len:]
            for key in form_sort
            if key.startswith(key_must_starts_with)
        ]
        data = {}
        data['where'] = [
            (ClauseEnum(clause_key), operand_form_value)
            for clause_key, operand_form_value in form_filter_clauses.items()
        ]
        if form_sort:
            data['sort'] = form_sort[0]

        instance = cls(**data, **identity_dict, label=label, model_class=model_class)
        instance._cast_operands()
        return instance

    @classmethod
    def _get_form_data_key(cls, value: Enum, key_prefix: str):
        if isinstance(value, Enum):
            val = value.value
        else:
            val = value
        if key_prefix.endswith(cls._PARAMS_SEPARATOR):
            return f'{key_prefix}{val}'
        return f'{key_prefix}{cls._PARAMS_SEPARATOR}{val}'

    @classmethod
    def _get_operand_form_value(cls, value):
        return value

    @classmethod
    def where_form_data_of(cls, where: List[WHERE_ITEM_TYPE], key_prefix=None, **identity_kwargs) -> Iterator[Tuple[str, Any]]:
        key_prefix = key_prefix or cls._get_form_key_prefix(**identity_kwargs)
        for clause, operand in where:
            yield (
                cls._get_form_data_key(clause, key_prefix),
                cls._get_operand_form_value(operand)
            )

    @property
    def where_form_data(self) -> Iterator[Tuple[str, Any]]:
        key_prefix = self._form_key_prefix
        return self.where_form_data_of(self.where, key_prefix=key_prefix)

    @classmethod
    def form_data_of(
        cls, *,
        where: List[WHERE_ITEM_TYPE] = [],
        sort: Optional[SortDirectionEnum] = None,
        key_prefix=None, **identity_kwargs
    ) -> Iterator[Tuple[str, Any]]:
        key_prefix = key_prefix or cls._get_form_key_prefix(**identity_kwargs)
        for wfd in cls.where_form_data_of(where, key_prefix=key_prefix):
            yield wfd
        if sort is not None:
            yield (
                cls._SORT_KEY,  # without prefix, cause common key for multiple columns (prefixes)
                key_prefix + str(sort.value)
            )

    @property
    def form_data(self) -> Iterator[Tuple[str, Any]]:
        key_prefix = self._form_key_prefix
        return self.form_data_of(where=self.where, sort=self.sort, key_prefix=key_prefix)

    def get_label(self, enum_opt):
        return str(enum_opt)

    def _in_where(self, clause: ClauseEnum):
        for w in self.where:
            if w[0] == clause:
                return True
        return False

    def _is_where_clause_active(self, clause: ClauseEnum):
        return self._in_where(clause)

    @property
    def _is_where_active(self):
        return len(self.where) > 0

    def _urlencode(self, quote_via=quote_plus, doseq=False, **url_params):
        return urlencode(url_params, quote_via=quote_via, doseq=doseq)

    def _get_base_options(
        self,
        OptionsEnum: Enum,
        get_label: FunctionType,
        is_active: FunctionType,
    ) -> Iterator[Dict]:
        form_key_prefix = self._form_key_prefix
        for oi in OptionsEnum:
            yield {
                'value': oi,
                'form_name': self._get_form_data_key(oi, form_key_prefix),
                'label': get_label(oi),
                'is_active': is_active(oi)
            }
            
    def _get_where_options(
        self,
        get_label: FunctionType,
    ) -> Iterator[Dict]:
        return self._get_base_options(ClauseEnum, get_label, self._is_where_clause_active)

    def _get_sort_options(
        self,
        get_label: FunctionType,
    ) -> Iterator[Dict]:
        return self._get_base_options(SortDirectionEnum, get_label, lambda d: self.sort == d)

    async def get_where_form(self, engine, backend, hidden_extra_data: Optional[Dict] = {}) -> Form:
        data = {}
        if self.where:
            data['operand'] = self.where[0][1]

        items = self._get_where_options(self.get_label)
        items = [
            (
                o['form_name'],  # as value
                o['label'],
                o['is_active'],
            )
            for o in items
        ]
        
        field_dict = {
            'Meta': type('Meta', tuple(), {'is_active': self._is_where_active}),
            'full_clause': Select2Field('Условие', choices=list(items)),
            # 'operand': StringField('Значение')
        }

        converter = ModelConverter()
        mapper = sa_inspect(self.model_class)
        field_dict['operand'] = await converter.convert(
            mapper=mapper,
            model=self.model_class,
            engine=engine,
            backend=backend,
            prop=self.field_prop
        )
        if field_dict.get('operand') is None:
            field_dict['operand'] = StringField('Значение')

        for k, v in hidden_extra_data.items():
            if isinstance(v, (list, tuple, )):
                for vi in v:
                    vi_key = k+self._IDENTITY_SEPARATOR+str(vi) 
                    field_dict[vi_key] = HiddenField(name=k)
                    data[vi_key] = vi
            else:
                field_dict[k] = HiddenField()
                data[k] = v

        FilterForm = type('FilterForm', (Form,), field_dict)
        return FilterForm(data=data)

    def get_sort_options(self, hidden_extra_data: Optional[Dict] = {}) -> Iterator[Dict]:
        for opt in self._get_sort_options(get_label=self.get_label):
            # opt['extra'] = hidden_extra_data
            yield opt

    def get_overlay(self, **overlay):
        data = self.dict()
        data.update(overlay)
        return type(self)(**data)

    def get_overlay_clear(self):
        return self.get_overlay(sort=None, where=[])


class ParametrizedColumnsManager(BaseModel):
    columns: List[FilteredOrderedAdminColumn] = []

    def __getitem__(self, key):
        return self.columns.__getitem__(key)

    def all(self):
        return self.columns

    def get_list_params_where(self):
        return list(self.columns_where_stmt(self.columns))

    def get_list_params_sort(self):
        return list(self.columns_sort_stmt(self.columns))

    @classmethod
    def columns_sort_stmt(cls, columns: Iterable[FilteredOrderedAdminColumn]):
        return chain(*[ca.sort_stmt() for ca in columns])

    @classmethod
    def columns_where_stmt(cls, columns: Iterable[FilteredOrderedAdminColumn]):
        return chain(*[ca.where_stmt() for ca in columns])

    @classmethod
    def columns_form_data(
        cls, 
        columns: Iterable[FilteredOrderedAdminColumn]
    ) -> Iterator[Tuple[str, Any]]:
        # columns: List[FilteredOrderedAdminColumn] = self.columns
        sort_key = FilteredOrderedAdminColumn._SORT_KEY
        ordering = []
        for key, value in chain.from_iterable([c.form_data for c in columns]):
            if key == sort_key:
                ordering.append(value)
            else:
                yield key, value
        if ordering:
            yield sort_key, ordering

    def columns_form_data_overlayed(
        cls, 
        columns: Iterable[FilteredOrderedAdminColumn], 
        overlay: FilteredOrderedAdminColumn
    ) -> Iterator[Tuple[str, Any]]:
        # columns: List[FilteredOrderedAdminColumn] = self.columns
        columns_overlayed = [
            c if not c.match_column_identity(overlay) else overlay 
            for c in columns
        ]
        return cls.columns_form_data(columns_overlayed)

    async def get_filter_form(self, column: FilteredOrderedAdminColumn, **kwargs):
        cols_filter_data = dict(self.columns_form_data_overlayed(
            self.columns, overlay=column.get_overlay(where=[])))
        return await column.get_where_form(hidden_extra_data=cols_filter_data, **kwargs)

    def _urlencode(self, url_data: DictReader={}, quote_via=quote_plus, doseq=True):
        return urlencode(url_data, quote_via=quote_via, doseq=doseq)

    def get_sort_options(self, column: FilteredOrderedAdminColumn):
        for opt in column.get_sort_options():
            opt['form_data_full'] = dict(self.columns_form_data_overlayed(
                self.columns,
                overlay=column.get_overlay(sort=opt['value'])
            ))
            opt['urlencode'] = self._urlencode(opt['form_data_full'])
            yield opt

    @classmethod
    def get_columns_from_form_data(cls, columns_identity: List, **columns_form_data: Dict):
        return [
            FilteredOrderedAdminColumn.from_identity(col_identity, **columns_form_data)
            for col_identity in columns_identity
        ]

    def update_columns_list_display(self, columns_identity: List, request: Request = None, url_query_str: Optional[str]=None):
        if request is None and url_query_str is None:
            params = {}
        else:
            url_query_str = url_query_str or request.url.query

            def val_prepare(key, v):
                if isinstance(v, list):
                    lenv = len(v)
                    if lenv == 1:
                        v = v[0]
                    elif lenv == 0:
                        v = None
                return v
            params = {
                k: val_prepare(k, v)
                for k, v in parse_qs(url_query_str).items()
            }
        self.columns = self.get_columns_from_form_data(columns_identity, **params)


# ColType = Union[ColumnProperty, str]
ColType = ColumnProperty


class ModelAdminParamsMixin:
    params: ListViewParams = ListViewParams(filters=[], ordering=[])
    columns: ParametrizedColumnsManager = ParametrizedColumnsManager()

    def get_list_view_params(self):
        return self.params

    def set_list_view_params(self, params):
        self.params = params

    def get_col_filter_label(self, clause, col, model, field):
        return str(clause)

    def get_col_ordering_label(self, direction, col, model, field):
        return str(direction)

    @lru_cache
    def _get_model_field(self, col: ColType) -> Tuple[str, str]:
        return find_model_class(col).__name__, col.key

    def _get_col_options_base(
        self,
        col: ColType,
        OptionsEnumClass: Enum,
        ListParamItem: BaseListParamItem,
        get_label: FunctionType,
        option_enum_key: str,
        multiple: bool = False
    ) -> Tuple[List[Tuple[ListViewParams, str, bool]], Union[BaseListParamItem, List[BaseListParamItem], None]]:
        model, field = self._get_model_field(col)
        items = []
        active_items = []
        for enum_opt in OptionsEnumClass:
            enum_opt_kw = {option_enum_key: enum_opt}
            active = self.get_list_view_params().get_item(
                ItemType=ListParamItem, model=model, field=field, **enum_opt_kw)
            is_active = active is not None
            if is_active:
                active_items.append(active)
            items.append((
                self.get_list_view_params().override(
                    ListParamItem(
                        model=model,
                        field=field,
                        **enum_opt_kw
                    ), remove=is_active),
                get_label(enum_opt, col, model, field),
                is_active
            ))
        return items, active_items if multiple else (active_items[0] if len(active_items) else None)

    def get_col_filter_options(
        self, col: ColType
    ) -> Tuple[List[Tuple[ListViewParams, str, bool]], List[BaseListParamItem]]:
        return self._get_col_options_base(
            col=col,
            OptionsEnumClass=ClauseEnum,
            ListParamItem=ListFilterItem,
            get_label=self.get_col_filter_label,
            option_enum_key='clause'
        )

    def get_col_filter_data(self, col: ColType) -> List[Tuple[ListFilterItem, str, bool]]:
        model, field = self._get_model_field(col)
        items = []
        active_items = []
        for cl in ClauseEnum:
            active = self.get_list_view_params().get_filter(model=model, field=field, clause=cl)
            is_active = active is not None
            if is_active:
                active_items.append(active)
            items.append((
                ListFilterItem(
                    model=model,
                    field=field,
                    clause=cl
                ),
                self.get_col_filter_label(cl, col, model, field),
                is_active
            ))
        params_without_this_field = self.get_list_view_params().override(
            self.get_list_view_params().get_filter(model=model, field=field), remove=True)
        return [(items, params_without_this_field, )]

    def get_col_ordering_options(self, col: ColType) -> Tuple[List[Tuple[ListOrderingItem, str, bool]], List[BaseListParamItem]]:
        return self._get_col_options_base(
            col=col,
            OptionsEnumClass=SortDirectionEnum,
            ListParamItem=ListOrderingItem,
            get_label=self.get_col_ordering_label,
            option_enum_key='direction',
            multiple=False
        )

    async def get_col_filter_form(self, col: ColType) -> List[Tuple[ListFilterItem, str, bool]]:
        model, field = self._get_model_field(col)
        params = self.get_list_view_params()
        col_filter_item = params.get_filter(model=model, field=field)
        is_filter_active = col_filter_item is not None
        data = {}
        if col_filter_item is not None and col_filter_item.operand is not None:
            data['operand'] = col_filter_item.operand

        items = []
        items.append((
            "",
            "Очистить",
            False,
        ))
        active_items = []
        for cl in ClauseEnum:
            active = params.get_filter(model=model, field=field, clause=cl)
            is_active = active is not None
            if is_active:
                active_items.append(active)
            item_full_clause = ListFilterItem(
                model=model,
                field=field,
                clause=cl
            ).get_full_clause()
            if is_active:
                data['full_clause'] = item_full_clause

            items.append((
                item_full_clause,
                self.get_col_filter_label(cl, col, model, field),
                is_active
            ))
        # class FilterForm(Form):
        #     class Meta:
        #         is_active = is_filter_active

        #     full_clause = Select2Field('Условие', choices=items)
        #     operand = StringField('Значение')

        field_dict = {
            'Meta': type('Meta', tuple(), {'is_active': is_filter_active}),
            'full_clause': Select2Field('Условие', choices=items),
            # 'operand': StringField('Значение')
        }

        converter = ModelConverter()
        # fix: convert() attrs set?
        mapper = sa_inspect(self.model)
        field_dict['operand'] = await converter.convert(mapper=mapper,
                                                        model=self.model, engine=self.engine, backend=self.backend, prop=col)
        if field_dict.get('operand') is None:
            field_dict['operand'] = StringField('Значение')

        params_without_this_field = self.get_list_view_params().override(
            self.get_list_view_params().get_filter(model=model, field=field), remove=True).get_requests_query_params()
        for k, v in params_without_this_field.items():
            field_dict[k] = HiddenField()
            data[k] = v

        FilterForm = type('FilterForm', (Form,), field_dict)

        fields = [f for f in FilterForm(data=data)]
        form = FilterForm(data=data)

        return form

    # async def get_list_col_head_display(self, col: ColType) -> Dict:
    #     # model, field = self._get_model_field(col)
    #     data = {'DIRECTION_ENUM': SortDirectionEnum}
    #     data['ordering_options'], data['order'] = self.get_col_ordering_options(col)
    #     data['order_direction'] = getattr(data['order'], 'direction', None)
    #     data['filter_form'] = await self.get_col_filter_form(col)
    #     data['filter_form_is_active'] = data['filter_form'].meta.is_active
    #     return data

    async def get_list_col_head_display(self, col: FilteredOrderedAdminColumn) -> Dict:
        data = {}
        data['DIRECTION_ENUM'] = SortDirectionEnum
        data['sort_options'] = self.columns.get_sort_options(col)
        data['sort_direction'] = col.sort
        form = await self.columns.get_filter_form(col, engine=self.engine, backend=self.backend)
        data['filter_form'] = form
        data['filter_form_is_active'] = form.meta.is_active
        return data

    def get_list_params_order_by(self, *args, **kwargs):
        return self.columns.get_list_params_sort()
        return [o.get_stmt() for o in self.get_list_view_params().ordering]

    def get_list_params_where(self, *args, **kwargs):
        return self.columns.get_list_params_where()
        return [f.get_stmt() for f in self.get_list_view_params().filters]

    def update_params(self, request: Request):
        url_str_params = request.url.query
        base_cols = self.get_list_columns()
        self.columns.update_columns_list_display(base_cols, request)
        # try:
        #     base_cols = self.get_list_columns()
        #     self.columns.update_columns_list_display(base_cols, request)
        #     # params = ListViewParams.from_url_str(url_str_params)
        #     # self.set_list_view_params(params)
        # except AttributeError as e:
        #     print('Failed to update list view params/ Please, check the syntax of the query at first')
        #     raise e


"""
Определиться с фильтрацией по произвольным значениям и по enum-ам
http://localhost:8000/admin/user_billing/list?
User__email__ilike=%25.com%25
&o=User__email__d%2CUser__username__d
&User__username__exact=%25r%25
"""
