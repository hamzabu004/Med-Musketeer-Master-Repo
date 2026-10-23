"""TC-C02 and /livez, /healthz behaviour without the compose stack."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.settings import Settings

REQUIRED = ("MM_DATABASE_URL", "MM_ZITADEL_URL", "MM_EMQX_STATUS_URL")


@pytest.fixture
def no_settings(monkeypatch):
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("missing", REQUIRED)
def test_tc_c02_api_refuses_to_start_without_required_setting(monkeypatch, no_settings, missing):
    for name in REQUIRED:
        if name != missing:
            monkeypatch.setenv(name, "postgresql+psycopg://u:p@127.0.0.1:1/db" if name == "MM_DATABASE_URL" else "http://127.0.0.1:1")
    with pytest.raises(ValidationError) as excinfo:
        create_app()
    assert missing.removeprefix("MM_").lower() in str(excinfo.value)


def test_database_url_is_not_shown_in_settings_repr():
    settings = Settings(database_url="postgresql+psycopg://u:hunter2@db/x", zitadel_url="http://z", emqx_status_url="http://e")
    assert "hunter2" not in repr(settings)


@pytest.fixture
def unreachable_app():
    # Port 1 on loopback refuses connections immediately, so every dependency check fails fast.
    settings = Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/db",
        zitadel_url="http://127.0.0.1:1",
        emqx_status_url="http://127.0.0.1:1/status",
        dependency_timeout_s=1,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_livez_is_ok_without_dependencies(unreachable_app):
    response = unreachable_app.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_reports_each_failed_dependency_with_503(unreachable_app):
    response = unreachable_app.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"database": "error", "zitadel": "error", "emqx": "error"},
    }
