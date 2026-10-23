"""TC-C12 (principal part): a valid token is accepted only for a registered user whose role and
organisation match the token. Tokens are signed locally; the users live in the real database."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from app.settings import Settings
from app.tokens import TokenVerifier
from tests.integration.test_schema import add_org
from tests.tokens import CONFIG, DEFAULT_ORG_ID, FakeJwks, SigningKey

pytestmark = pytest.mark.integration


@pytest.fixture
def key():
    return SigningKey()


@pytest.fixture
def client(migrated, key):
    settings = Settings(database_url=migrated["api"], zitadel_url="http://zitadel-api:8080",
                        emqx_status_url="http://127.0.0.1:1/status")
    app = create_app(settings)
    with TestClient(app) as test_client:
        jwks_http = FakeJwks(key).client()
        app.state.verifier = TokenVerifier(CONFIG, "http://zitadel-api:8080", jwks_http)
        yield test_client


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(db, sub: str, role: str, org_id=None) -> uuid.UUID:
    return db.scalar(text("INSERT INTO users (zitadel_sub, role, org_id) VALUES (:s, :r, :o) RETURNING user_id"),
                     {"s": sub, "r": role, "o": org_id})


def org_with_zitadel_id(db, zitadel_org_id: str, status: str = "active") -> uuid.UUID:
    org_id = add_org(db)
    db.execute(text("UPDATE organisations SET zitadel_org_id = :z, status = :s WHERE org_id = :o"),
               {"z": zitadel_org_id, "s": status, "o": org_id})
    return org_id


def test_tc_c12_a_registered_system_admin_is_accepted(client, db, key):
    user_id = register(db, "admin-sub", "system_admin")
    response = client.get("/me", headers=bearer(key.token(sub="admin-sub")))
    assert response.status_code == 200
    assert response.json() == {"user_id": str(user_id), "role": "system_admin", "org_id": None}
    assert client.get("/admin/devices", headers=bearer(key.token(sub="admin-sub"))).status_code == 200


def test_tc_c12_a_registered_doctor_is_accepted_in_their_organisation(client, db, key):
    org_id = org_with_zitadel_id(db, "z-org-a")
    user_id = register(db, "doc-sub", "doctor", org_id)
    token = key.token(sub="doc-sub", roles={"doctor": {"z-org-a": "a"}}, org="z-org-a")
    assert client.get("/me", headers=bearer(token)).json() == {
        "user_id": str(user_id), "role": "doctor", "org_id": str(org_id)}
    assert client.get("/admin/devices", headers=bearer(token)).status_code == 403  # D9: registry is system admin only


def test_tc_c12_requests_without_a_valid_bearer_token_get_401(client, key):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/me", headers=bearer("garbage")).status_code == 401
    assert client.get("/me", headers=bearer(SigningKey().token())).status_code == 401  # unknown key
    assert client.get("/me", headers=bearer(key.token(aud=["other"]))).status_code == 401


@pytest.mark.parametrize("case", [
    "unregistered", "role differs", "two roles", "no role", "role from another org",
    "other organisation", "suspended organisation", "admin from client org",
])
def test_tc_c12_valid_tokens_that_do_not_match_a_user_get_403(client, db, key, case):
    org_a = org_with_zitadel_id(db, "z-org-a")
    org_b = org_with_zitadel_id(db, "z-org-b")
    suspended = org_with_zitadel_id(db, "z-org-s", status="suspended")
    register(db, "doc-a", "doctor", org_a)
    register(db, "doc-s", "doctor", suspended)
    register(db, "admin", "system_admin")
    tokens = {
        "unregistered": key.token(sub="nobody", roles={"doctor": {"z-org-a": "a"}}, org="z-org-a"),
        "role differs": key.token(sub="doc-a", roles={"org_admin": {"z-org-a": "a"}}, org="z-org-a"),
        "two roles": key.token(sub="doc-a", roles={"doctor": {"z-org-a": "a"}, "patient": {"z-org-a": "a"}}, org="z-org-a"),
        "no role": key.token(sub="doc-a", roles={}, org="z-org-a"),
        "role from another org": key.token(sub="doc-a", roles={"doctor": {"z-org-b": "b"}}, org="z-org-a"),
        "other organisation": key.token(sub="doc-a", roles={"doctor": {"z-org-b": "b"}}, org="z-org-b"),
        "suspended organisation": key.token(sub="doc-s", roles={"doctor": {"z-org-s": "s"}}, org="z-org-s"),
        "admin from client org": key.token(sub="admin", roles={"system_admin": {"z-org-a": "a"}}, org="z-org-a"),
    }
    assert org_b  # registered so "other organisation" refers to a real organisation
    assert client.get("/me", headers=bearer(tokens[case])).status_code == 403


def test_without_zitadel_config_authentication_answers_503(migrated):
    settings = Settings(database_url=migrated["api"], zitadel_url="http://127.0.0.1:1",
                        emqx_status_url="http://127.0.0.1:1/status", zitadel_config_file="/nonexistent.json")
    with TestClient(create_app(settings)) as client:
        assert client.get("/me", headers=bearer("x")).status_code == 503
        assert client.get("/livez").status_code == 200


def test_unknown_roles_in_the_token_are_ignored(client, db, key):
    register(db, "admin", "system_admin")
    token = key.token(sub="admin", roles={"system_admin": {DEFAULT_ORG_ID: "d"}, "zitadel_internal": {DEFAULT_ORG_ID: "d"}})
    assert client.get("/me", headers=bearer(token)).status_code == 200
