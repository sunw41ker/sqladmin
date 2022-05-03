from typing import ClassVar, Type, Union, Set
from enum import Enum
import re
from typing import Any, Dict, Iterable, List, Optional, OrderedDict, Set, Union
# from urllib.parse import urlencode, quote_plus, parse_qs, parse_qsl
from sqlalchemy import inspect as base_sa_inspect
# import urllib
from sqladmin.backends import BackendEnum, get_used_backend


used_backend: BackendEnum = get_used_backend()

if used_backend == BackendEnum.GINO:
    from sqladmin.backends.gino.models import GinoResultList

    def sa_inspect(obj, *args, **kwargs):
        if isinstance(obj, list):
            if len(obj) > 0:
                return base_sa_inspect(obj[0], *args, **kwargs)
        if isinstance(obj, GinoResultList):
            if len(obj) > 0:
                return base_sa_inspect(obj[0], *args, **kwargs)
            else:
                return base_sa_inspect(obj.class_, *args, **kwargs)
        return base_sa_inspect(obj, *args, **kwargs)
elif used_backend in (BackendEnum.SA_13, BackendEnum.SA_14,):
    sa_inspect = base_sa_inspect
else:
    raise ImportError("Undefined backend: {}".format(used_backend))


def as_str(s: Union[str, bytes]) -> str:
    if isinstance(s, bytes):
        return s.decode("utf-8")

    return str(s)


def prettify_class_name(name: str) -> str:
    return re.sub(r"(?<=.)([A-Z])", r" \1", name)


def slugify_class_name(name: str) -> str:
    dashed = re.sub("(.)([A-Z][a-z]+)", r"\1-\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1-\2", dashed).lower()
