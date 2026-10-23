"""Who is calling, and what they may do.

Until Slice 3 adds ZITADEL token validation, get_principal refuses every request, so no
endpoint that depends on it is reachable. Tests replace it with app.dependency_overrides.
"""
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

ROLES = ("system_admin", "org_admin", "doctor", "patient")


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    role: str
    org_id: UUID | None


async def get_principal() -> Principal:
    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "authentication is not configured",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
