"""The directory: names of the people a caller works with (D14).

Names and e-mail addresses live only in ZITADEL (D12), so the API reads them there, as mm-api, for
the accounts the caller may see:
- organisation admin: every account of the organisation, with e-mail;
- doctor: themselves and their current patients;
- patient: themselves and their current doctor.
E-mail is returned to the organisation admin only, who manages the accounts. The system admin
has no directory: they see no patient or doctor data (D9).
"""
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.accounts import idp_error
from app.auth import OrgMember, Zitadel
from app.db import Conn, many
from app.zitadel import ZitadelError

router = APIRouter(tags=["organisation"])


class Person(BaseModel):
    user_id: UUID
    role: str
    status: str
    given_name: str | None  # None: ZITADEL returned no profile for the account
    family_name: str | None
    email: str | None  # organisation admin only


VISIBLE = {
    "org_admin": "TRUE",
    "doctor": """u.user_id = :user OR u.user_id IN (
                     SELECT p.user_id FROM patients p JOIN care_assignments c ON c.patient_id = p.patient_id
                     WHERE c.doctor_id = :user AND c.valid_to IS NULL)""",
    "patient": """u.user_id = :user OR u.user_id IN (
                      SELECT c.doctor_id FROM care_assignments c
                      WHERE c.patient_id = :patient AND c.valid_to IS NULL)""",
}


@router.get("/directory", response_model=list[Person])
async def directory(principal: OrgMember, conn: Conn, zitadel: Zitadel):
    accounts = await many(conn, f"""
        SELECT u.user_id, u.zitadel_sub, u.role, u.status FROM users u
        WHERE u.org_id = :org AND ({VISIBLE[principal.role]})
        ORDER BY u.role, u.created_at, u.user_id
    """, org=principal.org_id, user=principal.user_id, patient=principal.patient_id)
    try:
        profiles = await zitadel.profiles([account["zitadel_sub"] for account in accounts])
    except ZitadelError as error:
        raise idp_error(error) from error
    people = []
    for account in accounts:
        profile = profiles.get(account["zitadel_sub"])
        people.append({
            "user_id": account["user_id"], "role": account["role"], "status": account["status"],
            "given_name": profile.given_name if profile else None,
            "family_name": profile.family_name if profile else None,
            "email": profile.email if profile and principal.role == "org_admin" else None,
        })
    return people
