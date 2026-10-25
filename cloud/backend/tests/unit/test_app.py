"""TC-C02 and /livez, /healthz behaviour without the compose stack."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.health import run_checks
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


def test_a_hanging_check_is_reported_as_error_within_the_timeout():
    async def hangs() -> str:
        await asyncio.sleep(60)
        return "ok"

    async def ok() -> str:
        return "ok"

    started = time.monotonic()
    result = asyncio.run(run_checks({"slow": hangs(), "fast": ok()}, timeout_s=0.2))
    assert result == {"slow": "error", "fast": "ok"}
    assert time.monotonic() - started < 2


# --- CORS and /auth/config (D14) -----------------------------------------------------------------

def settings_with(**overrides) -> Settings:
    return Settings(database_url="postgresql+psycopg://u:p@127.0.0.1:1/db", zitadel_url="http://127.0.0.1:1",
                    emqx_status_url="http://127.0.0.1:1/status", **overrides)


def test_cors_origins_are_read_comma_separated(monkeypatch):
    monkeypatch.setenv("MM_CORS_ORIGINS", " http://localhost:3000/ , https://dash.example ")
    assert settings_with().cors_origins == ["http://localhost:3000", "https://dash.example"]


def preflight(client: TestClient, origin: str):
    return client.options("/me", headers={"Origin": origin, "Access-Control-Request-Method": "GET",
                                          "Access-Control-Request-Headers": "authorization"})


def test_cors_allows_only_the_configured_origins():
    with TestClient(create_app(settings_with(cors_origins="http://localhost:3000"))) as client:
        allowed = preflight(client, "http://localhost:3000")
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "authorization" in allowed.headers["access-control-allow-headers"].lower()
        assert "access-control-allow-credentials" not in allowed.headers
        assert "access-control-allow-origin" not in preflight(client, "https://evil.example").headers


def test_without_cors_origins_no_cors_headers_are_sent():
    with TestClient(create_app(settings_with())) as client:
        assert "access-control-allow-origin" not in preflight(client, "http://localhost:3000").headers


def test_auth_config_is_503_until_zitadel_is_configured(tmp_path):
    with TestClient(create_app(settings_with(zitadel_config_file=tmp_path / "missing.json"))) as client:
        assert client.get("/auth/config").status_code == 503


def test_auth_config_needs_the_dashboard_app(tmp_path):
    config = tmp_path / "zitadel.json"
    config.write_text('{"issuer": "http://localhost:8080", "project_id": "p1", "default_org_id": "o1"}')
    with TestClient(create_app(settings_with(zitadel_config_file=config))) as client:
        assert client.get("/auth/config").status_code == 503


def test_auth_config_gives_the_dashboard_what_it_needs_to_sign_in(tmp_path):
    config = tmp_path / "zitadel.json"
    config.write_text('{"issuer": "http://localhost:8080", "project_id": "p1", "default_org_id": "o1",'
                      ' "dashboard_client_id": "c1@medmusketeer"}')
    with TestClient(create_app(settings_with(zitadel_config_file=config))) as client:
        response = client.get("/auth/config")
    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in ("issuer", "client_id", "project_id")} == {
        "issuer": "http://localhost:8080", "client_id": "c1@medmusketeer", "project_id": "p1"}
    scopes = body["scope"].split()
    assert {"openid", "urn:zitadel:iam:org:project:id:p1:aud", "urn:zitadel:iam:org:projects:roles",
            "urn:zitadel:iam:user:resourceowner"} <= set(scopes)
