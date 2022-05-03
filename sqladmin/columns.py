from typing import Dict, Optional, Union, Any, List, Type
from pydantic import BaseModel, validator, ValidationError

from .helpers import sa_inspect


class BaseModelAdminColumn(BaseModel):
    _IDENTITY_FIELDS = 'model', 'field'
    _IDENTITY_SEPARATOR = '__'
    _MAPPER_KEY = '_mapper'

    model: Union[str, None]
    model_class: Optional[Type]
    field: str
    field_prop: Optional[Any]
    label: str
    
    def __init__(self, **data: Any) -> None:
        if data.get('model_class') is None: 
            mapper = data.get(self._MAPPER_KEY)
            if mapper is None:
                data[self._MAPPER_KEY] = sa_inspect(data['model']) 
            data['model_class'] = data[self._MAPPER_KEY].class_
        if data.get('field_prop') is None:
            data['field_prop'] = getattr(data['model_class'], data['field'])
        super().__init__(**data)

    @classmethod
    def from_col_list_item(
        cls,
        item: Union[str, Any],
        model_class: Optional[Any] = None,
        label: Optional[str] = None
    ) -> "BaseModelAdminColumn":
        data = {}
        mapper = None
        if model_class is not None:
            if isinstance(model_class, str):
                if not mapper:
                    mapper = sa_inspect(model_class)
                if getattr(mapper, 'class_', None) is not None:
                    # sa_inspect() returns mapper with 'class_' attribute
                    data['model_class'] = mapper.class_
                else:
                    data['model_class'] = mapper  # sa_inspect() returns model class
            data['model'] = data['model_class'].__name__

        if isinstance(item, str):
            item_path = item.split('.')
            item_path_len = len(item_path)
            if (
                (item_path_len <= 1 and data['model_class'] is None)
                or (item_path_len > 1 and data['model_class'] is not None)
                or item_path_len == 0
            ):
                raise AttributeError()

            if item_path_len == 1:
                data['field'] = item_path[0]
            elif item_path_len > 1:
                *model_path, field_name = item_path
                mapper = sa_inspect('.'.join(model_path))
                if getattr(mapper, 'class_', None) is not None:
                    # sa_inspect() returns mapper with 'class_' attribute
                    data['model_class'] = mapper.class_
                else:
                    data['model_class'] = mapper  # sa_inspect() returns model class
                data['model'] = data['model_class'].__name__
                data['field'] = field_name

            data['field_prop'] = getattr(model_class, data['field'])

        if label is not None:
            data['label'] = label

        if data.get('field') is None or data.get('model') is None:
            raise AttributeError()

        return cls(**data)

    @property
    def identity(self) -> str:
        base = self.dict()
        return self.get_identity(**base)

    @identity.setter
    def _identity_setter(self, value: str) -> None:
        self.model, self.field = value.split(self._IDENTITY_SEPARATOR)

    @classmethod
    def get_identity(cls, **kwargs) -> str:
        return cls._IDENTITY_SEPARATOR.join(
            [str(kwargs[attr])
             for attr in cls._IDENTITY_FIELDS
             if kwargs.get(attr, None) is not None]
        )

    def get_identity_dict(self) -> Dict:
        return {i: getattr(self, i) for i in self._IDENTITY_FIELDS}

    def match(self, **kwargs) -> bool:
        for k, v in kwargs.items():
            if getattr(self, k, None) != v:
                return False
        return True
    
    def match_column_identity(self, column: 'BaseModelAdminColumn') -> bool:
        for k in self._IDENTITY_FIELDS:
            if getattr(self, k) != getattr(column, k):
                return False
        return True
    
    
