
from typing import Optional, List, Set


class BaseRelationshipsLoader:
    def __init__(self):
        pass
    
    def import_from(self, path: str, packages:Optional[List[str]]=[]):
        from importlib import import_module
        
        path_list = path.split('.')
        cls_name = path_list[len(path_list) - 1]
        if len(path_list) == 1:
            path = '.'

        for package in packages:
            try:
                cls = getattr(import_module(path, package=package), cls_name, None)
                if cls is not None:
                    break
            except ModuleNotFoundError():
                cls = None
        else:
            cls = getattr(import_module(path), cls_name, None)

        if cls is None:
            raise ModuleNotFoundError()
        
        return cls

    def load(self, name: str):
        return self.import_from(name)
        raise NotImplementedError()


class BaseModelRelationshipsLoader(BaseRelationshipsLoader):
    RELATIONSHIPS_LOADER_KEY: str = None
    base_model_registry: Set = set()
    
    def __init__(self, base_model=None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.base_model = base_model
        if self.base_model is not None:
            self._register()

    def _register(self) -> None:
        loader = getattr(self.base_model, self.RELATIONSHIPS_LOADER_KEY, None)
        if loader is not self and isinstance(loader, BaseModelRelationshipsLoader):
            loader._unregister()
        elif loader is not None:
            raise AttributeError(f'Attribute is already set with undefined value:', str(loader))
        setattr(self.base_model, self.RELATIONSHIPS_LOADER_KEY, self)
        self.base_model_registry.add(self.base_model)
    
    def _unregister(self) -> None:
        loader = getattr(self.base_model, self.RELATIONSHIPS_LOADER_KEY, None)
        if loader is None:
            return
        delattr(self.base_model, self.RELATIONSHIPS_LOADER_KEY)
        self.base_model_registry.remove(self.base_model)
        self.base_model = None

    @classmethod
    def get_base_model_registry(cls) -> Set:
        return cls.base_model_registry
    
    @classmethod
    def get_base_model(cls):
        if not len(cls.base_model_registry):
            return None
        return list(cls.base_model_registry)[0]
    
    
    @classmethod
    def get(cls, base_model) -> Optional[BaseRelationshipsLoader]:
        return getattr(base_model, cls.RELATIONSHIPS_LOADER_KEY, None)
    
    @classmethod
    def get_or_init(cls, base_model) -> BaseRelationshipsLoader:
        loader = cls.get(base_model=base_model)
        if loader is None:
            loader = cls(base_model=base_model)
        return loader
    
    @property
    def models(self) -> List:
        if self.base_model is None:
            return []
        return self.base_model.__subclasses__()
    
    def load(self, name: str):
        for c in self.models:
            if f'{c.__module__}.{c.__name__}'.endswith(name):
                return c
        return super().load(name)