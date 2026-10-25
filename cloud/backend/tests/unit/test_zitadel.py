"""app.zitadel.ZitadelAdmin against a scripted ZITADEL (httpx MockTransport): the calls it makes,
the compensation when a later step fails, and reloading a replaced token. The real ZITADEL is
covered by TC-C13 (test_stack)."""
import asyncio
import json

import httpx
import pytest

from app.zitadel import ZitadelAdmin, ZitadelError
from tests.tokens import CONFIG, DEFAULT_ORG_ID, PROJECT_ID

CLIENT_ORG = "400000000000000001"


class ScriptedZitadel:
    """Answers by (method, path); records every request. An answer may be a status code."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers[(request.method, request.url.path)]
        if callable(answer):
            answer = answer(request)
        if isinstance(answer, int):
            return httpx.Response(answer, json={"code": 9, "message": f"status {answer}"})
        return httpx.Response(200, json=answer)

    def calls(self) -> list[tuple[str, str]]:
        return [(request.method, request.url.path) for request in self.requests]


@pytest.fixture
def token_file(tmp_path):
    path = tmp_path / "zitadel-api.pat"
    path.write_text("token-1\n")
    return path


def admin(script: ScriptedZitadel, token_file) -> ZitadelAdmin:
    http = httpx.AsyncClient(transport=httpx.MockTransport(script.handler))
    return ZitadelAdmin(CONFIG, "http://zitadel-api:8080/", http, token_file)


USER_ANSWERS = {
    ("POST", "/management/v1/granted_projects/_search"): {"result": [
        {"projectId": "other", "grantId": "g-other"}, {"projectId": PROJECT_ID, "grantId": "g-1"}]},
    ("POST", "/v2/users/human"): {"userId": "u-1"},
    ("POST", "/management/v1/users/u-1/grants"): {"userGrantId": "ug-1"},
    ("POST", "/v2/users/u-1/invite_code"): {"inviteCode": "ABC123"},
    ("DELETE", "/v2/users/u-1"): {},
}


def test_creating_a_user_grants_the_role_through_the_project_grant(token_file):
    script = ScriptedZitadel(USER_ANSWERS)
    new_user = asyncio.run(admin(script, token_file).create_user(CLIENT_ORG, "doctor", "d@x.example", "Dee", "Doc"))
    assert (new_user.user_id, new_user.invite_code) == ("u-1", "ABC123")
    assert script.calls() == [("POST", "/management/v1/granted_projects/_search"), ("POST", "/v2/users/human"),
                              ("POST", "/management/v1/users/u-1/grants"), ("POST", "/v2/users/u-1/invite_code")]
    search, human, grant, _ = script.requests
    assert search.headers["x-zitadel-orgid"] == CLIENT_ORG
    assert all(r.headers["Host"] == "localhost:8080" and r.headers["Authorization"] == "Bearer token-1"
               for r in script.requests)
    assert json.loads(human.content)["organization"] == {"orgId": CLIENT_ORG}
    assert json.loads(human.content)["email"] == {"email": "d@x.example", "returnCode": {}}  # no e-mail sent
    assert json.loads(grant.content) == {"projectId": PROJECT_ID, "projectGrantId": "g-1", "roleKeys": ["doctor"]}


def test_a_failed_grant_deletes_the_new_user(token_file):
    script = ScriptedZitadel({**USER_ANSWERS, ("POST", "/management/v1/users/u-1/grants"): 400})
    with pytest.raises(ZitadelError) as excinfo:
        asyncio.run(admin(script, token_file).create_user(CLIENT_ORG, "doctor", "d@x.example", "Dee", "Doc"))
    assert excinfo.value.status == 400
    assert script.calls()[-1] == ("DELETE", "/v2/users/u-1")


def test_only_organisation_roles_can_be_granted(token_file):
    with pytest.raises(ValueError):
        asyncio.run(admin(ScriptedZitadel({}), token_file).create_user(CLIENT_ORG, "system_admin", "a@x.example", "A", "B"))


def test_an_organisation_gets_the_project_granted_or_is_deleted_again(token_file):
    answers = {
        ("POST", "/v2/organizations"): {"organizationId": CLIENT_ORG},
        ("POST", f"/management/v1/projects/{PROJECT_ID}/grants"): {"grantId": "g-1"},
        ("DELETE", f"/v2/organizations/{CLIENT_ORG}"): {},
    }
    script = ScriptedZitadel(answers)
    assert asyncio.run(admin(script, token_file).create_organisation("Clinic")) == CLIENT_ORG
    grant = script.requests[1]
    assert grant.headers["x-zitadel-orgid"] == DEFAULT_ORG_ID  # the project's owner grants it
    assert json.loads(grant.content) == {"grantedOrgId": CLIENT_ORG, "roleKeys": ["org_admin", "doctor", "patient"]}

    failing = ScriptedZitadel({**answers, ("POST", f"/management/v1/projects/{PROJECT_ID}/grants"): 500})
    with pytest.raises(ZitadelError):
        asyncio.run(admin(failing, token_file).create_organisation("Clinic"))
    assert failing.calls()[-1] == ("DELETE", f"/v2/organizations/{CLIENT_ORG}")


def test_a_replaced_token_is_reloaded_after_a_401(token_file):
    script = ScriptedZitadel({("POST", "/v2/users/u-1/deactivate"):
                              lambda request: {} if request.headers["Authorization"] == "Bearer token-2" else 401})
    client = admin(script, token_file)
    with pytest.raises(ZitadelError) as excinfo:  # same token in the file: no retry
        asyncio.run(client.deactivate_user("u-1"))
    assert excinfo.value.status == 401 and len(script.requests) == 1
    token_file.write_text("token-2\n")
    asyncio.run(client.deactivate_user("u-1"))
    assert [r.headers["Authorization"] for r in script.requests] == ["Bearer token-1", "Bearer token-1", "Bearer token-2"]


def test_an_unreachable_zitadel_is_an_error_with_status_0(token_file):
    def refuse(request):
        raise httpx.ConnectError("refused")

    client = ZitadelAdmin(CONFIG, "http://zitadel-api:8080", httpx.AsyncClient(transport=httpx.MockTransport(refuse)),
                          token_file)
    with pytest.raises(ZitadelError) as excinfo:
        asyncio.run(client.deactivate_user("u-1"))
    assert excinfo.value.status == 0


def test_deactivating_an_already_inactive_user_succeeds(token_file):
    # ZITADEL v4.20.0 answers a second deactivate with 400 "User already inactive" (checked 2026-10-24).
    answers = {("POST", "/v2/users/u-1/deactivate"): 400, ("GET", "/v2/users/u-1"): {"user": {"state": "USER_STATE_INACTIVE"}}}
    asyncio.run(admin(ScriptedZitadel(answers), token_file).deactivate_user("u-1"))

    still_active = {**answers, ("GET", "/v2/users/u-1"): {"user": {"state": "USER_STATE_ACTIVE"}}}
    with pytest.raises(ZitadelError) as excinfo:
        asyncio.run(admin(ScriptedZitadel(still_active), token_file).deactivate_user("u-1"))
    assert excinfo.value.status == 400


# --- profiles (app.directory) ------------------------------------------------------------------

def profile_answer(request: httpx.Request) -> dict:
    ids = json.loads(request.content)["queries"][0]["inUserIdsQuery"]["userIds"]
    return {"result": [{"userId": user_id, "human": {"profile": {"givenName": f"G-{user_id}", "familyName": "F"},
                                                     "email": {"email": f"{user_id}@x.example"}}}
                       for user_id in ids if user_id != "gone"]}


def test_profiles_are_read_in_batches_and_cached(token_file, monkeypatch):
    monkeypatch.setattr("app.zitadel.PROFILE_BATCH", 2)
    script = ScriptedZitadel({("POST", "/v2/users"): profile_answer})
    client = admin(script, token_file)
    found = asyncio.run(client.profiles(["u1", "u2", "u3", "gone"]))
    assert set(found) == {"u1", "u2", "u3"}  # a user ZITADEL does not return is left out
    assert found["u1"].given_name == "G-u1" and found["u1"].email == "u1@x.example"
    assert len(script.requests) == 2  # four ids in batches of two
    asyncio.run(client.profiles(["u1", "u2"]))
    assert len(script.requests) == 2  # cached


def test_profiles_are_read_again_after_the_ttl(token_file, monkeypatch):
    script = ScriptedZitadel({("POST", "/v2/users"): profile_answer})
    client = admin(script, token_file)
    asyncio.run(client.profiles(["u1"]))
    monkeypatch.setattr("app.zitadel.PROFILE_TTL_S", -1)
    client._profiles = {key: (0.0, value) for key, (_, value) in client._profiles.items()}  # expired
    asyncio.run(client.profiles(["u1"]))
    assert len(script.requests) == 2


def test_a_zitadel_failure_reading_profiles_is_raised(token_file):
    script = ScriptedZitadel({("POST", "/v2/users"): 503})
    with pytest.raises(ZitadelError):
        asyncio.run(admin(script, token_file).profiles(["u1"]))
