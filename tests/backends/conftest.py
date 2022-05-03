from sqladmin.backends import get_used_backend, BackendEnum
from tests.settings import Settings, get_settings


used_backend: BackendEnum = get_used_backend()


if used_backend in (BackendEnum.SA_13, BackendEnum.SA_14):
    from .sqlalchemy.conftest import *
elif used_backend == BackendEnum.GINO:
    from .gino.conftest import *
else:
    raise ImportError('Undefined backend')
