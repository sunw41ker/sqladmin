from gino.declarative import Model, ModelType, inspect_model_type

import sqlalchemy as sa

from .models import (
    BaseModelRelationshipsLoader,
    find_model_class,
    get_gino_mapper_for
)


SA_MODEL_MAPPER_KEY = 'mapper'


# replace default gino model mapper
sa.inspection._registrars.pop(ModelType, None)
sa.inspection._registrars.pop(Model, None)


@sa.inspection._inspects(ModelType)
def inspect_admin_model_type(target: ModelType):
    return get_gino_mapper_for(target=target)


@sa.inspection._inspects(Model)
def inspect_admin_model(target: Model):
    return get_gino_mapper_for(target=target)


@sa.inspection._inspects(str)
def inspect_admin_str(target: str):
    base_models = list(BaseModelRelationshipsLoader.get_base_model_registry())
    if len(base_models) > 0:
        try:
            model_class = find_model_class(target, base_model=base_models[0])
        except ModuleNotFoundError as e:
            print(f'Module/target {target} not found')
            return None
        if model_class is not None:
            mapper = get_gino_mapper_for(model_class)
            setattr(model_class, SA_MODEL_MAPPER_KEY, mapper)
            setattr(model_class, 'persist_selectable', model_class.__table__)
            setattr(model_class, 'local_table', model_class.__table__)
        return mapper
        return model_class
    return None
