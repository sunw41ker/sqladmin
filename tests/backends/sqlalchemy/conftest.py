import pytest

from tests.settings import Settings
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@pytest.fixture(autouse=True, scope="session")
async def engine(
    settings: Settings
) -> Engine:
    return create_engine(settings.TEST_DATABASE_URI_SYNC)
