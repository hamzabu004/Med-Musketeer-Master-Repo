"""Accounts: the organisation admin creates and disables doctor and patient accounts (D2, D9, D12).

An account exists in two places, created together by the API:
- ZITADEL: a human user in the organisation's ZITADEL organisation, with the role granted. Names
  and e-mail live only there.
- the database: the `users` row (the mirror app.auth checks) and, for a patient, the `patients`
  row with the pseudonym that ECG data is filed under.

ZITADEL is changed first, because `users.zitadel_sub` needs its id. If the database then refuses
the row, the ZITADEL user is deleted again; anything left behind cannot sign in to the API, which
refuses ZITADEL users that are not registered.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth import OrgAdmin, Principal, Zitadel
from app.db import Conn, audit, many, not_found, one
from app.organisation import end_wearable_assignment
from app.zitadel import ZitadelAdmin, ZitadelError

router = APIRouter(tags=["organisation admin"])


# --- models ------------------------------------------------------------------------------------

class PersonIn(BaseModel):
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # also the ZITADEL username
    given_name: str = Field(min_length=1, max_length=200)
    family_name: str = Field(min_length=1, max_length=200)


class AccountIn(PersonIn):
    role: Literal["doctor", "patient"]
    pseudonym: str | None = Field(default=None, min_length=1, max_length=64)  # patients only

    @model_validator(mode="after")
    def pseudonym_for_patients_only(self):
        if (self.role == "patient") != (self.pseudonym is not None):
            raise ValueError("a pseudonym is required for a patient and not allowed otherwise")
        return self


class Account(BaseModel):
    user_id: UUID
    zitadel_sub: str
    role: str
    status: str
    org_id: UUID
    patient_id: UUID | None
    pseudonym: str | None
    created_at: datetime


class NewAccount(Account):
    invite_code: str  # shown once; the person uses it in ZITADEL's login to set their credentials


ACCOUNT_SQL = """
    SELECT u.user_id, u.zitadel_sub, u.role, u.status, u.org_id, u.created_at, p.patient_id, p.pseudonym
    FROM users u LEFT JOIN patients p ON p.user_id = u.user_id
"""


# --- helpers -----------------------------------------------------------------------------------

def idp_error(error: ZitadelError) -> HTTPException:
    if error.status == 409:
        return HTTPException(status.HTTP_409_CONFLICT, f"identity provider: {error.message}")
    if error.status == 400:
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"identity provider: {error.message}")
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "identity provider error")


async def create_account(conn: AsyncConnection, zitadel: ZitadelAdmin, actor: Principal, org_id: UUID,
                         role: str, person: PersonIn, pseudonym: str | None = None) -> dict:
    """Create the ZITADEL user and the database rows; the caller has checked the actor's rights."""
    org = await one(conn, "SELECT zitadel_org_id, status FROM organisations WHERE org_id = :o FOR SHARE", o=org_id)
    if org is None:
        raise not_found("organisation")
    if org["status"] != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "the organisation is suspended")
    if org["zitadel_org_id"] is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the organisation has no ZITADEL organisation")
    if pseudonym is not None and await one(
            conn, "SELECT 1 FROM patients WHERE org_id = :o AND pseudonym = :p", o=org_id, p=pseudonym):
        raise HTTPException(status.HTTP_409_CONFLICT, "pseudonym already used in this organisation")

    try:
        new_user = await zitadel.create_user(org["zitadel_org_id"], role, person.email,
                                             person.given_name, person.family_name)
    except ZitadelError as error:
        raise idp_error(error) from error

    try:
        user_id = await conn.scalar(text(
            "INSERT INTO users (zitadel_sub, role, org_id) VALUES (:sub, :role, :org) RETURNING user_id"
        ), {"sub": new_user.user_id, "role": role, "org": org_id})
        if pseudonym is not None:
            await conn.execute(text("INSERT INTO patients (user_id, org_id, pseudonym) VALUES (:u, :o, :p)"),
                               {"u": user_id, "o": org_id, "p": pseudonym})
    except IntegrityError:
        await zitadel.undo(zitadel.delete_user, new_user.user_id)
        raise
    scope = "registry" if actor.role == "system_admin" else "organisation"
    await audit(conn, actor.user_id, scope, "account.created", org_id=org_id, target_id=user_id, role=role)
    account = await one(conn, ACCOUNT_SQL + " WHERE u.user_id = :u", u=user_id)
    return {**account, "invite_code": new_user.invite_code}


# --- endpoints ---------------------------------------------------------------------------------

@router.post("/accounts", status_code=status.HTTP_201_CREATED, response_model=NewAccount)
async def create_doctor_or_patient(body: AccountIn, admin: OrgAdmin, conn: Conn, zitadel: Zitadel):
    return await create_account(conn, zitadel, admin, admin.org_id, body.role, body, body.pseudonym)


@router.get("/accounts", response_model=list[Account])
async def list_accounts(admin: OrgAdmin, conn: Conn):
    return await many(conn, ACCOUNT_SQL + " WHERE u.org_id = :o ORDER BY u.created_at, u.user_id", o=admin.org_id)


@router.post("/accounts/{user_id}/disable", response_model=Account)
async def disable_account(user_id: UUID, admin: OrgAdmin, conn: Conn, zitadel: Zitadel):
    """The user's tokens are refused at once. A doctor's patients lose their doctor (the admin
    assigns a new one); a patient's wearable is returned, ending the monitoring session."""
    account = await one(conn, ACCOUNT_SQL + " WHERE u.user_id = :u AND u.org_id = :o FOR UPDATE OF u",
                        u=user_id, o=admin.org_id)
    if account is None or account["role"] not in ("doctor", "patient"):
        raise not_found("account")
    if account["status"] == "disabled":
        raise HTTPException(status.HTTP_409_CONFLICT, "account already disabled")

    await conn.execute(text("UPDATE users SET status = 'disabled' WHERE user_id = :u"), {"u": user_id})
    if account["role"] == "doctor":
        await conn.execute(text("UPDATE care_assignments SET valid_to = now() WHERE doctor_id = :u AND valid_to IS NULL"),
                           {"u": user_id})
    else:
        await end_wearable_assignment(conn, account["patient_id"])
    await audit(conn, admin.user_id, "organisation", "account.disabled", org_id=admin.org_id, target_id=user_id)
    try:
        # Last, so a ZITADEL failure rolls back the database change and the request can be retried.
        await zitadel.deactivate_user(account["zitadel_sub"])
    except ZitadelError as error:
        if error.status != 404:  # a user already deleted in ZITADEL cannot sign in either
            raise idp_error(error) from error
    return {**account, "status": "disabled"}
