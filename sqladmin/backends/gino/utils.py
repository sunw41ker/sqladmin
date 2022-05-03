# from collections import namedtuple
# from pyexpat import model
# from sqlalchemy.orm import RelationshipProperty
# from sqlalchemy import inspect
# from sqlalchemy.sql import ColumnElement
# from gino.crud import CRUDModel
# from gino.declarative import ModelType as GinoModelType

# import inspect as py_inspect
# from asyncio import iscoroutine, run
# from types import LambdaType
# from typing import Any, Dict, Iterator, OrderedDict, Optional, List, Tuple
# from importlib import import_module
# from sqlalchemy.exc import NoInspectionAvailable
# from sqladmin.exceptions import InvalidColumnError, InvalidModelError

# from sqlalchemy.orm.base import ONETOMANY, MANYTOONE, MANYTOMANY

# from .models import GinoRelationshipsLoader


# RELATIONSHIP_PROPERTY_ID_KEY_TPL = '{}_id'


# def find_model_class(identity, base_model, extra: Optional[Dict]=None) -> CRUDModel:
#     if isinstance(identity, str):
#         # from sqladmin.models import GinoRelationshipsLoader
#         loader = GinoRelationshipsLoader.get(base_model=base_model)
#         model_class = loader.load(identity)
#     elif isinstance(identity, (GinoModelType, )):
#         model_class = identity
#     elif isinstance(identity, LambdaType):
#         model_class = identity(**extra)
    
#     if model_class == None:
#         raise ModuleNotFoundError(f'Model {type(identity)} not found')

#     return model_class


# def find_model_field(identity, base_model, extra: Optional[Dict]=None) -> CRUDModel:
#     if isinstance(identity, str):
#         *class_path, field_name = identity.split('.')
#         cls = find_model_class('.'.join(class_path), base_model=base_model, extra=extra)
#         if cls is None:
#             # field = None
#             raise ModuleNotFoundError(f'Model {type(identity)} not found')
#         else:
#             field = getattr(cls, field_name, None)
#     elif isinstance(identity, (ColumnElement, )):
#         field = identity
#     elif isinstance(identity, LambdaType):
#         field = identity(**extra)
    
#     if field == None:
#         raise ModuleNotFoundError(f'Field {type(identity)} not found')

#     return field


# def get_related_model(prop: RelationshipProperty, *args, **kwargs) -> CRUDModel:
#     RESULT_KEY = '_gino_related_model'
#     related_model = getattr(prop, RESULT_KEY, None)
#     if related_model is not None:
#         return related_model

#     related_model = find_model_class(prop.argument, base_model=prop.parent.class_)

#     setattr(prop, RESULT_KEY, related_model)
#     return related_model


# def get_related_secondary_model(prop: RelationshipProperty, *args, **kwargs) -> CRUDModel:
#     RESULT_KEY = '_gino_related_secondary_model'
#     related_model = getattr(prop, RESULT_KEY, None)
#     if related_model is not None:
#         return related_model

#     related_model = find_model_class(prop.secondary, base_model=prop.parent.class_)

#     setattr(prop, RESULT_KEY, related_model)
#     return related_model


# def get_model_pk(class_, *, single=True, raise_on_multiple=False):
#     try:
#         mapper = inspect(class_)
#     except NoInspectionAvailable:
#         raise InvalidModelError(
#             f"Class {class_.__name__} is not a SQLAlchemy model."
#         )

#     pk_columns = list(mapper.primary_key)

#     if single:
#         if len(pk_columns) > 0:
#             if raise_on_multiple:
#                 assert len(pk_columns) > 1, "Multiple PK columns not supported."
#         return pk_columns[0]
#     return pk_columns


# def get_one2many_query(
#     model_instance: type,
#     model_prop: RelationshipProperty
# ):
#     model_prop_pk_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(model_prop.key)
#     if not hasattr(model_instance, model_prop_pk_key):
#         model_prop_pk_key = None
#     prop_has_not_pointer = model_prop_pk_key is None

#     if prop_has_not_pointer:
#         return None

#     model_prop_pk_val = getattr(model_instance, model_prop_pk_key)
#     RelatedModel = get_related_model(model_prop)
#     related_model_pk_column = get_model_pk(RelatedModel)

#     return RelatedModel.query.where(related_model_pk_column == model_prop_pk_val)


# def get_backref_column(prop: RelationshipProperty, related_model: type = None):
#     RelatedModel = related_model or get_related_model(prop=prop)
#     if prop.back_populates is not None:
#         related_prop_pk_column_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(
#             prop.back_populates)
#         related_prop_pk_column = getattr(RelatedModel, related_prop_pk_column_key)
#     elif prop.backref is not None:
#         back_populates, ref_kwargs = prop.backref
#         related_prop_pk_column_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(
#             back_populates)
#         related_prop_pk_column = getattr(RelatedModel, related_prop_pk_column_key)
#     else:
#         raise AttributeError(
#             'Improperly configured relation: back_populates or backref is not set')
#     return related_prop_pk_column


# def get_many2one_query(
#     model_instance: type,
#     model_prop: RelationshipProperty
# ):
#     RelatedModel = get_related_model(prop=model_prop)
#     model_pk = get_model_pk(model_instance)
#     model_pk_val = getattr(model_instance, model_pk.key)
#     relationship_backref_col = get_backref_column(
#         model_prop, related_model=RelatedModel)
#     return RelatedModel.query.where(relationship_backref_col == model_pk_val)


# def get_relationship_direction(
#     model_instance: GinoModelType,
#     model_prop: RelationshipProperty,
# ):
#     related_model_prop_pk_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(model_prop.key)
#     RelatedModel = get_related_model(model_prop)
#     if not hasattr(model_instance, related_model_prop_pk_key):
#         related_model_prop_pk_key = None

#     # init direction of relation
#     direction = getattr(model_prop, 'direction', None)
#     if direction is not None:
#         return direction
#     if model_prop.secondary is None:
#         if related_model_prop_pk_key is None:
#             if model_prop.uselist is not None:
#                 print()
#             if model_prop.uselist:
#                 direction = ONETOMANY
#             else:
#                 direction = MANYTOONE    
#         else:
#             direction = MANYTOONE
#     else:
#         direction = MANYTOMANY
#     setattr(model_prop, 'direction', direction)
#     return direction 


# def get_relationship_uselist(prop: RelationshipProperty, instance: GinoModelType=None):
#     if prop.direction is None:
#         assert instance is not None
#         prop.direction = get_relationship_direction(instance, prop)
#     if prop.uselist is None:
#         prop.uselist = prop.direction is not MANYTOONE
#     return prop.uselist

# def fetch_model_instance_relationship(
#     model_instance: GinoModelType,
#     model_prop: RelationshipProperty,
#     as_property: bool = False
# ):
#     if getattr(model_instance, model_prop.key, None) is not model_prop:
#         # prop on instance is not same, so prop on instance is already patched
#         return

#     model_prop_pk_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(model_prop.key)
#     if not hasattr(model_instance, model_prop_pk_key):
#         model_prop_pk_key = None

#     # init direction of relation
#     model_prop.direction = get_relationship_direction(model_instance, model_prop)

#     RelatedModel = get_related_model(model_prop)
#     related_model_pk_column = get_model_pk(RelatedModel)

#     # model_prop_query_attr = '_{}_query'.format(model_prop.key)
#     # if getattr(model_instance, model_prop_query_attr, None) is None:
#     if model_prop.direction == MANYTOONE:
#         # model_instance has foreign key pointed to related model instance id
#         def fget():
#             if model_prop_pk_key is not None:
#                 print()
#             assert model_prop_pk_key is not None
#             model_prop_pk_val = getattr(model_instance, model_prop_pk_key)
#             return RelatedModel.query.where(related_model_pk_column == model_prop_pk_val).gino.all()
#     elif model_prop.direction == ONETOMANY:
#         def fget():
#             # TODO: implement many to one relationship
#             if model_prop.back_populates is not None:
#                 related_model_prop_pk_column_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(
#                     model_prop.back_populates)
#                 related_model_prop_pk_column = getattr(
#                     RelatedModel, related_model_prop_pk_column_key)
#             elif model_prop.backref is not None:
#                 back_populates, ref_kwargs = model_prop.backref
#                 related_model_prop_pk_column_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(
#                     back_populates)
#                 related_model_prop_pk_column = getattr(
#                     RelatedModel, related_model_prop_pk_column_key)
#             else:
#                 raise AttributeError(
#                     'Improperly configured relation: back_populates or backref is not set')

#             if related_model_prop_pk_column is not None:
#                 print()
#             assert related_model_prop_pk_column is not None
#             model_pk_column = get_model_pk(model_instance.__class__)
#             model_instance_pk_val = getattr(model_instance, model_pk_column.key)
#             return RelatedModel.query.where(related_model_prop_pk_column == model_instance_pk_val).gino.all()
#     elif model_prop.direction == MANYTOMANY:
#         if model_prop.secondary is None:
#             raise AttributeError(
#                     'Improperly configured relation: many to many requires "secondary" parameter')
#         def fget():
#             SecondaryModel = get_related_secondary_model(model_prop)
#             related_model_pk_column = get_model_pk(SecondaryModel)
#             Model = type(model_instance)
#             s2model_id_col_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(Model.__name__.lower())
#             s2related_id_col_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(RelatedModel.__name__.lower())
#             model_relation_key = 'm2m_{}'.format(Model.__name__.lower())
#             model_pk_column = get_model_pk(Model)
#             model_instance_pk_val = getattr(model_instance, model_pk_column.key)
#             query = RelatedModel.outerjoin(SecondaryModel).outerjoin(Model).select().where(
#                 model_pk_column==model_instance_pk_val
#                 # getattr(SecondaryModel, s2model_id_col_key) == model_instance_pk_val
#             )
#             related_models_instances_coroutine = query.gino.load(
#                 RelatedModel.distinct(related_model_pk_column).load(
#                     **{model_relation_key: Model.distinct(model_pk_column)}
#                 )).all()
#             return related_models_instances_coroutine
#             # TODO: implement many to may relationship
#             # model_prop_pk_val = getattr(model_instance, None)
#             # return RelatedModel.query.where(related_model_pk_column==model_prop_pk_val)
#             raise NotImplemented()
#     else:
#         fget = None
    
#     assert fget is not None

#     if as_property:
#         setattr(
#             model_instance, model_prop.key,
#             property(fget=fget)
#         )
#     else:
#         setattr(
#             model_instance, model_prop.key,
#             fget()
#         )


# def get_all_relationships(instance: GinoModelType):
#     RESULT_KEY = '_relationships'
#     rels = getattr(instance, RESULT_KEY, None)
#     if rels is not None:
#         return rels

#     Model = type(instance)
#     rels = OrderedDict()
#     for key in dir(Model):
#         attr = getattr(Model, key, None)
#         if not isinstance(attr, RelationshipProperty):
#             continue
#         rels[key] = attr
#     setattr(Model, RESULT_KEY, rels)
#     return rels


# async def fetch_all_relationships(model_instance: GinoModelType):
#     for key, rel in get_all_relationships(model_instance).items():
#         fetch_model_instance_relationship(model_instance=model_instance, model_prop=rel)
#         await await_relationship(model_instance=model_instance, key=key)
#     return model_instance


# async def await_relationship(
#     model_instance: type,
#     key: str
# ):
#     relationship_coroutine = getattr(model_instance, key, None)
#     if iscoroutine(relationship_coroutine):
#         # prop on instance is not same, so prop on instance is already patched
#         setattr(model_instance, key, await relationship_coroutine)
#     else:
#         return relationship_coroutine


# def get_related_property_gino_loader(GinoModelClass: GinoModelType, model_class_pk, key, prop):
#     RelatedModelClass = get_related_model(prop)
#     rel_pk = get_model_pk(RelatedModelClass)
#     return GinoModelClass.load(**{key: RelatedModelClass.on(model_class_pk == rel_pk)})


# def _get_cols_sorted_data(GinoModelClass: type, data: Dict):
#     cols_data = {}
#     non_cols_data = {}
#     for key, val in data.items():
#         if key in GinoModelClass.__table__.c:
#             cols_data[key] = val
#         else:
#             non_cols_data[key] = val
#     return cols_data, non_cols_data


# async def prepare_gino_model_data(
#     GinoModelClass: GinoModelType,
#     data: Dict
# ):
#     cols_data, non_cols_data = _get_cols_sorted_data(GinoModelClass, data)
#     non_cols_data_converted = []
#     for key, val in non_cols_data.items():
#         attr = getattr(GinoModelClass, key, None)
#         if isinstance(attr, RelationshipProperty):
#             prop_id_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(key)
#             RelatedModel = get_related_model(prop=attr)
#             if hasattr(GinoModelClass, prop_id_key):
#                 if isinstance(val, RelatedModel):  # if value are model instance
#                     related_pk = get_model_pk(RelatedModel)
#                     val = getattr(val, related_pk.key)
#                 cols_data[prop_id_key] = val
#                 non_cols_data_converted.append(key)
#             else:
#                 # for "many to one" relationship we don't have a
#                 # instance id ib DB because data are not saved to DB
#                 # so, we must do this operations after data saved (for getting id)
#                 continue
#                 # assert model_instance_id
#                 # related_model_id_col = get_model_pk(RelatedModel)
#                 # related_model_backref_col = get_backref_column(prop=attr, related_model=RelatedModel)
#                 # if related_model_backref_col  is None:
#                 #     raise AttributeError('Bad relationship configuration: no id found.')
#                 # if not hasattr(val, '__iter__'):
#                 #     val = iter([val])
#                 # for v in val:
#                 #     # TODO: test
#                 #     await RelatedModel.update.values(
#                 #         **{related_model_backref_col.key: model_instance_id}
#                 #     ).where(related_model_id_col == v).gino.status()

#     # TODO: add hybrid_properties support
#     # hybrid_properties not supported yet
#     for c in non_cols_data_converted:
#         non_cols_data.pop(c, None)

#     return cols_data, non_cols_data


# async def process_gino_model_post_create(
#     data: Dict,
#     instance: GinoModelType = None,
#     instance_id: Any = None,
#     Model: type = None, 
#     backref_key_none: Any = None
# ):  
#     if instance is None:
#         if Model is None or instance_id is None:
#             raise AttributeError('Incorrect argumants')
#     elif Model is None or instance_id is None:
#         if instance is None:
#             raise AttributeError('Incorrect argumants')
#         Model = type(instance)
#     cols_data, non_cols_data = _get_cols_sorted_data(Model, data)
#     for key, val in non_cols_data.items():
#         attr = getattr(Model, key, None)
#         if isinstance(attr, RelationshipProperty):
#             prop_id_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(key)
#             RelatedModel = get_related_model(prop=attr)
#             if hasattr(Model, prop_id_key):
#                 # if isinstance(val, RelatedModel):  # if value are model instance
#                 #     related_pk = get_model_pk(RelatedModel)
#                 #     val = getattr(val, related_pk.key)
#                 # cols_data[prop_id_key] = val
#                 # non_cols_data.pop(key, None)
#                 continue
#             else:
#                 # continue
#                 # assert model_instance_id
#                 instance_pk_col = get_model_pk(Model)
#                 related_model_id_col = get_model_pk(RelatedModel)
#                 related_model_backref_col = get_backref_column(
#                     prop=attr, related_model=RelatedModel)
#                 if related_model_backref_col is None:
#                     raise AttributeError('Bad relationship configuration: no id found.')
#                 if not hasattr(val, '__iter__'):
#                     val = [] if val is None else [val]
#                 if instance_id is None:
#                     instance_id = getattr(instance, instance_pk_col.key)
#                 if len(val) > 0:
#                     if isinstance(val[0], RelatedModel):
#                         val = [getattr(v, related_model_id_col.key) for v in val]
#                     update_values = {related_model_backref_col.key: instance_id}
#                     where_cond = related_model_id_col.in_(val)
#                     # match = await RelatedModel.query.where(where_cond).gino.all()
#                     # await RelatedModel.update.values(**update_values).where(where_cond).gino.status()
#                     # match_2 = await RelatedModel.query.where(where_cond).gino.all()
#                 else:
#                     update_values = {related_model_backref_col.key: backref_key_none }
#                     where_cond = related_model_backref_col == instance_id
#                 match = await RelatedModel.query.where(where_cond).gino.all()
#                 await RelatedModel.update.values(**update_values).where(where_cond).gino.status()
#                 match_2 = await RelatedModel.query.where(where_cond).gino.all()
                    

#     # TODO: add hybrid_properties support
#     # hybrid_properties not supported yet

#     return cols_data, non_cols_data


# def get_relation_property_id_col(GinoModel: GinoModelType, prop: RelationshipProperty, default: Any = ...):
#     prop_id_key = RELATIONSHIP_PROPERTY_ID_KEY_TPL.format(prop.key)
#     return getattr(GinoModel, prop_id_key, default)
