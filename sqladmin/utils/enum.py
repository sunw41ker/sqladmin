from collections import namedtuple
from enum import Enum, EnumMeta, _EnumDict
from typing import (
    no_type_check,
    Type,
    Any,
    List
)

class LocalizedEnumMeta(EnumMeta):
    """Metaclass used to specify class variables in ModelAdmin.

    Danger:
        This class should almost never be used directly.
    """

    @no_type_check
    def __new__(mcls, name, bases, attrs: dict, **kwargs: Any):
        # enum_type = None
        if name != "LocalizedEnum":
            if len(bases) > 1:
                # enum_type = bases[0]
                bases = bases[1:]
        cls: Type["LocalizedEnum"] = super().__new__(mcls, name, bases, attrs)
        return cls


# @TODO: Добавить поддержку babel
class LocalizedEnum(Enum, metaclass=LocalizedEnumMeta):
    """Базовый класс для локализации значений enum-ов"""
    
    def __new__(cls, *args, **kwargs):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    # ignore the first param since it's already set by __new__
    def __init__(self, _: str, description: str = None):
        self._description_ = description

    # this makes sure that the description is read-only
    @property
    def description(self):
        return self._description_

    def __str__(self) -> str:
        return self.description or self.name
