"""seed-dev's ZITADEL step against a scripted ZITADEL: a failure part-way leaves nothing behind, so the
empty-stack guard stays truthful and the command can be re-run. The real run is covered by TC-C19."""
from dataclasses import replace

import httpx
import pytest

from app.dev_seed import PEOPLE, create_zitadel_people, undo
from app.tokens import ZitadelConfig
from app.zitadel_bootstrap import Zitadel

CONFIG = ZitadelConfig(issuer="http://localhost:8080", project_id="p1", default_org_id="default")


def scripted(fail_at_user: int) -> tuple[Zitadel, list[httpx.Request]]:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if request.method == "DELETE":
            return httpx.Response(200, json={})
        if path == "/v2/organizations":
            return httpx.Response(201, json={"organizationId": "o1"})
        if path.endswith("/grants") and "projects" in path:
            return httpx.Response(200, json={"grantId": "g1"})
        if path == "/v2/users/human":
            created = sum(1 for r in requests if r.url.path == "/v2/users/human")
            if created == fail_at_user:
                return httpx.Response(400, json={"message": "Password is too weak"})
            return httpx.Response(201, json={"userId": f"u{created}"})
        return httpx.Response(200, json={})  # grant searches and user grants

    zitadel = Zitadel("http://zitadel-api:8080", CONFIG.issuer, "token")
    zitadel.http = httpx.Client(base_url="http://zitadel-api:8080", transport=httpx.MockTransport(handler))
    return zitadel, requests


def test_a_failure_part_way_deletes_what_was_created_in_zitadel():
    zitadel, requests = scripted(fail_at_user=3)  # after the system admin and the org admin
    people, created = [replace(person) for person in PEOPLE], []
    with pytest.raises(RuntimeError):
        create_zitadel_people(zitadel, CONFIG, people, "weak", created)
    undo(zitadel, created)
    deleted = [r.url.path for r in requests if r.method == "DELETE"]
    # the system admin (default organisation) and the organisation, which takes its users with it
    assert deleted == ["/v2/users/u1", "/v2/organizations/o1"]
    assert all(person.zitadel_sub == "" for person in PEOPLE)  # the templates are untouched
