"""The bootstrap's dashboard app (D14) and SMTP provider against a scripted ZITADEL: each created
once, then kept in line with the configuration. The real ZITADEL is covered by TC-C19 and TC-C43
(test_stack)."""
import json

import httpx
import pytest

from app.zitadel_bootstrap import DASHBOARD_APP, SMTP_PROVIDER, Zitadel, smtp_settings

PROJECT = "p1"
ORG = "o1"
SEARCH = f"/management/v1/projects/{PROJECT}/apps/_search"


def scripted(answers: dict) -> tuple[Zitadel, list[httpx.Request]]:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status, body = answers[(request.method, request.url.path)]
        return httpx.Response(status, json=body)

    zitadel = Zitadel("http://zitadel-api:8080", "http://localhost:8080", "token")
    zitadel.http = httpx.Client(base_url="http://zitadel-api:8080", transport=httpx.MockTransport(handler))
    return zitadel, requests


def test_the_dashboard_app_is_created_as_a_pkce_browser_app_with_jwt_tokens():
    zitadel, requests = scripted({
        ("POST", SEARCH): (200, {}),
        ("POST", f"/management/v1/projects/{PROJECT}/apps/oidc"): (200, {"appId": "a1", "clientId": "c1"}),
    })
    assert zitadel.ensure_dashboard_app(ORG, PROJECT, ["http://localhost:3000", "http://127.0.0.1:3000"]) == "c1"
    body = json.loads(requests[1].content)
    assert body["name"] == DASHBOARD_APP
    assert body["appType"] == "OIDC_APP_TYPE_USER_AGENT"
    assert body["authMethodType"] == "OIDC_AUTH_METHOD_TYPE_NONE"  # no secret: PKCE
    assert body["accessTokenType"] == "OIDC_TOKEN_TYPE_JWT" and body["accessTokenRoleAssertion"] is True
    assert body["redirectUris"] == ["http://localhost:3000/auth/callback", "http://127.0.0.1:3000/auth/callback"]
    assert body["postLogoutRedirectUris"] == ["http://localhost:3000/", "http://127.0.0.1:3000/"]
    assert body["devMode"] is True  # http origins
    assert requests[1].headers["x-zitadel-orgid"] == ORG


@pytest.mark.parametrize("status,body", [(200, {}), (400, {"code": 9, "message": "No changes (COMMAND-1m88i)"})])
def test_an_existing_app_is_updated_to_the_current_origins(status, body):
    update = f"/management/v1/projects/{PROJECT}/apps/a1/oidc_config"
    zitadel, requests = scripted({
        ("POST", SEARCH): (200, {"result": [{"id": "a1", "oidcConfig": {"clientId": "c1"}}]}),
        ("PUT", update): (status, body),
    })
    assert zitadel.ensure_dashboard_app(ORG, PROJECT, ["https://dash.example"]) == "c1"
    sent = json.loads(requests[1].content)
    assert sent["redirectUris"] == ["https://dash.example/auth/callback"] and sent["devMode"] is False


def test_http_and_https_origins_cannot_share_the_app():
    # dev mode would relax redirect checks for the https (production) origin as well
    zitadel, requests = scripted({})
    with pytest.raises(SystemExit):
        zitadel.ensure_dashboard_app(ORG, PROJECT, ["http://localhost:3000", "https://dash.example"])
    assert requests == []


@pytest.mark.parametrize("message", ["invalid redirect uri", "Errors.Project.App.RedirectURIChanged"])
def test_a_refused_update_stops_the_bootstrap(message):
    zitadel, _ = scripted({
        ("POST", SEARCH): (200, {"result": [{"id": "a1", "oidcConfig": {"clientId": "c1"}}]}),
        ("PUT", f"/management/v1/projects/{PROJECT}/apps/a1/oidc_config"): (400, {"message": message}),
    })
    with pytest.raises(RuntimeError):
        zitadel.ensure_dashboard_app(ORG, PROJECT, ["https://dash.example"])


RESEND = {"MM_SMTP_HOST": "smtp.resend.com:465", "MM_SMTP_USER": "resend", "MM_SMTP_PASSWORD": "re_key",
          "MM_SMTP_SENDER": "no-reply@medmusketeer.site"}
SMTP = smtp_settings(RESEND)


def test_smtp_settings_default_to_tls_and_the_medmusketeer_sender_name():
    assert SMTP == {"host": "smtp.resend.com:465", "user": "resend", "password": "re_key", "tls": True,
                    "senderAddress": "no-reply@medmusketeer.site", "senderName": "MedMusketeer", "replyToAddress": ""}
    assert smtp_settings({**RESEND, "MM_SMTP_TLS": "False"})["tls"] is False


def test_no_smtp_host_means_no_provider():
    assert smtp_settings({}) is None and smtp_settings({"MM_SMTP_HOST": "  ", "MM_SMTP_SENDER": "x@y.z"}) is None


@pytest.mark.parametrize("override", [{"MM_SMTP_HOST": "smtp.resend.com"}, {"MM_SMTP_SENDER": ""},
                                      {"MM_SMTP_TLS": "yes"}])
def test_bad_smtp_settings_stop_the_bootstrap(override):
    with pytest.raises(SystemExit):
        smtp_settings({**RESEND, **override})


def test_the_smtp_provider_is_created_and_activated():
    zitadel, requests = scripted({
        ("POST", "/admin/v1/email/_search"): (200, {"result": [{"id": "other", "description": "someone else's"}]}),
        ("POST", "/admin/v1/email/smtp"): (200, {"id": "s1"}),
        ("POST", "/admin/v1/email/s1/_activate"): (200, {}),
    })
    assert zitadel.ensure_smtp_provider(SMTP) == "s1"
    assert json.loads(requests[1].content) == {"description": SMTP_PROVIDER, **SMTP}
    assert [r.url.path for r in requests][-1] == "/admin/v1/email/s1/_activate"


@pytest.mark.parametrize("status,body", [(200, {}), (400, {"message": "No changes (COMMAND-...)"})])
def test_an_active_smtp_provider_is_updated_and_not_activated_again(status, body):
    zitadel, requests = scripted({
        ("POST", "/admin/v1/email/_search"): (200, {"result": [
            {"id": "s1", "description": SMTP_PROVIDER, "state": "EMAIL_PROVIDER_ACTIVE"}]}),
        ("PUT", "/admin/v1/email/smtp/s1"): (status, body),
    })
    assert zitadel.ensure_smtp_provider(SMTP) == "s1"
    assert [(r.method, r.url.path) for r in requests] == [("POST", "/admin/v1/email/_search"),
                                                          ("PUT", "/admin/v1/email/smtp/s1")]
    assert json.loads(requests[1].content)["password"] == "re_key"  # a rotated key takes effect


def test_an_inactive_smtp_provider_is_activated():
    zitadel, requests = scripted({
        ("POST", "/admin/v1/email/_search"): (200, {"result": [
            {"id": "s1", "description": SMTP_PROVIDER, "state": "EMAIL_PROVIDER_INACTIVE"}]}),
        ("PUT", "/admin/v1/email/smtp/s1"): (200, {}),
        ("POST", "/admin/v1/email/s1/_activate"): (200, {}),
    })
    zitadel.ensure_smtp_provider(SMTP)
    assert requests[-1].url.path == "/admin/v1/email/s1/_activate"


def test_a_refused_smtp_update_stops_the_bootstrap():
    zitadel, _ = scripted({
        ("POST", "/admin/v1/email/_search"): (200, {"result": [{"id": "s1", "description": SMTP_PROVIDER}]}),
        ("PUT", "/admin/v1/email/smtp/s1"): (400, {"message": "invalid host"}),
    })
    with pytest.raises(RuntimeError):
        zitadel.ensure_smtp_provider(SMTP)
