"""The API's ZITADEL management client (D2, D3, D12).

The API is the only path that creates organisations and accounts: it changes ZITADEL and the
database together. It calls ZITADEL as the service account `mm-api`, which the zitadel-bootstrap
job creates with the instance role IAM_ORG_MANAGER (organisations, their users and user grants,
project grants; nothing instance-wide). Its token is in a file that only the bootstrap job and the
API mount.

Accounts get no password from the API: ZITADEL returns an invite code, which the organisation
admin hands to the person, who then sets their own password or passkey in ZITADEL's login.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.tokens import ZitadelConfig

log = logging.getLogger(__name__)

ORG_ROLES = ("org_admin", "doctor", "patient")  # granted to every client organisation (D3)


class ZitadelError(Exception):
    """ZITADEL refused or failed a call. status is ZITADEL's HTTP status (0: not reachable)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"ZITADEL HTTP {status}: {message}")
        self.status = status
        self.message = message


@dataclass(frozen=True)
class NewUser:
    user_id: str  # ZITADEL user id, the token's sub
    invite_code: str


class ZitadelAdmin:
    def __init__(self, config: ZitadelConfig, zitadel_url: str, http: httpx.AsyncClient, token_file: Path):
        self.config = config
        self._url = zitadel_url.rstrip("/")
        # ZITADEL picks the instance by Host, so internal calls carry the public host name.
        self._host = urlsplit(config.issuer).netloc
        self._http = http
        self._token_file = token_file
        self._token = token_file.read_text().strip()

    async def _call(self, method: str, path: str, org: str | None = None, **kwargs) -> dict:
        response = await self._send(method, path, org, **kwargs)
        if response.status_code == 401:
            # The bootstrap job replaces the token when it expires or stops working: reload once.
            token = self._token_file.read_text().strip()
            if token != self._token:
                self._token = token
                response = await self._send(method, path, org, **kwargs)
        if response.status_code >= 300:
            try:
                message = str(response.json().get("message", ""))[:300]
            except ValueError:
                message = response.text[:300]
            raise ZitadelError(response.status_code, message)
        return response.json() if response.content else {}

    async def _send(self, method: str, path: str, org: str | None, **kwargs) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token}", "Host": self._host}
        if org:
            headers["x-zitadel-orgid"] = org
        try:
            return await self._http.request(method, self._url + path, headers=headers, **kwargs)
        except httpx.HTTPError as error:
            raise ZitadelError(0, type(error).__name__) from error

    async def undo(self, action, *args) -> None:
        """Best-effort compensation after a later step failed; the original error is what matters.
        Anything left behind is inert: the API refuses ZITADEL users it has not registered."""
        try:
            await action(*args)
        except ZitadelError as error:
            log.warning("could not undo %s%s in ZITADEL: %s", action.__name__, args, error)

    # --- organisations -------------------------------------------------------------------------

    async def create_organisation(self, name: str) -> str:
        """A ZITADEL organisation with the MedMusketeer project granted to it (roles ORG_ROLES)."""
        org_id = (await self._call("POST", "/v2/organizations", json={"name": name}))["organizationId"]
        try:
            await self._call("POST", f"/management/v1/projects/{self.config.project_id}/grants",
                             org=self.config.default_org_id,
                             json={"grantedOrgId": org_id, "roleKeys": list(ORG_ROLES)})
        except ZitadelError:
            await self.undo(self.delete_organisation, org_id)
            raise
        return org_id

    async def delete_organisation(self, org_id: str) -> None:
        await self._call("DELETE", f"/v2/organizations/{org_id}")

    async def _project_grant_id(self, org_id: str) -> str:
        found = await self._call("POST", "/management/v1/granted_projects/_search", org=org_id, json={})
        for grant in found.get("result", []):
            if grant.get("projectId") == self.config.project_id:
                return grant["grantId"]
        raise ZitadelError(404, f"the MedMusketeer project is not granted to organisation {org_id}")

    # --- users ---------------------------------------------------------------------------------

    async def create_user(self, org_id: str, role: str, email: str, given_name: str, family_name: str) -> NewUser:
        """A human user in the organisation, with the role granted and an invite code returned."""
        if role not in ORG_ROLES:
            raise ValueError(f"not an organisation role: {role}")
        grant_id = await self._project_grant_id(org_id)
        user_id = (await self._call("POST", "/v2/users/human", json={
            "organization": {"orgId": org_id},
            "username": email,
            "profile": {"givenName": given_name, "familyName": family_name},
            # returnCode: ZITADEL sends no e-mail; the invite below verifies the address.
            "email": {"email": email, "returnCode": {}},
        }))["userId"]
        try:
            await self._call("POST", f"/management/v1/users/{user_id}/grants", org=org_id, json={
                "projectId": self.config.project_id, "projectGrantId": grant_id, "roleKeys": [role]})
            code = (await self._call("POST", f"/v2/users/{user_id}/invite_code", json={"returnCode": {}}))["inviteCode"]
        except ZitadelError:
            await self.undo(self.delete_user, user_id)
            raise
        return NewUser(user_id=user_id, invite_code=code)

    async def deactivate_user(self, user_id: str) -> None:
        """Idempotent: a user who is already inactive (an earlier attempt whose answer was lost, or a
        change in the console) counts as done, so a retried disable can complete."""
        try:
            await self._call("POST", f"/v2/users/{user_id}/deactivate", json={})
        except ZitadelError as error:
            # ZITADEL v4 answers 400 FAILED_PRECONDITION "User already inactive"; check the state
            # rather than the message text.
            if error.status != 400:
                raise
            user = await self._call("GET", f"/v2/users/{user_id}")
            if user.get("user", {}).get("state") != "USER_STATE_INACTIVE":
                raise

    async def delete_user(self, user_id: str) -> None:
        await self._call("DELETE", f"/v2/users/{user_id}")
