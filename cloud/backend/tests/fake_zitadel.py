"""Test helper: an in-memory stand-in for app.zitadel.ZitadelAdmin.

Used by the database tests so they need no ZITADEL container; the real client is exercised end to
end by the stack tests (TC-C13). `fail` makes the next call of the named method raise, to test that
a ZITADEL failure leaves no database rows behind.
"""
import itertools

from app.zitadel import NewUser, ZitadelAdmin, ZitadelError


class FakeZitadelAdmin:
    def __init__(self):
        self._ids = itertools.count(1)
        self.organisations: dict[str, str] = {}  # zitadel org id -> name
        self.users: dict[str, dict] = {}  # zitadel user id -> {org, role, email, state}
        self.failures: dict[str, ZitadelError] = {}

    def fail(self, method: str, status: int = 500, message: str = "injected failure") -> None:
        self.failures[method] = ZitadelError(status, message)

    def _maybe_fail(self, method: str) -> None:
        if method in self.failures:
            raise self.failures.pop(method)

    undo = ZitadelAdmin.undo

    async def create_organisation(self, name: str) -> str:
        self._maybe_fail("create_organisation")
        if name in self.organisations.values():
            raise ZitadelError(409, "Organisation already exists")
        org_id = f"z-org-{next(self._ids)}"
        self.organisations[org_id] = name
        return org_id

    async def delete_organisation(self, org_id: str) -> None:
        self._maybe_fail("delete_organisation")
        self.organisations.pop(org_id)

    async def create_user(self, org_id: str, role: str, email: str, given_name: str, family_name: str) -> NewUser:
        self._maybe_fail("create_user")
        if any(user.get("email") == email for user in self.users.values()):
            raise ZitadelError(409, "User already exists")
        user_id = f"z-user-{next(self._ids)}"
        self.users[user_id] = {"org": org_id, "role": role, "email": email, "state": "active"}
        return NewUser(user_id=user_id, invite_code=f"INVITE-{user_id}")

    async def deactivate_user(self, user_id: str) -> None:
        self._maybe_fail("deactivate_user")
        # Users arranged directly in the database are taken to exist in ZITADEL too.
        self.users.setdefault(user_id, {})["state"] = "inactive"

    async def delete_user(self, user_id: str) -> None:
        self._maybe_fail("delete_user")
        self.users.pop(user_id)
