from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_hosted_url_selects_psycopg_without_losing_password_or_ssl(scheme):
    settings = Settings(
        database_url=f"{scheme}://demo:p%40ss%25word@db.example/expenses?sslmode=require"
    )
    parsed = make_url(settings.database_url)
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.password == "p@ss%word"
    assert parsed.query["sslmode"] == "require"


def test_ui_assets_are_served_when_working_directory_is_not_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    application = create_app(Settings())
    with TestClient(application) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Fairshare" in response.text
        assert response.headers["content-type"].startswith("text/html")
        for asset in ("style.css", "app.js"):
            assert client.get(f"/static/{asset}").status_code == 200
        assert "/" not in client.get("/openapi.json").json()["paths"]
        assert not list(Path(tmp_path).iterdir())
