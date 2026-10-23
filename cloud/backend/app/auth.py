"""Who is calling, and what they may do (D2, D3, D9).

get_principal accepts a request only when:
- it carries a valid ZITADEL access token (app.tokens),
- the token grants exactly one MedMusketeer role, granted by the user's own ZITADEL organisation,
- the user is registered in `users` with that same role (the mirror is changed only by the API)
  and has not been disabled,
- and, for organisation users, the user's organisation is the one in the token and is active.
The system admin's token must come from the ZITADEL instance's default organisation.
"""
import logging
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text

from app.tokens import InvalidToken
from app.zitadel import ZitadelAdmin

log = logging.getLogger(__name__)

ROLES = ("system_admin", "org_admin", "doctor", "patient")


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    role: str
    org_id: UUID | None
    patient_id: UUID | None = None  # set for a patient with a patient record


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def _forbidden(reason: str) -> HTTPException:
    log.info("request refused: %s", reason)
    return HTTPException(status.HTTP_403_FORBIDDEN, "not allowed")


async def get_principal(request: Request) -> Principal:
    verifier = getattr(request.app.state, "verifier", None)
    if verifier is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "authentication is not configured")

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("a bearer token is required")
    try:
        claims = await verifier.verify(token)
    except InvalidToken as error:
        log.info("token rejected: %s", error)
        raise _unauthorized("invalid token") from error

    roles = {role: orgs for role, orgs in claims.roles.items() if role in ROLES}
    if len(roles) != 1:
        raise _forbidden(f"token grants {len(roles)} MedMusketeer roles")
    (role, granting_orgs), = roles.items()
    if claims.zitadel_org_id not in granting_orgs:
        raise _forbidden("role not granted by the user's own organisation")

    async with request.app.state.engine.connect() as conn:
        row = (await conn.execute(text("""
            SELECT u.user_id, u.role, u.org_id, u.status, o.zitadel_org_id, o.status AS org_status,
                   p.patient_id
            FROM users u
            LEFT JOIN organisations o ON o.org_id = u.org_id
            LEFT JOIN patients p ON p.user_id = u.user_id
            WHERE u.zitadel_sub = :sub
        """), {"sub": claims.subject})).mappings().first()

    if row is None:
        raise _forbidden("user not registered")
    if row["role"] != role:
        raise _forbidden("role in token differs from the registered role")
    if row["status"] != "active":
        raise _forbidden("user disabled")
    if role == "system_admin":
        if claims.zitadel_org_id != verifier.config.default_org_id:
            raise _forbidden("system admin token from another organisation")
    else:
        if row["zitadel_org_id"] != claims.zitadel_org_id:
            raise _forbidden("organisation in token differs from the registered organisation")
        if row["org_status"] != "active":
            raise _forbidden("organisation suspended")
    return Principal(user_id=row["user_id"], role=row["role"], org_id=row["org_id"], patient_id=row["patient_id"])


def require_role(*roles: str):
    unknown = set(roles) - set(ROLES)
    if unknown:
        raise ValueError(f"unknown roles: {sorted(unknown)}")

    async def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed for this role")
        return principal

    return dependency


SystemAdmin = Annotated[Principal, Depends(require_role("system_admin"))]
OrgAdmin = Annotated[Principal, Depends(require_role("org_admin"))]
Doctor = Annotated[Principal, Depends(require_role("doctor"))]
OrgMember = Annotated[Principal, Depends(require_role("org_admin", "doctor", "patient"))]
OrgAdminOrDoctor = Annotated[Principal, Depends(require_role("org_admin", "doctor"))]
CareReader = Annotated[Principal, Depends(require_role("doctor", "patient"))]  # ECG and alerts (D9)


def get_zitadel(request: Request) -> ZitadelAdmin:
    zitadel = getattr(request.app.state, "zitadel", None)
    if zitadel is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "account management is not configured")
    return zitadel


Zitadel = Annotated[ZitadelAdmin, Depends(get_zitadel)]
