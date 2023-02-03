from functools import lru_cache
from gino.crud import CRUDModel
from gino.declarative import Model, ModelType, ColumnAttribute, declarative_base, inspect_model_type
from sqlalchemy import ForeignKey, ForeignKeyConstraint
from gino.ext.starlette import Gino, GinoEngine  # type: ignore
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql.schema import Column
from sqlalchemy.orm import ColumnProperty, RelationshipProperty as SA_RelationshipProperty, Session, interfaces
from sqlalchemy.orm.base import MANYTOMANY, ONETOMANY, MANYTOONE
from sqlalchemy.orm.attributes import QueryableAttribute
from sqlalchemy.sql.schema import FetchedValue


from typing import Any, List, OrderedDict, Union, Optional, Dict, ClassVar
from pydantic import BaseSettings, SecretStr, validator, PostgresDsn

from sqlalchemy.orm import relationship as sa_relationship

from sqlalchemy.orm import ColumnProperty, Mapper as SA_Mapper
# from sqlalchemy import inspect
import inspect
import sqlalchemy as sa
from sqlalchemy.orm.instrumentation import ClassManager
from sqlalchemy.orm.state import InstanceState
from sqladmin.backends.relationships import BaseModelRelationshipsLoader

# from collections import namedtuple
from sqlalchemy.orm import RelationshipProperty
from sqlalchemy import inspect, and_
from sqlalchemy.sql.elements import Cast
from sqlalchemy.sql import ColumnElement
from gino.crud import CRUDModel
from gino.declarative import ModelType as GinoModelType

import inspect as py_inspect
from asyncio import iscoroutine, run
from types import LambdaType
from typing import Any, Dict, Iterator, OrderedDict, Optional, List, Tuple
from importlib import import_module
from sqlalchemy.exc import NoInspectionAvailable
from sqladmin.exceptions import InvalidColumnError, InvalidModelError
from sqlalchemy.orm.base import DEFAULT_MANAGER_ATTR, DEFAULT_STATE_ATTR
from sqlalchemy.orm.instrumentation import ClassManager

from sqlalchemy.orm.base import ONETOMANY, MANYTOONE, MANYTOMANY


NO_ATTR = None
RELATIONSHIP_PROPERTY_ID_KEY_TPL = '{}_id'
MAPPER_KEY = 'mapper'
GINO_MAPPER_KEY = '_gino_mapper'



class GinoRelationshipsLoader(BaseModelRelationshipsLoader):
    RELATIONSHIPS_LOADER_KEY = '_gino_relationships_loader'


class GinoResultList(list):
    def __init__(self, *args, class_=None, prop: SA_RelationshipProperty = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_ = class_
        self.prop = prop


# class RelationshipProperty:
#     _sa_prop = None
#     _init_args = None

#     def __init__(
#         self,
#         argument, *args, **kwargs
#     ) -> None:
#         stack = inspect.stack()
#         self._init_args = {'argument': argument,
#                            'args': args, 'kwargs': kwargs}

#     @property
#     def sa_prop(self):
#         if self._sa_prop is None:
#             arg = self._init_args['argument']
#             if not isinstance(arg, Model):
#                 if callable(arg):
#                     arg = arg()
#                 # elif isinstance(arg, str):
#                 #     # trying to get model declared in same global context
#                 #     arg = globals[arg]
#             self._sa_prop = sa_relationship(
#                 arg,
#                 *self._init_args['args'],
#                 **self._init_args['kwargs']
#             )
#             self._sa_parent
#         return self._sa_prop

#     @property
#     def sa_prop(self):
#         if self._sa_prop is None:
#             arg = self._init_args['argument']
#             if not isinstance(arg, Model):
#                 if callable(arg):
#                     arg = arg()
#                 # elif isinstance(arg, str):
#                 #     # trying to get model declared in same global context
#                 #     arg = globals[arg]
#             self._sa_prop = sa_relationship(
#                 arg,
#                 *self._init_args['args'],
#                 **self._init_args['kwargs']
#             )
#         return self._sa_prop

#     def __getattribute__(self, attr):
#         """Перенапраяляем обращение к несуществующим аттрибутам к self.get_inspected()"""
#         try:
#             return super().__getattribute__(attr)
#         except AttributeError:
#             try:
#                 return getattr(self.sa_prop, attr)
#             except AttributeError as e:
#                 raise e


class GinoClassManager(ClassManager):
    pass


class GinoModelMapperProperty(InstrumentedAttribute):
    pass


class GinoModelMapperInherited(SA_Mapper):
    def __init__(self, *args, inspected=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._inspected = inspected

    @property
    def inspected(self):
        if self._inspected is None:
            self._inspected = sa.inspection.inspect(self.class_.__table__)
        return self._inspected

    @inspected.setter
    def set_inspected(self, inspected):
        self._inspected = inspected

    def _should_exclude(self, name, assigned_name, local, column):
        local = None
        return super()._should_exclude(name, assigned_name, local, column)

    def _is_userland_descriptor(self, obj):
        if isinstance(obj, ColumnAttribute):
            return False
        return super()._is_userland_descriptor(obj)



class GinoModelMapperAdapter:
    # __mappers = []
    non_primary = None
    base_mapper = None
    _gino_base_model = None
    _delete_orphans: List = None
    concrete = True
    
            
    class StrAttr(str):
        # def __init__(self, *args, **kwargs):
        #     super().__init__(*args, **kwargs)
            # base_model = GinoModelMapperAdapter.get_gino_base_model()
        def __clause_element__(self, *args, **kwargs):
            base_model = GinoModelMapperAdapter.get_gino_base_model()
            return find_model_field(self, base_model=base_model)

    def __init__(self, class_, inspected=None, relationships_loader=None, **kwargs) -> None:
        self.class_ = class_
        self._class_instance = kwargs.pop('instance', None)
        self._inspected = inspected
        self.relationships_loader = relationships_loader
        self._attrs = None
        self._props_extra = OrderedDict()
        self._columns = None
        self._delete_orphans = []
        self._attrs = self._get_model_class_attrs(self.class_, init=True)
        # self.__mappers.append(self)

    @classmethod
    def get_gino_base_model(self):
        if self._gino_base_model is None:
            base_models = list(BaseModelRelationshipsLoader.get_base_model_registry())
            if len(base_models) > 0:
                self._gino_base_model = base_models[0]
        return self._gino_base_model
    # def get_models_modules(self):
    #     return [m.class_.__module__ for m in self.__mappers]

    def _patch_sa_relaionship_property(self, prop: RelationshipProperty, key: str, init: bool = True):
        prop.set_parent(self, init)
        prop.persist_selectable = self.class_.__table__
        if getattr(prop, 'key', None) is None:
            prop.key = key

        # prop._setup_join_conditions()
        
        # TODO patch many to many relationships correct
        
        for attr_key in ['order_by']:
            val = getattr(prop, attr_key, None)
            if isinstance(val, str):
                setattr(prop, attr_key, self.StrAttr(val))
                val = getattr(prop, attr_key, None)
                # print();
                # setattr(val, '__clause_element__', __clause_element__)

        if prop.backref is not None:
            RelatedModel = get_related_model(prop)
            back_populates, params = prop.backref
            bkref = getattr(RelatedModel, back_populates, None)
            
            # TODO patch many to many relationships correct
            # create relationship if backref set
            if bkref is None:
                backref_prop = sa_relationship(
                    self.class_, 
                    secondary=prop.secondary,
                    back_populates=key
                )
                self._patch_sa_relaionship_property(backref_prop, key=back_populates, init=init)
                
                setattr(RelatedModel, back_populates,
                    backref_prop
                )
                # mapper = get_gino_mapper_for(RelatedModel)
                # mapper._props_extra[prop.back_populates] = sa_relationship(
                #     self.class_, 
                #     back_populates=key
                # ) 
                            
        # prop.do_init()
        

        # related_model_prop_fk_key = '{}_id'.format(val.key)
        # RelatedModel = get_related_model(val)
        # if not hasattr(RelatedModel, related_model_prop_fk_key):
        #     related_model_prop_fk_key = None

        # # init direction of relation
        # direction = getattr(val, 'direction', None)
        # # if direction is not None:
        # #     return direction
        # if direction is not None:
        #     if val.secondary is None:
        #         if related_model_prop_fk_key is None:
        #             if val.uselist is not None:
        #                 print()
        #             if val.uselist:
        #                 direction = ONETOMANY
        #             else:
        #                 direction = MANYTOONE
        #         else:
        #             direction = MANYTOONE
        #     else:
        #         direction = MANYTOMANY
        #     setattr(val, 'direction', direction)

        # if val.uselist is None:
        #     val.uselist = val.direction is not MANYTOONE
        # add __clause_element__() to some attrs
        return prop

    def _class_attr_to_prop(self, class_, key, val, init=False):
        # if class_.__name__ == "Address":
        #     if key in ('user_id', ):
        #         print()
        if not isinstance(val, (
            QueryableAttribute,  # @hybrid_property result
            property,
            ColumnAttribute,
            SA_RelationshipProperty,
            Column,
        )):
            return None

        if hasattr(val, 'column'):
            val = ColumnProperty(val.column)
            val.set_parent(self, init)
            if getattr(val, 'key', None) is None:
                val.key = key
            return val
        elif isinstance(val, Column):
            val = ColumnProperty(val)
            val.set_parent(self, init)
            if getattr(val, 'key', None) is None:
                val.key = key
            return val
        elif isinstance(val, SA_RelationshipProperty):
            if not hasattr(val, 'prop'):
                val.prop = val  # compatibillity for tests

            val = self._patch_sa_relaionship_property(val, key=key, init=init)
            return val
        elif isinstance(val, QueryableAttribute):
            if getattr(val, 'key', None) is None:
                val.key = key
            return val
        # else:
        #     return ColumnProperty(val)
        # comp = Comparator()
        # attr = InstrumentedAttribute(class_=val.__class__, key=key)
        attr = GinoModelMapperProperty(class_=val.__class__, key=key)
        if not hasattr(attr, 'doc') or not getattr(attr, 'doc', None):
            attr.doc = 'doc text of attribute'
        return attr

    def _get_model_class_attrs(self, class_, init=False) -> OrderedDict:
        attrs_collection = OrderedDict()
        class_keys = dir(class_)
        for key in class_keys:
            if key.startswith('__'):
                continue
            # @FIX util.warn( "Unmanaged access of declarative attribute %s from non-mapped class ...
            # @see .../site-packages/sqlalchemy/ext/declarative/api.py:210
            val = getattr(class_, key, NO_ATTR)

            attr = self._class_attr_to_prop(class_, key, val, init=init)
            if not attr:
                continue
            attrs_collection[key] = attr

        return attrs_collection

    def _config(self, init=False):
        if self._attrs is None:
            self._attrs = self._get_model_class_attrs(self.class_, init=init)

    @property
    def inspected(self):
        if self._inspected is None:
            self._inspected = sa.inspection.inspect(self.class_.__table__)
        return self._inspected

    @inspected.setter
    def set_inspected(self, inspected):
        self._inspected = inspected

    @property
    def attrs(self):
        if self._attrs is None:
            self._attrs = self._get_model_class_attrs(self.class_, init=True)
        return self._attrs
    
    @property
    def _props(self):
        props = OrderedDict()
        props.update(self._props_extra)
        props.update(self.attrs)
        return props

    @property
    def _instance(self):
        if isinstance(self._class_instance, self.class_):
            return self._class_instance
        return None

    @property
    def identity(self):
        if self._instance is None:
            return list(self.inspected.primary_key)
        return [getattr(self._instance, c.key) for c in self.inspected.primary_key]

    @property
    def mapper(self):
        return self

    @property
    def persist_selectable(self):
        return self.class_.__table__

    @property
    def local_table(self):
        return self.class_.__table__

    @property
    def _equivalent_columns(self):
        return dict()

    def common_parent(self, other):
        """Return true if the given mapper shares a
        common inherited parent as this mapper."""

        return self.base_mapper is other.base_mapper

    def primary_mapper(self):
        """Return the primary mapper corresponding to this mapper's class key
        (class)."""

        return self.mapper
    
    def get_property(self, key, _configure_mappers=False):
        # SA_Mapper.get_property
        key_id = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(key)
        if hasattr(self.class_, key_id):
            return getattr(self.class_, key_id)
        return getattr(self.class_, key, None)
    
    def iterate_to_root(self):
        yield self
    
    @property
    def self_and_descendants(self):
        # res = SA_Mapper.self_and_descendants
        return set((self, ))
    
    def has_property(self, key):
        return hasattr(self.class_, key)
        return len([k for k, attr in self.attrs if k == key] > 0)

    def _configure_property(self, key, prop, init=True, setparent=True):
        print()
        pass
    
    def __getattribute__(self, attr):
        """Перенапраяляем обращение к несуществующим аттрибутам к self.get_inspected()"""
        if attr == 'attrs':  # required for property ?
            return super().__getattribute__(attr)
        try:
            return super().__getattribute__(attr)
        except AttributeError:
            try:
                return getattr(self.inspected, attr)
            except AttributeError as e:
                if self._class_instance is not None:
                    return getattr(self._class_instance, attr)
                # raise e


# GinoModelMapper = GinoModelMapperInherited
GinoModelMapper = GinoModelMapperAdapter


class GinoModelInstanceState(InstanceState):

    def __init__(self, obj, manager, mapper=None) -> None:
        super().__init__(obj, manager)
        if mapper is not None:
            self.mapper = mapper

    @property
    def identity(self):
        identity = super().identity
        if identity is None:
            return self.mapper.identity
        return identity
        pk = list(self.inspected.primary_key)[0]
        if self._instance is None:
            return list(self.inspected.primary_key)
        return [getattr(self._instance, c.key) for c in self.inspected.primary_key]


class InstanceStateGinoAdapter(interfaces.InspectionAttrInfo):
    sa_state = None
    def __init__(self, instance_state: InstanceState) -> None:
        self.sa_state = instance_state

    @property
    def identity(self):
        identity = self.sa_state.identity
        if identity is None:
            return self.mapper.identity
        return identity
        pk = list(self.inspected.primary_key)[0]
        if self._instance is None:
            return list(self.inspected.primary_key)
        return [getattr(self._instance, c.key) for c in self.inspected.primary_key]
    
    @property
    def mapper(self):
        return getattr(self.object, MAPPER_KEY, None)

    def __getattribute__(self, attr):
        """Перенапраяляем обращение к несуществующим аттрибутам к self.get_inspected()"""
        # if attr == 'attrs':  # required for property ?
        #     return super().__getattribute__(attr)
        try:
            return super().__getattribute__(attr)
        except AttributeError:
            try:
                return getattr(self.sa_state, attr)
            except AttributeError as e:
                # if self._class_instance is not None:
                #     return getattr(self._class_instance, attr)
                raise e


def find_model_class(identity, base_model=None, extra: Optional[Dict]=None) -> CRUDModel:
    model_class = None
    if isinstance(identity, str):
        # from sqladmin.models import GinoRelationshipsLoader
        loader = GinoRelationshipsLoader.get(base_model=base_model)
        try:
            model_class = loader.load(identity)
        except ModuleNotFoundError as e:
            model_class = None
    elif isinstance(identity, (GinoModelType, )):
        model_class = identity
    elif isinstance(identity, LambdaType):
        model_class = identity(**extra)
    elif isinstance(identity, (ColumnElement, ColumnProperty, Cast )):
        """search by models properties
        """
        base_model = base_model or GinoRelationshipsLoader.get_base_model()
        # models = base_model.__subclasses__()
        class_attribute = getattr(identity, 'class_attribute', None)
        # if class_attribute is None:
        #     # identity.table.element.
        #     class_attribute = identity.table.name
        # if isinstance(identity, Cast):
        #     print()
        identity_table = getattr(identity, 'table', None)
        if identity_table is None:
            if getattr(identity, 'class_attribute', None) is not None:
                identity_table = identity.class_attribute.table
        # identity_table = identity.table
        # except Exception as e:
        #     identity_table = None
        for model in base_model.__subclasses__():
            if type(identity_table.name).__name__ in ('str', 'quoted_name', ):
                if model.__table__.name == identity_table.name:
                    model_class = model
                    break
            else:
                if model.__table__.name == identity_table.element.name:
                    model_class = model
                    break
            for attr in dir(model):
                attr_val = getattr(model, attr, None)
                if (
                    (attr_val is identity) 
                    or (class_attribute is not None and attr_val is class_attribute)
                ):  
                    model_class = model
                    break
            if model_class is not None:
                break
    if model_class is None:
        raise ModuleNotFoundError(f'Model {type(identity)} not found')

    return model_class


def find_model_field(identity, base_model, extra: Optional[Dict]=None) -> CRUDModel:
    if isinstance(identity, str):
        *class_path, field_name = identity.split('.')
        cls = find_model_class('.'.join(class_path), base_model=base_model, extra=extra)
        if cls is None:
            # field = None
            raise ModuleNotFoundError(f'Model {type(identity)} not found')
        else:
            field = getattr(cls, field_name, None)
    elif isinstance(identity, (ColumnElement, )):
        field = identity
    elif isinstance(identity, LambdaType):
        field = identity(**extra)
    
    if field is None:
        raise ModuleNotFoundError(f'Field {type(identity)} not found')

    return field


def get_related_model(prop: RelationshipProperty, *args, **kwargs) -> CRUDModel:
    RESULT_KEY = '_gino_related_model'
    related_model = getattr(prop, RESULT_KEY, None)
    if related_model is not None:
        return related_model

    related_model = find_model_class(prop.argument, base_model=prop.parent.class_)

    setattr(prop, RESULT_KEY, related_model)
    return related_model


def get_related_secondary_model(prop: RelationshipProperty, *args, **kwargs) -> CRUDModel:
    RESULT_KEY = '_gino_related_secondary_model'
    related_model = getattr(prop, RESULT_KEY, None)
    if related_model is not None:
        return related_model

    related_model = find_model_class(prop.secondary, base_model=prop.parent.class_)

    setattr(prop, RESULT_KEY, related_model)
    return related_model


def get_secondary_model_fk(Model, SecondaryModel, default=None):
    key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(Model.__name__.lower())
    return getattr(SecondaryModel, key, default)


def get_model_pk(
    class_, *, 
    single=True, 
    raise_on_multiple=False, 
    matching_col:Optional[Column]=None, 
    matching_model:Optional[GinoModelType]=None
):
    try:
        mapper = inspect(class_)
    except NoInspectionAvailable:
        raise InvalidModelError(
            f"Class {class_.__name__} is not a SQLAlchemy model."
        )

    pk_columns = list(mapper.primary_key)
    
    if pk_columns:
        if single:
            if len(pk_columns) > 0:
                if raise_on_multiple:
                    assert len(pk_columns) > 1, "Multiple PK columns not supported."
            return pk_columns[0]
        return pk_columns

    fk_constraints = [c for c in mapper.local_table.constraints if isinstance(c, ForeignKeyConstraint)]
    if matching_col is not None:
        reffered_table = matching_col.table
    elif matching_model is not None:
        reffered_table = matching_model.__table__
    else:
        return None
    for fk_c in fk_constraints:
        if fk_c.referred_table == reffered_table:
            return list(fk_c.columns)[0]

    return None 


def get_one2many_query(
    model_instance: type,
    model_prop: RelationshipProperty
):
    model_prop_pk_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(model_prop.key)
    if not hasattr(model_instance, model_prop_pk_key):
        model_prop_pk_key = None
    prop_has_not_pointer = model_prop_pk_key is None

    if prop_has_not_pointer:
        return None

    model_prop_pk_val = getattr(model_instance, model_prop_pk_key)
    RelatedModel = get_related_model(model_prop)
    related_model_pk_column = get_model_pk(RelatedModel)

    return RelatedModel.query.where(related_model_pk_column == model_prop_pk_val)


def get_backref_column(prop: RelationshipProperty, related_model: type = None):
    RelatedModel = related_model or get_related_model(prop=prop)
    if prop.back_populates is not None:
        related_prop_pk_column_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(
            prop.back_populates)
        related_prop_pk_column = getattr(RelatedModel, related_prop_pk_column_key)
    elif prop.backref is not None:
        back_populates, ref_kwargs = prop.backref
        related_prop_pk_column_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(
            back_populates)
        related_prop_pk_column = getattr(RelatedModel, related_prop_pk_column_key)
    else:
        raise AttributeError(
            'Improperly configured relation: back_populates or backref is not set')
    return related_prop_pk_column


def get_many2one_query(
    model_instance: type,
    model_prop: RelationshipProperty
):
    RelatedModel = get_related_model(prop=model_prop)
    model_pk = get_model_pk(model_instance)
    model_pk_val = getattr(model_instance, model_pk.key)
    relationship_backref_col = get_backref_column(
        model_prop, related_model=RelatedModel)
    return RelatedModel.query.where(relationship_backref_col == model_pk_val)

                
def get_relationship_direction(
    model: GinoModelType,
    model_prop: RelationshipProperty,
):
    """
    Args:
        model (GinoModelType): _description_
        model_prop (RelationshipProperty): _description_
        @TODO: improve
    Returns:
        _type_: _description_
    """
    direction = getattr(model_prop, 'direction', None)
    if direction is not None:
        return direction
    
    model_prop_pk_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(model_prop.key)
        
    back_populates = model_prop.back_populates
    uselist = model_prop.uselist
    if model_prop.backref is not None:
        back_populates = back_populates or model_prop.backref[0]
        uselist = (model_prop.backref[1] or {}).get('uselist', None)
    RelatedModel = get_related_model(model_prop) 
    # for rfk in RelatedModel.__table__.foreign_keys:
    #     if rfk.column.table == model.__table__:
    #         related_model_prop_fk = rfk.column
    #         break
    # else:
    #     related_model_prop_fk = None
    related_model_prop_fk_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(back_populates)
    
    # model_prop.secondaryjoin
    if model_prop.secondary is None:
        if (
            (hasattr(model, model_prop.key) 
             and hasattr(model, model_prop_pk_key) 
             and not hasattr(RelatedModel, related_model_prop_fk_key)) 
        ):
            direction = MANYTOONE
        elif (
            hasattr(RelatedModel, back_populates) 
            and hasattr(RelatedModel, related_model_prop_fk_key) 
            and not hasattr(model, model_prop_pk_key)):
            direction = ONETOMANY
        else:
            direction = MANYTOONE
    else:
        direction = MANYTOMANY
    setattr(model_prop, 'direction', direction)
    
    print(f'Direction of prop {model_prop} is: {direction}')
    
    return direction 


def get_relationship_uselist(prop: RelationshipProperty, instance: GinoModelType=None):
    if prop.direction is None:
        assert instance is not None
        prop.direction = get_relationship_direction(instance, prop)
    if prop.uselist is None:
        prop.uselist = prop.direction is not MANYTOONE
    return prop.uselist

def fetch_model_instance_relationship(
    model_instance: GinoModelType,
    model_prop: RelationshipProperty,
    as_property: bool = False
):
    if getattr(model_instance, model_prop.key, None) is not model_prop:
        # prop on instance is not same, so prop on instance is already patched
        return
    
    Model = type(model_instance)
    model_pk_column = get_model_pk(Model)
    model_instance_pk_value = getattr(model_instance, model_pk_column.key, None)

    # pointer to RelatedModel instance id (pk column value)
    model_prop_pk_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(model_prop.key)
    if not hasattr(model_instance, model_prop_pk_key):
        model_prop_pk_key = None

    # init direction of relation
    rel_direction = get_relationship_direction(model_instance, model_prop)

    RelatedModel = get_related_model(model_prop)
    related_model_pk_column = get_model_pk(RelatedModel, matching_col=model_pk_column)

    # model_prop_query_attr = '_{}_query'.format(model_prop.key)
    # if getattr(model_instance, model_prop_query_attr, None) is None:
    if rel_direction == MANYTOONE:
        # model_instance has foreign key pointed to related model instance id
        def fget():
            if model_prop_pk_key is None:
                print()
            assert model_prop_pk_key is not None
            # model_prop_pk_val = getattr(model_instance, model_prop_pk_key)
            return RelatedModel.query.where(
                related_model_pk_column == getattr(model_instance, model_prop_pk_key, None)
            ).gino.one_or_none()
    elif rel_direction == ONETOMANY:
        def fget():
            # TODO: implement many to one relationship
            if model_prop.back_populates is not None:
                related_model_prop_pk_column_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(
                    model_prop.back_populates)
                related_model_prop_pk_column = getattr(
                    RelatedModel, related_model_prop_pk_column_key)
            elif model_prop.backref is not None:
                back_populates, ref_kwargs = model_prop.backref
                related_model_prop_pk_column_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(
                    back_populates)
                related_model_prop_pk_column = getattr(
                    RelatedModel, related_model_prop_pk_column_key)
            else:
                raise AttributeError(
                    'Improperly configured relation: back_populates or backref is not set')

            if related_model_prop_pk_column is not None:
                print()
            assert related_model_prop_pk_column is not None
            model_pk_column = get_model_pk(model_instance.__class__)
            model_instance_pk_val = getattr(model_instance, model_pk_column.key)
            return RelatedModel.query.where(related_model_prop_pk_column == model_instance_pk_val).gino.all()
    elif rel_direction == MANYTOMANY:
        if model_prop.secondary is None:
            raise AttributeError(
                    'Improperly configured relation: many to many requires "secondary" parameter')
        def fget():
            SecondaryModel = get_related_secondary_model(model_prop)
            related_model_pk_column = get_model_pk(SecondaryModel)
            # Model = type(model_instance)
            s2model_id_col_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(Model.__name__.lower())
            s2related_id_col_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(RelatedModel.__name__.lower())
            model_relation_key = 'm2m_{}'.format(Model.__name__.lower())
            model_pk_column = get_model_pk(Model)
            model_instance_pk_val = getattr(model_instance, model_pk_column.key)
            query = RelatedModel.outerjoin(SecondaryModel).outerjoin(Model).select().where(
                model_pk_column==model_instance_pk_val
                # getattr(SecondaryModel, s2model_id_col_key) == model_instance_pk_val
            )
            related_models_instances_coroutine = query.gino.load(
                RelatedModel.distinct(related_model_pk_column).load(
                    **{model_relation_key: Model.distinct(model_pk_column)}
                )).all()
            return related_models_instances_coroutine
            # TODO: implement many to may relationship
            # model_prop_pk_val = getattr(model_instance, None)
            # return RelatedModel.query.where(related_model_pk_column==model_prop_pk_val)
            raise NotImplemented()
    else:
        fget = None
    
    assert fget is not None

    if as_property:
        setattr(
            model_instance, model_prop.key,
            property(fget=fget)
        )
    else:
        setattr(
            model_instance, model_prop.key,
            fget()
        )


def get_all_relationships(instance: GinoModelType):
    RESULT_KEY = '_relationships'
    rels = getattr(instance, RESULT_KEY, None)
    if rels is not None:
        return rels

    Model = type(instance)
    rels = OrderedDict()
    for key in dir(Model):
        attr = getattr(Model, key, None)
        if not isinstance(attr, RelationshipProperty):
            continue
        rels[key] = attr
    setattr(Model, RESULT_KEY, rels)
    return rels


async def fetch_all_relationships(model_instance: GinoModelType):
    for key, rel in get_all_relationships(model_instance).items():
        fetch_model_instance_relationship(model_instance=model_instance, model_prop=rel)
        await await_relationship(model_instance=model_instance, key=key)
    return model_instance


async def await_relationship(
    model_instance: type,
    key: str
):
    relationship_coroutine = getattr(model_instance, key, None)
    if iscoroutine(relationship_coroutine):
        # prop on instance is not same, so prop on instance is already patched
        setattr(model_instance, key, await relationship_coroutine)
    else:
        return relationship_coroutine


def get_related_property_gino_loader(GinoModelClass: GinoModelType, model_class_pk, key, prop):
    RelatedModelClass = get_related_model(prop)
    rel_pk = get_model_pk(RelatedModelClass, matching_col=model_class_pk)
    return GinoModelClass.load(**{key: RelatedModelClass.on(model_class_pk == rel_pk)})


def _get_cols_sorted_data(GinoModelClass: type, data: Dict):
    cols_data = {}
    non_cols_data = {}
    for key, val in data.items():
        if key in GinoModelClass.__table__.c:
            cols_data[key] = val
        else:
            non_cols_data[key] = val
    return cols_data, non_cols_data


async def prepare_gino_model_data(
    GinoModelClass: GinoModelType,
    data: Dict
):
    cols_data, non_cols_data = _get_cols_sorted_data(GinoModelClass, data)
    non_cols_data_converted = []
    for key, val in non_cols_data.items():
        attr = getattr(GinoModelClass, key, None)
        if isinstance(attr, RelationshipProperty):
            prop_id_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(key)
            RelatedModel = get_related_model(prop=attr)
            if hasattr(GinoModelClass, prop_id_key):
                if isinstance(val, RelatedModel):  # if value are model instance
                    related_pk = get_model_pk(RelatedModel)
                    val = getattr(val, related_pk.key)
                cols_data[prop_id_key] = val
                non_cols_data_converted.append(key)
            else:
                # for "many to one" relationship we don't have a
                # instance id ib DB because data are not saved to DB
                # so, we must do this operations after data saved (for getting id)
                continue
                # assert model_instance_id
                # related_model_id_col = get_model_pk(RelatedModel)
                # related_model_backref_col = get_backref_column(prop=attr, related_model=RelatedModel)
                # if related_model_backref_col  is None:
                #     raise AttributeError('Bad relationship configuration: no id found.')
                # if not hasattr(val, '__iter__'):
                #     val = iter([val])
                # for v in val:
                #     # TODO: test
                #     await RelatedModel.update.values(
                #         **{related_model_backref_col.key: model_instance_id}
                #     ).where(related_model_id_col == v).gino.status()

    # TODO: add hybrid_properties support
    # hybrid_properties not supported yet
    for c in non_cols_data_converted:
        non_cols_data.pop(c, None)

    return cols_data, non_cols_data


async def process_gino_model_post_create(
    data: Dict,
    instance: GinoModelType = None,
    instance_id: Any = None,
    Model: type = None, 
    backref_key_none: Any = None
):  
    if instance is None:
        if Model is None or instance_id is None:
            raise AttributeError('Incorrect argumants')
    elif Model is None or instance_id is None:
        if instance is None:
            raise AttributeError('Incorrect argumants')
        Model = type(instance)
    cols_data, non_cols_data = _get_cols_sorted_data(Model, data)
    for key, val in non_cols_data.items():
        attr = getattr(Model, key, None)
        if isinstance(attr, RelationshipProperty):
            direction = get_relationship_direction(Model, attr)
            prop_id_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(key)
            RelatedModel = get_related_model(prop=attr)
            if direction == ONETOMANY:
                # if isinstance(val, RelatedModel):  # if value are model instance
                #     related_pk = get_model_pk(RelatedModel)
                #     val = getattr(val, related_pk.key)
                # cols_data[prop_id_key] = val
                # non_cols_data.pop(key, None)
                continue
            elif direction == MANYTOONE:
                # assert model_instance_id
                instance_pk_col = get_model_pk(Model)
                related_model_id_col = get_model_pk(RelatedModel)
                related_model_backref_col = get_backref_column(
                    prop=attr, related_model=RelatedModel)
                if related_model_backref_col is None:
                    raise AttributeError('Bad relationship configuration: no id found.')
                if not hasattr(val, '__iter__'):
                    val = [] if val is None else [val]
                if instance_id is None:
                    instance_id = getattr(instance, instance_pk_col.key)
                if len(val) > 0:
                    if isinstance(val[0], RelatedModel):
                        val = [getattr(v, related_model_id_col.key) for v in val]
                    update_values = {related_model_backref_col.key: instance_id}
                    where_cond = related_model_id_col.in_(val)
                    # match = await RelatedModel.query.where(where_cond).gino.all()
                    # await RelatedModel.update.values(**update_values).where(where_cond).gino.status()
                    # match_2 = await RelatedModel.query.where(where_cond).gino.all()
                else:
                    update_values = {related_model_backref_col.key: backref_key_none }
                    where_cond = related_model_backref_col == instance_id
                match = await RelatedModel.query.where(where_cond).gino.all()
                await RelatedModel.update.values(**update_values).where(where_cond).gino.status()
                match_2 = await RelatedModel.query.where(where_cond).gino.all()
            elif direction == MANYTOMANY:
                # assert model_instance_id
                SecondaryModel = get_related_secondary_model(attr)
                instance_pk_col = get_model_pk(Model)
                related_model_id_col = get_model_pk(RelatedModel)
                sm2model_col = get_secondary_model_fk(Model, SecondaryModel)
                sm2related_model_col = get_secondary_model_fk(RelatedModel, SecondaryModel)
                if not hasattr(val, '__iter__'):
                    val = [] if val is None else [val]
                if instance_id is None:
                    instance_id = getattr(instance, instance_pk_col.key)
                if len(val) > 0:
                    if isinstance(val[0], RelatedModel):
                        val = [getattr(v, related_model_id_col.key) for v in val]
                # val = [getattr(v, related_model_id_col.key) for v in val]
               
                # delete all not in val
                await SecondaryModel.delete.where(
                    and_(sm2model_col==instance_id, 
                         sm2related_model_col.notin_(val))
                ).gino.status()
                
                # get not exists
                related_ids_associated = await SecondaryModel.select(sm2related_model_col.key).where(sm2model_col==instance_id).gino.all()
                related_ids_associated = [getattr(r, sm2related_model_col.key) for r in related_ids_associated]
                related_ids_without_sm_instances = (set(val) - set(related_ids_associated))
                
                # insert not exists secondary model instances
                sm_datas = [
                    {
                        sm2model_col.key: instance_id,
                        sm2related_model_col.key: rel_id
                    } 
                    for rel_id in related_ids_without_sm_instances
                ]
                if len(sm_datas) > 0:
                    await SecondaryModel.insert().gino.all(sm_datas)
            else:
                raise ValueError()
                    

    # TODO: add hybrid_properties support
    # hybrid_properties not supported yet

    return cols_data, non_cols_data


def get_relation_property_id_col(GinoModel: GinoModelType, prop: RelationshipProperty, default: Any = ...):
    prop_id_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(prop.key)
    return getattr(GinoModel, prop_id_key, default)


def _map_target(target: Any):
    pass


def get_gino_mapper_for(target: Any):    
    mapper = getattr(target, MAPPER_KEY, None)
    if mapper is not None:
        if isinstance(target, mapper.class_):
            mapper._class_instance = target
            
            class_manager = getattr(mapper.class_, DEFAULT_MANAGER_ATTR, None)
            if class_manager is None:
                class_manager = ClassManager(mapper.class_)
                for key, attr in mapper.attrs.items():
                    class_manager[key] = attr
                setattr(mapper.class_, DEFAULT_MANAGER_ATTR, class_manager)
            
            instance_state = getattr(target, DEFAULT_STATE_ATTR, None)
            if instance_state is None:
                instance_state = GinoModelInstanceState(target, class_manager, mapper)
                setattr(target, DEFAULT_STATE_ATTR, instance_state)
            if isinstance(instance_state, InstanceState):
                instance_state = InstanceStateGinoAdapter(instance_state)
                setattr(target, DEFAULT_STATE_ATTR, instance_state)
                # if not hasattr(instance_state, '_sa_identity'):
                #     instance_state._sa_identity = instance_state.identity
                #     setattr(
                #         instance_state, 'identity', 
                #         property(lambda: instance_state._sa_identity or instance_state.object.identity_map.values())
                #     )
            return instance_state
        return mapper
    try:
        inspected = inspect_model_type(target)
        class_ = target
        instance = None
    except AttributeError:
        TargetType = type(target)
        inspected = inspect_model_type(TargetType)
        class_ = TargetType
        instance = target
        
    mapper = GinoModelMapper(
        class_=class_,
        local_table=target.__table__,
        inspected=inspected,
        instance=instance,
    )
    
    class_manager = getattr(mapper.class_, DEFAULT_MANAGER_ATTR, None)
    if class_manager is None:
        class_manager = ClassManager(mapper.class_)
        for key, attr in mapper.attrs.items():
            class_manager[key] = attr
        setattr(mapper.class_, DEFAULT_MANAGER_ATTR, class_manager)
    
    setattr(target, MAPPER_KEY, mapper)
    return mapper
