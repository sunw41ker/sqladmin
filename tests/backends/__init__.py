from sqladmin.backends import get_used_backend, BackendEnum


used_backend = get_used_backend()


if used_backend in (BackendEnum.SA_13, BackendEnum.SA_14):
    pass
elif used_backend == BackendEnum.GINO:
    # from .gino import *
    pass
else:
    raise ImportError('Undefined backend')
