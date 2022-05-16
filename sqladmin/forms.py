from asyncio import iscoroutine
import anyio
import inspect
from typing import Any, Callable, Dict, Sequence, Type, Union, Optional, Iterable, no_type_check

from sqlalchemy import inspect as sqlalchemy_inspect, select
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.engine import Engine
from sqlalchemy.orm.attributes import QueryableAttribute
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import ColumnProperty, Mapper, RelationshipProperty, Session
from sqlalchemy.sql.schema import Column
from sqlalchemy.sql.elements import Cast
from wtforms import (
    BooleanField,
    DateField,
    DateTimeField,
    DecimalField,
    Field,
    Form,
    IntegerField,
    SelectField,
    StringField,
    TextAreaField,
    PasswordField,
    validators,
)
from wtforms.fields.core import UnboundField
from wtforms.fields import FileField, MultipleFileField
from pydantic import BaseModel as PydanticBaseModel
from pydantic.fields import ModelField as PydanticModelField
from sqladmin.backends.gino.models import get_related_model, get_relation_property_id_col, get_model_pk, get_relationship_direction

from sqladmin.schemas import RelationshipModelField as PydanticRealtionshipModelField
from sqladmin.fields import QuerySelectField, QuerySelectMultipleField
from sqladmin.backends import BackendEnum, get_used_backend

used_backend: BackendEnum = get_used_backend()

if used_backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession   # type: ignore
    Gino = None
    EngineTypeTuple = Engine, AsyncEngine
    EngineType = Union[Engine, AsyncEngine]
    from sqlalchemy import Column
    #TODO: implement SqlAlchemy backend
elif used_backend == BackendEnum.GINO:
    # from gino.ext.starlette import Gino  # type: ignore
    from gino.ext.starlette import Gino, GinoEngine  # type: ignore
    from sqladmin.backends.gino.models import GinoModelMapperProperty
    from sqlalchemy.orm.base import MANYTOMANY, ONETOMANY, MANYTOONE
    # from .backends.gino.models import GinoModelMapperProperty
    # from asyncpg.pool import Pool as GinoEngine
    # from gino import create_engine
    # from gino import Gino
    from sqlalchemy import Table
    AsyncEngine, AsyncSession = None, None 
    EngineTypeTuple = Engine, Gino
    EngineType = Union[Engine, Gino]
    

@no_type_check
def converts(*args: str) -> Callable:
    def _inner(func: Callable) -> Callable:
        func._converter_for = frozenset(args)
        return func

    return _inner


class ModelConverterBase:
    _convert_for = None

    def __init__(self) -> None:
        converters = {}

        for name in dir(self):
            obj = getattr(self, name)
            if hasattr(obj, "_converter_for"):
                for classname in obj._converter_for:
                    converters[classname] = obj

        self.converters = converters

    def get_converter(self, column: Column) -> Callable:
        types = inspect.getmro(type(column.type))

        # Search by name
        for col_type in types:
            if col_type.__name__ in self.converters:
                return self.converters[col_type.__name__]

        raise Exception(
            f"Could not find field converter for column {column.name} ({types[0]!r})."
        )

    async def convert(
        self,
        model: type,
        mapper: Mapper,
        prop: Union[ColumnProperty, RelationshipProperty],
        engine: Union[Engine, AsyncEngine],
        backend: BackendEnum,
        *args, **_kwargs
    ) -> UnboundField:
        kwargs: Dict = {
            "validators": [],
            "filters": [],
            "default": None,
            "description": getattr(prop, 'doc', None),
        }

        converter = None
        column = None

        if isinstance(prop, (ColumnProperty, Column)):
            if isinstance(prop, ColumnProperty):
                assert len(prop.columns) == 1, "Multiple-column properties not supported"
                column = prop.columns[0]
            else:
                column = prop

            # TODO: определитьсЯ, как работать с relationships в формах
            if column.primary_key or column.foreign_keys:
                return

            default = getattr(column, "default", None)

            if default is not None:
                # Only actually change default if it has an attribute named
                # 'arg' that's callable.
                callable_default = getattr(default, "arg", None)

                if callable_default is not None:
                    # ColumnDefault(val).arg can be also a plain value
                    default = (
                        callable_default(None)
                        if callable(callable_default)
                        else callable_default
                    )

            kwargs["default"] = default

            if column.nullable or column.type.python_type is bool:
                kwargs["validators"].append(validators.Optional())
            else:
                kwargs["validators"].append(validators.InputRequired())

            converter = self.get_converter(column)
        else:
            nullable = True
            if hasattr(prop, 'local_remote_pairs'):
                if prop.local_remote_pairs: 
                    for pair in prop.local_remote_pairs:
                        if not pair[0].nullable:
                            nullable = False
                else:
                    nullable = True
            else:
                nullable = getattr(prop, 'nullable', False)
                    # nullable = False

            kwargs["allow_blank"] = nullable
            
            if used_backend == BackendEnum.GINO:
                pk_columns = list(mapper.primary_key.columns.items())
                pk = pk_columns[0][1].name
                if isinstance(prop, RelationshipProperty):
                    stmt = select(get_related_model(prop))
                else:
                    stmt = select(model)  # not required in Gino backend
            elif used_backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
                pk = mapper.primary_key[0].name
                stmt = engine.select(prop.table)
            
            if backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
                if isinstance(engine, Engine):
                    with Session(engine) as session:
                        objects = await anyio.to_thread.run_sync(session.execute, stmt)
                        object_list = [
                            (str(self.get_pk(obj, pk)), obj)
                            for obj in objects.scalars().all()
                        ]
                        kwargs["object_list"] = object_list
                else:
                    async with AsyncSession(engine) as session:
                        objects = await session.execute(stmt)
                        object_list = [
                            (str(self.get_pk(obj, pk)), obj)
                            for obj in objects.scalars().all()
                        ]
                        kwargs["object_list"] = object_list
            elif backend == BackendEnum.GINO:
                if isinstance(prop, RelationshipProperty):
                    RelatedModelClass = get_related_model(prop)
                    objects = await engine.all(
                        stmt.execution_options(loader=RelatedModelClass), 
                        # loader=RelatedModelClass,
                        # return_model=True,
                        # model=RelatedModelClass
                    )
                    pk = get_model_pk(RelatedModelClass, matching_model=model).key
                    # # object_list = objects
                    # # objects = await session.execute(stmt)
                    # print()
                    object_list = [
                        (str(self.get_pk(obj, pk)), obj)
                        for obj in objects
                    ]
                    
                    # object_list = await RelatedModelClass.query.gino.all()
                    kwargs["object_list"] = object_list
                # else:
                #     objects = await engine.all(
                #         stmt.execution_options(loader=model), 
                #         # loader=model,
                #         # return_model=True,
                #         # model=model
                #     )
                #     # # object_list = objects
                #     # # objects = await session.execute(stmt)
                #     # print()
                #     object_list = [
                #         (str(self.get_pk(obj, pk)), obj)
                #         for obj in objects
                #     ]
                    
                #     # object_list = await RelatedModelClass.query.gino.all()
                #     kwargs["object_list"] = object_list
            else:
                raise TypeError('Unknown backend type: '+ str(used_backend))
            
            if isinstance(prop, Cast):
                if hasattr(prop, 'type'):
                    converter = self.converters[type(prop.type).__name__]
            # elif isinstance(prop, QueryableAttribute):
            if isinstance(prop, QueryableAttribute):
                if hasattr(prop, 'descriptor'):
                    if prop.descriptor.__class__.__name__ == 'hybrid_property':
                        type_guess = getattr(prop.descriptor.fget, '__annotations__', {}).get('return', str)
                        converter = self.converters[type_guess.__name__]
            elif isinstance(prop, (RelationshipProperty, )):
                if hasattr(prop, 'direction') and prop.direction is not None:
                    converter = self.converters[prop.direction.name]
                else:
                    converter = self.converters['RelationshipProperty']
            else:
                if hasattr(prop, 'class_') and prop.class_ is not None:
                    converter = self.converters[prop.class_.__name__]
                elif hasattr(prop, 'type'):
                    converter = self.converters[type(prop.type).__name__]
                    kwargs.pop("allow_blank")
                # else:
                #     converter = self.converters['String']  # remove this!
        if converter is None:
            print()
        assert converter is not None

        convert_result = converter(
            model=model, mapper=mapper, prop=prop, column=column, field_args=kwargs
        )
        
        if iscoroutine(convert_result):
            return await convert_result
        return convert_result

    def get_pk(self, o: Any, pk_name: str) -> Any:
        return getattr(o, pk_name)


class ModelConverter(ModelConverterBase):
    @classmethod
    def _string_common(cls, column: Column, field_args: Dict, **kwargs: Any) -> None:
        if isinstance(column.type.length, int) and column.type.length:
            field_args["validators"].append(validators.Length(max=column.type.length))

    @converts("String")  # includes Unicode
    def conv_String(self, field_args: Dict, **kwargs: Any) -> Field:
        self._string_common(field_args=field_args, **kwargs)
        return StringField(**field_args)
    
    @converts("str") 
    def conv_str(self, field_args: Dict, **kwargs: Any) -> Field:
        field_args.pop("allow_blank", None)
        field_args.pop("object_list", None)
        return StringField(**field_args)

    @converts("Text", "LargeBinary", "Binary")  # includes UnicodeText
    def conv_Text(self, field_args: Dict, **kwargs: Any) -> Field:
        self._string_common(field_args=field_args, **kwargs)
        return TextAreaField(**field_args)

    @converts("Boolean", "dialects.mssql.base.BIT", "bool")
    def conv_Boolean(self, field_args: Dict, **kwargs: Any) -> Field:
        # field_args.pop('allow_blank', None)
        field_args.pop("object_list", None)
        return BooleanField(**field_args)

    @converts("Date")
    def conv_Date(self, field_args: Dict, **kwargs: Any) -> Field:
        return DateField(**field_args)

    @converts("DateTime")
    def conv_DateTime(self, field_args: Dict, **kwargs: Any) -> Field:
        return DateTimeField(**field_args)

    @converts("Enum")
    def conv_Enum(self, column: Column, field_args: Dict, **kwargs: Any) -> Field:
        field_args["choices"] = [(e, e) for e in column.type.enums]
        return SelectField(**field_args)
    
    @converts("ChoiceType")
    def conv_ChoiceType(self, column: Column, field_args: Dict, **kwargs: Any) -> Field:
        def get_val(choice):
            if hasattr(choice, 'value'):
                return choice.value
            else:
                return choice
        field_args["choices"] = [(get_val(e), e) for e in column.type.choices]
        return SelectField(**field_args)

    @converts("Integer")  # includes BigInteger and SmallInteger
    def handle_integer_types(
        self, column: Column, field_args: Dict, **kwargs: Any
    ) -> Field:
        field_args.pop('allow_blank', None)
        field_args.pop("object_list", None)
        return IntegerField(**field_args)

    @converts("Numeric", "int", "float", "Float")  # includes DECIMAL, Float/FLOAT, REAL, and DOUBLE
    def handle_decimal_types(
        self, column: Column, field_args: Dict, **kwargs: Any
    ) -> Field:
        field_args.pop("allow_blank", None)
        field_args.pop("object_list", None)
        # override default decimal places limit, use database defaults instead
        field_args.setdefault("places", None)
        return DecimalField(**field_args)

    # @converts("dialects.mysql.types.YEAR", "dialects.mysql.base.YEAR")
    # def conv_MSYear(self, field_args: Dict, **kwargs: Any) -> Field:
    #     field_args["validators"].append(validators.NumberRange(min=1901, max=2155))
    #     return StringField(**field_args)

    # @converts("dialects.postgresql.base.INET")
    # def conv_PGInet(self, field_args: Dict, **kwargs: Any) -> Field:
    #     field_args.setdefault("label", "IP Address")
    #     field_args["validators"].append(validators.IPAddress())
    #     return StringField(**field_args)

    # @converts("dialects.postgresql.base.MACADDR")
    # def conv_PGMacaddr(self, field_args: Dict, **kwargs: Any) -> Field:
    #     field_args.setdefault("label", "MAC Address")
    #     field_args["validators"].append(validators.MacAddress())
    #     return StringField(**field_args)

    # @converts("dialects.postgresql.base.UUID")
    # def conv_PGUuid(self, field_args: Dict, **kwargs: Any) -> Field:
    #     field_args.setdefault("label", "UUID")
    #     field_args["validators"].append(validators.UUID())
    #     return StringField(**field_args)

    def _get_label(self, obj):
        return str(obj)
    
    @converts("MANYTOONE")
    def conv_ManyToOne(self, field_args: Dict, **kwargs: Any) -> Field:
        field_args['get_label'] = self._get_label
        return QuerySelectField(**field_args)

    @converts("MANYTOMANY", "ONETOMANY")
    def conv_ManyToMany(self, field_args: Dict, **kwargs: Any) -> Field:
        field_args['get_label'] = self._get_label
        return QuerySelectMultipleField(**field_args)

    @converts("RelationshipProperty")
    async def conv_RelationshipProperty(self, field_args: Dict, model, prop: RelationshipProperty, **kwargs: Any) -> Field:
        # TODO: implement gino relationship property
        # field_args.pop("allow_blank", None)
        # field_args.pop("object_list", None)
        
        RelatedModelClass = get_related_model(prop)
    
        # Directions:
        #   1. this prop + this_related_id_key ---> RelatedClass.id
        #   2. this.id <--- RelatedClass prop + .this_id
        
        # patch_model_instance_relationship(model_instance=)
        # await_relationship(model_instance=)
        field_args['get_label'] = self._get_label
        
        # prop_id_col = get_relation_property_id_col(model, prop, None)
        direction = get_relationship_direction(model, prop)
        if direction in (MANYTOMANY, ONETOMANY, ):
            return QuerySelectMultipleField(**field_args)
        
        return QuerySelectField(**field_args)
    
    @converts("property")
    def conv_property(self, field_args: Dict, **kwargs: Any) -> Field:
        # self._string_common(field_args=field_args, **kwargs)
        return StringField(**field_args)

    @converts("EmailType")
    def conv_EmailType(self, field_args: Dict, **kwargs: Any) -> Field:
        # self._string_common(field_args=field_args, **kwargs)
        return StringField(**field_args)
    
    @converts("PasswordType")
    def conv_PasswordType(self, field_args: Dict, **kwargs: Any) -> Field:
        # self._string_common(field_args=field_args, **kwargs)
        
        return None  # password fields doesn't editing
        # temporary disabled password fields
        field_args['render_kw'] = {'disabled':'', 'type': 'password'}
        return StringField(**field_args)
    
    @converts("JSONB")
    def conv_JSONB(self, field_args: Dict, **kwargs: Any) -> Field:
        # self._string_common(field_args=field_args, **kwargs)
        return TextAreaField(**field_args)
    
    @converts("ProfileLocality")
    def conv_ProfileLocality(self, field_args: Dict, **kwargs: Any) -> Field:
        # self._string_common(field_args=field_args, **kwargs)
        return StringField(**field_args)
    
    @converts("ARRAY")
    def conv_ARRAY(self, field_args: Dict, **kwargs: Any) -> Field:
        # self._string_common(field_args=field_args, **kwargs)
        return TextAreaField(**field_args)
    
    @converts("hybrid_property")
    def conv_hybrid_property(self, field_args: Dict, **kwargs: Any) -> Field:
        # self._string_common(field_args=field_args, **kwargs)
        field_args.pop("allow_blank", None)
        field_args.pop("object_list", None)
        return TextAreaField(**field_args)
    # sqlalchemy_utils.types.email.EmailType


# class PydanticConverter(ModelConverterBase):
#     @classmethod
#     def _string_common(cls, column: Column, field_args: Dict, **kwargs: Any) -> None:
#         if isinstance(column.type.length, int) and column.type.length:
#             field_args["validators"].append(validators.Length(max=column.type.length))

#     @converts("str")  # includes Unicode
#     def conv_String(self, field_args: Dict, **kwargs: Any) -> Field:
#         self._string_common(field_args=field_args, **kwargs)
#         return StringField(**field_args)
    
#     # @converts("str") 
#     # def conv_str(self, field_args: Dict, **kwargs: Any) -> Field:
#     #     # field_args.pop("allow_blank", None)
#     #     field_args.pop("object_list", None)
#     #     return StringField(**field_args)

#     @converts("Boolean", "dialects.mssql.base.BIT", "bool")
#     def conv_Boolean(self, field_args: Dict, **kwargs: Any) -> Field:
#         # field_args.pop('allow_blank', None)
#         field_args.pop("object_list", None)
#         return BooleanField(**field_args)

#     @converts("Date")
#     def conv_Date(self, field_args: Dict, **kwargs: Any) -> Field:
#         return DateField(**field_args)

#     @converts("DateTime")
#     def conv_DateTime(self, field_args: Dict, **kwargs: Any) -> Field:
#         return DateTimeField(**field_args)

#     @converts("Enum")
#     def conv_Enum(self, column: Column, field_args: Dict, **kwargs: Any) -> Field:
#         field_args["choices"] = [(e, e) for e in column.type.enums]
#         return SelectField(**field_args)
    
#     @converts("ChoiceType")
#     def conv_ChoiceType(self, column: Column, field_args: Dict, **kwargs: Any) -> Field:
#         def get_val(choice):
#             if hasattr(choice, 'value'):
#                 return choice.value
#             else:
#                 return choice
#         field_args["choices"] = [(get_val(e), e) for e in column.type.choices]
#         return SelectField(**field_args)

#     @converts("Integer")  # includes BigInteger and SmallInteger
#     def handle_integer_types(
#         self, column: Column, field_args: Dict, **kwargs: Any
#     ) -> Field:
#         return IntegerField(**field_args)

#     @converts("Numeric", "int", "float")  # includes DECIMAL, Float/FLOAT, REAL, and DOUBLE
#     def handle_decimal_types(
#         self, column: Column, field_args: Dict, **kwargs: Any
#     ) -> Field:
#         field_args.pop("allow_blank", None)
#         field_args.pop("object_list", None)
#         # override default decimal places limit, use database defaults instead
#         field_args.setdefault("places", None)
#         return DecimalField(**field_args)

#     # @converts("dialects.mysql.types.YEAR", "dialects.mysql.base.YEAR")
#     # def conv_MSYear(self, field_args: Dict, **kwargs: Any) -> Field:
#     #     field_args["validators"].append(validators.NumberRange(min=1901, max=2155))
#     #     return StringField(**field_args)

#     # @converts("dialects.postgresql.base.INET")
#     # def conv_PGInet(self, field_args: Dict, **kwargs: Any) -> Field:
#     #     field_args.setdefault("label", "IP Address")
#     #     field_args["validators"].append(validators.IPAddress())
#     #     return StringField(**field_args)

#     # @converts("dialects.postgresql.base.MACADDR")
#     # def conv_PGMacaddr(self, field_args: Dict, **kwargs: Any) -> Field:
#     #     field_args.setdefault("label", "MAC Address")
#     #     field_args["validators"].append(validators.MacAddress())
#     #     return StringField(**field_args)

#     # @converts("dialects.postgresql.base.UUID")
#     # def conv_PGUuid(self, field_args: Dict, **kwargs: Any) -> Field:
#     #     field_args.setdefault("label", "UUID")
#     #     field_args["validators"].append(validators.UUID())
#     #     return StringField(**field_args)

#     @classmethod
#     def _get_label(cls, obj):
#         return str(obj)
    
#     @converts("MANYTOONE")
#     def conv_ManyToOne(self, field_args: Dict, **kwargs: Any) -> Field:
#         return QuerySelectField(**field_args)

#     @converts("MANYTOMANY", "ONETOMANY")
#     def conv_ManyToMany(self, field_args: Dict, **kwargs: Any) -> Field:
#         return QuerySelectMultipleField(**field_args)

#     @converts("RelationshipProperty")
#     async def conv_RelationshipProperty(self, field_args: Dict, model, prop: RelationshipProperty, **kwargs: Any) -> Field:
#         # TODO: implement gino relationship property
#         # field_args.pop("allow_blank", None)
#         # field_args.pop("object_list", None)
        
#         RelatedModelClass = get_related_model(prop)
    
#         # Directions:
#         #   1. this prop + this_related_id_key ---> RelatedClass.id
#         #   2. this.id <--- RelatedClass prop + .this_id
        
#         # patch_model_instance_relationship(model_instance=)
#         # await_relationship(model_instance=)
#         field_args['get_label'] = self._get_label
        
#         direction = get_relationship_direction(model, prop)
#         if direction in (MANYTOMANY, MANYTOONE, ):
#             return QuerySelectMultipleField(**field_args)
        
#         return QuerySelectField(**field_args)
    
#     @converts("property")
#     def conv_property(self, field_args: Dict, **kwargs: Any) -> Field:
#         # self._string_common(field_args=field_args, **kwargs)
#         return StringField(**field_args)

#     @converts("EmailType")
#     def conv_EmailType(self, field_args: Dict, **kwargs: Any) -> Field:
#         # self._string_common(field_args=field_args, **kwargs)
#         return StringField(**field_args)
    
#     @converts("PasswordType")
#     def conv_PasswordType(self, field_args: Dict, **kwargs: Any) -> Field:
#         # self._string_common(field_args=field_args, **kwargs)
        
#         return None  # password fields doesn't editing
#         # temporary disabled password fields
#         field_args['render_kw'] = {'disabled':'', 'type': 'password'}
#         return StringField(**field_args)
    
#     @converts("JSONB")
#     def conv_JSONB(self, field_args: Dict, **kwargs: Any) -> Field:
#         # self._string_common(field_args=field_args, **kwargs)
#         return TextAreaField(**field_args)
    
#     @converts("ProfileLocality")
#     def conv_ProfileLocality(self, field_args: Dict, **kwargs: Any) -> Field:
#         # self._string_common(field_args=field_args, **kwargs)
#         return StringField(**field_args)
    
#     @converts("ARRAY")
#     def conv_ARRAY(self, field_args: Dict, **kwargs: Any) -> Field:
#         # self._string_common(field_args=field_args, **kwargs)
#         return TextAreaField(**field_args)
    
#     @converts("hybrid_property")
#     def conv_hybrid_property(self, field_args: Dict, **kwargs: Any) -> Field:
#         # self._string_common(field_args=field_args, **kwargs)
#         field_args.pop("allow_blank", None)
#         field_args.pop("object_list", None)
#         return TextAreaField(**field_args)
    
#     # sqlalchemy_utils.types.email.EmailType
#     async def convert(
#         self,
#         model: type,
#         mapper: Mapper,
#         prop: PydanticModelField,
#         engine: Union[Engine, AsyncEngine],
#         backend: BackendEnum,
#         schema: PydanticBaseModel,
#         *args, **_kwargs
#     ) -> UnboundField:
#         kwargs: Dict = {
#             "validators": [],
#             "filters": [],
#             "default": None,
#             "description": getattr(prop, 'doc', None),
#         }

#         converter = None
#         column = None

#         if isinstance(prop, (ColumnProperty, Column)):
#             if isinstance(prop, ColumnProperty):
#                 assert len(prop.columns) == 1, "Multiple-column properties not supported"
#                 column = prop.columns[0]
#             else:
#                 column = prop

#             # TODO: определитьсЯ, как работать с relationships в формах
#             if column.primary_key or column.foreign_keys:
#                 return

#             default = getattr(column, "default", None)

#             if default is not None:
#                 # Only actually change default if it has an attribute named
#                 # 'arg' that's callable.
#                 callable_default = getattr(default, "arg", None)

#                 if callable_default is not None:
#                     # ColumnDefault(val).arg can be also a plain value
#                     default = (
#                         callable_default(None)
#                         if callable(callable_default)
#                         else callable_default
#                     )

#             kwargs["default"] = default

#             if column.nullable:
#                 kwargs["validators"].append(validators.Optional())
#             else:
#                 kwargs["validators"].append(validators.InputRequired())

#             converter = self.get_converter(column)
#         else:
#             nullable = True
#             if hasattr(prop, 'local_remote_pairs'):
#                 if prop.local_remote_pairs: 
#                     for pair in prop.local_remote_pairs:
#                         if not pair[0].nullable:
#                             nullable = False
#                 else:
#                     nullable = True
#             else:
#                 nullable = getattr(prop, 'nullable', False)
#                     # nullable = False

#             kwargs["allow_blank"] = nullable
            
#             if used_backend == BackendEnum.GINO:
#                 pk_columns = list(mapper.primary_key.columns.items())
#                 pk = pk_columns[0][1].name
#                 if isinstance(prop, RelationshipProperty):
#                     stmt = select(get_related_model(prop))
#                 else:
#                     stmt = select(model)  # not required in Gino backend
#             elif used_backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
#                 pk = mapper.primary_key[0].name
#                 stmt = engine.select(prop.table)
            
#             if backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
#                 if isinstance(engine, Engine):
#                     with Session(engine) as session:
#                         objects = await anyio.to_thread.run_sync(session.execute, stmt)
#                         object_list = [
#                             (str(self.get_pk(obj, pk)), obj)
#                             for obj in objects.scalars().all()
#                         ]
#                         kwargs["object_list"] = object_list
#                 else:
#                     async with AsyncSession(engine) as session:
#                         objects = await session.execute(stmt)
#                         object_list = [
#                             (str(self.get_pk(obj, pk)), obj)
#                             for obj in objects.scalars().all()
#                         ]
#                         kwargs["object_list"] = object_list
#             elif backend == BackendEnum.GINO:
#                 if isinstance(prop, RelationshipProperty):
#                     RelatedModelClass = get_related_model(prop)
#                     objects = await engine.all(
#                         stmt.execution_options(loader=RelatedModelClass), 
#                         # loader=RelatedModelClass,
#                         # return_model=True,
#                         # model=RelatedModelClass
#                     )
#                     pk = get_model_pk(RelatedModelClass).key
#                     # # object_list = objects
#                     # # objects = await session.execute(stmt)
#                     # print()
#                     object_list = [
#                         (str(self.get_pk(obj, pk)), obj)
#                         for obj in objects
#                     ]
                    
#                     # object_list = await RelatedModelClass.query.gino.all()
#                     kwargs["object_list"] = object_list
#                 # else:
#                 #     objects = await engine.all(
#                 #         stmt.execution_options(loader=model), 
#                 #         # loader=model,
#                 #         # return_model=True,
#                 #         # model=model
#                 #     )
#                 #     # # object_list = objects
#                 #     # # objects = await session.execute(stmt)
#                 #     # print()
#                 #     object_list = [
#                 #         (str(self.get_pk(obj, pk)), obj)
#                 #         for obj in objects
#                 #     ]
                    
#                 #     # object_list = await RelatedModelClass.query.gino.all()
#                 #     kwargs["object_list"] = object_list
#             else:
#                 raise TypeError('Unknown backend type: '+ str(used_backend))
            
#             if isinstance(prop, QueryableAttribute):
#                 if hasattr(prop, 'descriptor'):
#                     if prop.descriptor.__class__.__name__ == 'hybrid_property':
#                         type_guess = getattr(prop.descriptor.fget, '__annotations__', {}).get('return', str)
#                         converter = self.converters[type_guess.__name__]
#             elif isinstance(prop, (RelationshipProperty, )):
#                 if not hasattr(prop, 'direction') and prop.direction is not None:
#                     direction = get_relationship_direction(model, prop)
#                 else:
#                     direction = prop.direction
#                 converter = self.converters[direction.name]
#                     # converter = self.converters['RelationshipProperty']
#             else:
#                 if hasattr(prop, 'class_') and prop.class_ is not None:
#                     converter = self.converters[prop.class_.__name__]
#                 # else:
#                 #     converter = self.converters['String']  # remove this!

#         assert converter is not None

#         convert_result = converter(
#             model=model, mapper=mapper, prop=prop, column=column, field_args=kwargs
#         )
        
#         if iscoroutine(convert_result):
#             return await convert_result
#         return convert_result

class ModelFromMixin:
    @property
    def has_file_fields(self):
        for field in self:
            if isinstance(field, (FileField, MultipleFileField, )):
                return True
        return False
    
    @property
    def form_enctype(self):
        if self.has_file_fields:
            return 'multipart/form-data'
        return None
    
async def get_model_form(
    model: type,
    engine: Union[Engine, AsyncEngine],
    backend: BackendEnum,
    only: Sequence[str] = None,
    exclude: Sequence[str] = None,
    schema: PydanticBaseModel = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Type[Form]:
    type_name = model.__name__ + "Form"
    
    if isinstance(model, PydanticBaseModel):
        converter = None
        mapper = None
        attributes = []
        fields: Iterable[PydanticModelField] = model.__fields__.values()
        attributes = [(name, attr) for name, attr in model.__fields__.items()]
    else:
        converter = ModelConverter()
        mapper = sqlalchemy_inspect(model)

        attributes = []
        
        for name, attr in mapper.attrs.items():
            if only and name not in only:
                continue
            elif exclude and name in exclude:
                continue
            if isinstance(attr, (GinoModelMapperProperty, )):
                continue  # skipping not implemented

            attributes.append((name, attr))

    field_dict = {}
    for name, attr in attributes:
        field = await converter.convert(model, mapper, attr, engine, backend)
        if field is not None:
            field_dict[name] = field

    if extra_fields:
        field_dict.update(extra_fields)
    
    return type(type_name, (Form, ModelFromMixin, ), field_dict)


async def prepare_endpoint_form_display(form: Form, endpoint: str):
    if endpoint in ('edit', 'create', ):
        for field in form:
            if isinstance(field, BooleanField):
                if field.render_kw is None:
                    field.render_kw = {}
                if 'class' not in field.render_kw:
                    field.render_kw['class'] = ''
                field.render_kw['class'] += ' form-check-input m-0 align-middle'
                
    return form
