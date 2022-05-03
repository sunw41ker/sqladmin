from functools import lru_cache


@lru_cache
def can_use():
    try:
        from gino.ext.starlette import Gino  # type: ignore
        return Gino is not None
    except ImportError:
        pass
    except ModuleNotFoundError:
        pass
    return False
    