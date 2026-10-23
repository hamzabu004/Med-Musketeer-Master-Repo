"""One-off job: set up MedMusketeer in ZITADEL, then write the API's (non-secret) ZITADEL config.

Idempotent, so it runs on every `compose up`:
1. the project "MedMusketeer" in the instance's default organisation, with role assertion on, so
   roles appear in access tokens;
2. the four project roles (D2);
3. the system_admin role for ZITADEL's first human admin (zitadel-admin@...), so the instance admin
   can act as the MedMusketeer system admin once registered with `python -m app.manage`;
4. the API's service account `mm-api` with the instance role IAM_ORG_MANAGER (D12), and a token for
   it in MM_ZITADEL_API_TOKEN_FILE (replaced when it is missing or no longer works);
5. MM_ZITADEL_CONFIG_FILE = {"issuer", "project_id", "default_org_id"}.

Uses the IAM_OWNER service account token created by ZITADEL's first start
(ZITADEL_FIRSTINSTANCE_PATPATH). Run: python -m app.zitadel_bootstrap
"""
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.auth import ROLES

log = logging.getLogger("zitadel_bootstrap")

PROJECT_NAME = "MedMusketeer"
ROLE_NAMES = {"system_admin": "System admin", "org_admin": "Organisation admin", "doctor": "Doctor", "patient": "Patient"}
# ZITADEL stores the first admin as zitadel-admin@<organisation domain>.
FIRST_ADMIN_USERNAME_PREFIX = "zitadel-admin@"
# The API's service account: organisations, their users and grants, nothing instance-wide.
API_SERVICE_ACCOUNT = "mm-api"
API_INSTANCE_ROLE = "IAM_ORG_MANAGER"
API_TOKEN_LIFETIME = timedelta(days=365)


class Zitadel:
    """The few ZITADEL management (v1) calls the job and the stack tests need."""

    def __init__(self, url: str, issuer: str, token: str):
        self.http = httpx.Client(
            base_url=url,
            # ZITADEL picks the instance by Host, so internal calls carry the public host name.
            headers={"Authorization": f"Bearer {token}", "Host": urlsplit(issuer).netloc},
            timeout=15,
        )

    def call(self, method: str, path: str, org: str | None = None, ok: tuple[int, ...] = (200,), **kwargs) -> dict:
        headers = {"x-zitadel-orgid": org} if org else {}
        response = self.http.request(method, path, headers=headers, **kwargs)
        if response.status_code not in ok:
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}: {response.text[:300]}")
        return response.json() if response.content else {}

    def default_org_id(self) -> str:
        return self.call("GET", "/admin/v1/orgs/default")["org"]["id"]

    def find_project(self, org: str, name: str) -> str | None:
        found = self.call("POST", "/management/v1/projects/_search", org=org, json={
            "queries": [{"nameQuery": {"name": name, "method": "TEXT_QUERY_METHOD_EQUALS"}}]})
        return found["result"][0]["id"] if found.get("result") else None

    def ensure_project(self, org: str, name: str) -> str:
        project_id = self.find_project(org, name)
        if project_id is None:
            project_id = self.call("POST", "/management/v1/projects", org=org,
                                   json={"name": name, "projectRoleAssertion": True})["id"]
            log.info("created project %s", project_id)
        return project_id

    def ensure_roles(self, org: str, project_id: str, roles: dict[str, str]) -> None:
        existing = self.call("POST", f"/management/v1/projects/{project_id}/roles/_search", org=org, json={})
        have = {role["key"] for role in existing.get("result", [])}
        missing = [{"key": key, "displayName": name} for key, name in roles.items() if key not in have]
        if missing:
            self.call("POST", f"/management/v1/projects/{project_id}/roles/_bulk", org=org, json={"roles": missing})
            log.info("added roles %s", [role["key"] for role in missing])

    def find_user(self, org: str, username: str, method: str = "TEXT_QUERY_METHOD_EQUALS") -> str | None:
        found = self.call("POST", "/management/v1/users/_search", org=org, json={
            "queries": [{"userNameQuery": {"userName": username, "method": method}}]})
        results = found.get("result", [])
        if len(results) > 1:
            raise RuntimeError(f"{len(results)} users match {username!r}")
        return results[0]["id"] if results else None

    def create_machine_user(self, org: str, username: str, name: str) -> str:
        """A service account whose access tokens are JWTs (the API validates JWTs only)."""
        return self.call("POST", "/management/v1/users/machine", org=org, json={
            "userName": username, "name": name, "accessTokenType": "ACCESS_TOKEN_TYPE_JWT"})["userId"]

    def client_secret(self, org: str, user_id: str) -> tuple[str, str]:
        secret = self.call("PUT", f"/management/v1/users/{user_id}/secret", org=org)
        return secret["clientId"], secret["clientSecret"]

    def ensure_instance_member(self, user_id: str, roles: list[str]) -> None:
        self.call("POST", "/admin/v1/members", ok=(200, 409), json={"userId": user_id, "roles": roles})

    def token_works(self, token: str) -> bool:
        response = self.http.get("/auth/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        return response.status_code == 200

    def replace_personal_access_token(self, org: str, user_id: str, lifetime: timedelta) -> str:
        """A new token for the service account; its earlier tokens are deleted."""
        existing = self.call("POST", f"/management/v1/users/{user_id}/pats/_search", org=org, json={})
        for pat in existing.get("result", []):
            self.call("DELETE", f"/management/v1/users/{user_id}/pats/{pat['id']}", org=org)
        expires = (datetime.now(UTC) + lifetime).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.call("POST", f"/management/v1/users/{user_id}/pats", org=org,
                         json={"expirationDate": expires})["token"]

    def ensure_user_grant(self, org: str, user_id: str, project_id: str, roles: list[str],
                          project_grant_id: str | None = None) -> None:
        found = self.call("POST", "/management/v1/users/grants/_search", org=org, json={"queries": [
            {"userIdQuery": {"userId": user_id}}, {"projectIdQuery": {"projectId": project_id}}]})
        if found.get("result"):
            return
        body = {"projectId": project_id, "roleKeys": roles}
        if project_grant_id:
            body["projectGrantId"] = project_grant_id
        self.call("POST", f"/management/v1/users/{user_id}/grants", org=org, json=body)
        log.info("granted %s to user %s", roles, user_id)


def write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    temporary.touch(mode=0o600)
    temporary.write_text(content)
    temporary.replace(path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    url = os.environ["MM_ZITADEL_URL"]
    issuer = os.environ["MM_ZITADEL_ISSUER"]
    token = Path(os.environ["MM_ZITADEL_ADMIN_PAT_FILE"]).read_text().strip()
    config_file = Path(os.environ["MM_ZITADEL_CONFIG_FILE"])
    api_token_file = Path(os.environ["MM_ZITADEL_API_TOKEN_FILE"])

    if set(ROLE_NAMES) != set(ROLES):
        raise SystemExit("ROLE_NAMES and app.auth.ROLES disagree")

    zitadel = Zitadel(url, issuer, token)
    default_org = zitadel.default_org_id()
    project_id = zitadel.ensure_project(default_org, PROJECT_NAME)
    zitadel.ensure_roles(default_org, project_id, ROLE_NAMES)
    admin_id = zitadel.find_user(default_org, FIRST_ADMIN_USERNAME_PREFIX, "TEXT_QUERY_METHOD_STARTS_WITH")
    if admin_id:
        zitadel.ensure_user_grant(default_org, admin_id, project_id, ["system_admin"])
    else:
        log.warning("first admin %r... not found; no system admin granted", FIRST_ADMIN_USERNAME_PREFIX)

    api_user = zitadel.find_user(default_org, API_SERVICE_ACCOUNT) or zitadel.create_machine_user(
        default_org, API_SERVICE_ACCOUNT, "MedMusketeer API")
    zitadel.ensure_instance_member(api_user, [API_INSTANCE_ROLE])
    if not (api_token_file.is_file() and zitadel.token_works(api_token_file.read_text().strip())):
        api_token = zitadel.replace_personal_access_token(default_org, api_user, API_TOKEN_LIFETIME)
        write_private(api_token_file, api_token)
        log.info("wrote a new token for %s to %s", API_SERVICE_ACCOUNT, api_token_file)

    config = {"issuer": issuer, "project_id": project_id, "default_org_id": default_org}
    config_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_file.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2))
    temporary.replace(config_file)
    log.info("wrote %s: %s", config_file, config)
    if admin_id:
        log.info("register the system admin with: python -m app.manage register-user --zitadel-sub %s --role system_admin",
                 admin_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
