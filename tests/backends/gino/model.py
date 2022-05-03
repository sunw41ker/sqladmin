from sqladmin.backends.gino.models import GinoModelMapper

from .base import metadata as sa_gino



class Mapper:
    """Mixin which adds custom gino mapper
    """
    
    @sa_gino.declared_attr
    def __mapper__(cls) -> GinoModelMapper:
        base = super()
        if hasattr(base, '__mapper__'):
            mapper = super().__mapper__()
        else:
            mapper = GinoModelMapper(model=cls)
        return mapper

