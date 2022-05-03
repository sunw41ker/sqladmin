from .backends import used_backend, BackendEnum


if used_backend == BackendEnum.GINO:
    from .subtest_admin_gino import *
elif used_backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
    from .subtest_admin_async import *
    from .subtest_admin_sync import *
