import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="session")
def postgres_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run real PostgreSQL integration tests")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must point to PostgreSQL with database name ending in _test")
    if url == Settings().database_url:
        pytest.fail("Test and application database URLs must differ")
    return url


@pytest.fixture
def api(postgres_url):
    # Isolated schema, never DROP DATABASE or reset the user's public schema.
    schema = "test_" + uuid.uuid4().hex
    admin = create_engine(postgres_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    parsed = make_url(postgres_url)
    scoped_url = parsed.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
        hide_password=False
    )
    config = Config("alembic.ini")
    config.attributes["database_url"] = scoped_url
    application = None
    try:
        command.upgrade(config, "head")
        application = create_app(Settings(database_url=scoped_url))
        with TestClient(application) as client:
            yield client, application
    finally:
        if application:
            application.state.engine.dispose()
        # The schema name is generated locally, quoted, and scoped to this test.
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def trip(api):
    client, application = api
    users = [
        client.post("/api/v1/users", json={"name": name}).json()["id"]
        for name in ("Mohit", "Rahul", "Ankit")
    ]
    group = client.post("/api/v1/groups", json={"name": "Goa Trip"}).json()["id"]
    for user in users:
        assert client.put(f"/api/v1/groups/{group}/members/{user}").status_code == 201
    return client, application, group, users
