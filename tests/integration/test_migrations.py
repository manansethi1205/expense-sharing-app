import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

pytestmark = pytest.mark.integration


def test_schema_matches_models_and_migration_round_trip(api):
    _, application = api
    config = Config("alembic.ini")
    config.attributes["database_url"] = application.state.settings.database_url
    command.check(config)
    command.downgrade(config, "base")
    assert set(inspect(application.state.engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    assert len(inspect(application.state.engine).get_table_names()) == 7
