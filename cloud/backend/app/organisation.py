"""Organisation API: the organisation admin manages patients, wearables and doctor assignments (D9).

Everything here is limited to the caller's own organisation. A patient outside the caller's
reach (another organisation, or for a doctor a patient who is not theirs) answers 404, the same as
a patient that does not exist, so ids cannot be probed. The organisation admin never reads ECG
data, classifications or alerts (app.care); a patient export leaves ECG out until D9's open
question is decided. Every change is written to the audit log with the acting user.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth import OrgAdmin, OrgAdminOrDoctor, OrgMember, Principal
from app.db import Conn, audit, many, not_found, one

router = APIRouter(tags=["organisation"])


# --- models ------------------------------------------------------------------------------------

class OwnOrganisation(BaseModel):
    org_id: UUID
    name: str
    kind: str
    status: str
    created_at: datetime


class OrgDevice(BaseModel):
    device_id: UUID
    type: str
    status: str
    current_mode: str
    current_gateway_id: UUID | None
    last_seen: datetime | None
    patient_id: UUID | None  # the patient the wearable is issued to


class PatientSummary(BaseModel):
    patient_id: UUID
    pseudonym: str
    user_id: UUID | None
    account_status: str | None
    doctor_id: UUID | None
    wearable_id: UUID | None
    created_at: datetime


class DoctorIn(BaseModel):
    doctor_id: UUID


class CareAssignment(BaseModel):
    assignment_id: UUID
    patient_id: UUID
    doctor_id: UUID
    assigned_by: UUID
    valid_from: datetime
    valid_to: datetime | None


class WearableIn(BaseModel):
    device_id: UUID


class WearableAssignment(BaseModel):
    device_id: UUID
    patient_id: UUID
    issued_by: UUID
    assigned_at: datetime
    unassigned_at: datetime | None


class DisorderIn(BaseModel):
    disorder: str = Field(min_length=1, max_length=200)


class Disorder(BaseModel):
    patient_id: UUID
    disorder: str
    recorded_by: UUID
    recorded_at: datetime


class ExportIn(BaseModel):
    destination: str = Field(min_length=1, max_length=500)


class PatientExport(BaseModel):
    export_id: UUID
    exported_by: UUID
    destination: str
    created_at: datetime
    patient: dict
    disorders: list[Disorder]
    care_assignments: list[CareAssignment]
    wearable_assignments: list[WearableAssignment]
    ecg_included: bool  # false until D9's open question on ECG in exports is decided


class AuditEvent(BaseModel):
    event_id: UUID
    at: datetime
    actor_id: UUID
    scope: str
    org_id: UUID | None
    action: str
    target_id: UUID | None
    details: dict


# --- helpers -----------------------------------------------------------------------------------

async def patient_in_scope(conn: AsyncConnection, principal: Principal, patient_id: UUID, *,
                           lock: bool = False) -> dict:
    """The patient, if the caller may see them: an org admin any patient of their organisation, a
    doctor their current patients, a patient themselves. Otherwise 404."""
    if principal.role == "org_admin":
        condition = "TRUE"
    elif principal.role == "doctor":
        condition = """EXISTS (SELECT 1 FROM care_assignments c WHERE c.patient_id = p.patient_id
                       AND c.doctor_id = :user AND c.valid_to IS NULL)"""
    elif principal.role == "patient":
        condition = "p.user_id = :user"
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed for this role")
    patient = await one(conn, f"""
        SELECT p.*, u.status AS account_status FROM patients p LEFT JOIN users u ON u.user_id = p.user_id
        WHERE p.patient_id = :patient AND p.org_id = :org AND {condition}
        {"FOR UPDATE OF p" if lock else ""}
    """, patient=patient_id, org=principal.org_id, user=principal.user_id)
    if patient is None:
        raise not_found("patient")
    return patient


async def require_active_account(conn: AsyncConnection, patient: dict) -> None:
    """Locks the patient's users row (FOR SHARE) until the transaction ends, so a concurrent disable
    (FOR UPDATE on that row) either runs first and is seen here, or waits and then undoes this
    request's assignment."""
    if patient["user_id"] is None:
        return
    account = await one(conn, "SELECT status FROM users WHERE user_id = :u FOR SHARE", u=patient["user_id"])
    if account["status"] != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "the patient's account is disabled")


async def end_wearable_assignment(conn: AsyncConnection, patient_id: UUID) -> dict | None:
    """End the patient's open wearable assignment and its monitoring session; data the wearable
    sends afterwards is not attributed to this patient."""
    ended = await one(conn, """
        UPDATE device_assignments SET unassigned_at = now()
        WHERE patient_id = :p AND unassigned_at IS NULL RETURNING *
    """, p=patient_id)
    if ended:
        await conn.execute(text("""
            UPDATE monitoring_sessions SET ended_at = now()
            WHERE device_id = :d AND patient_id = :p AND ended_at IS NULL
        """), {"d": ended["device_id"], "p": patient_id})
    return ended


# --- own organisation, devices, audit ----------------------------------------------------------

@router.get("/organisation", response_model=OwnOrganisation)
async def own_organisation(principal: OrgMember, conn: Conn):
    return await one(conn, "SELECT * FROM organisations WHERE org_id = :o", o=principal.org_id)


@router.get("/devices", response_model=list[OrgDevice])
async def organisation_devices(principal: OrgAdminOrDoctor, conn: Conn):
    """Org admin: every device granted to the organisation. Doctor: the wearables of their patients."""
    if principal.role == "org_admin":
        scope = "JOIN device_grants g ON g.device_id = d.device_id AND g.revoked_at IS NULL AND g.org_id = :org"
        where = "TRUE"
    else:
        scope = "JOIN patients p ON p.patient_id = a.patient_id AND p.org_id = :org"
        where = """a.patient_id IN (SELECT c.patient_id FROM care_assignments c
                                    WHERE c.doctor_id = :user AND c.valid_to IS NULL)"""
    return await many(conn, f"""
        SELECT d.device_id, d.type, d.status, d.current_mode, d.current_gateway_id, d.last_seen, a.patient_id
        FROM devices d
        LEFT JOIN device_assignments a ON a.device_id = d.device_id AND a.unassigned_at IS NULL
        {scope}
        WHERE {where}
        ORDER BY d.type, d.device_id
    """, org=principal.org_id, user=principal.user_id)


@router.get("/audit", response_model=list[AuditEvent])
async def organisation_audit(admin: OrgAdmin, conn: Conn, limit: int = Query(200, ge=1, le=1000)):
    return await many(conn, "SELECT * FROM audit_log WHERE org_id = :o ORDER BY at DESC, event_id LIMIT :n",
                      o=admin.org_id, n=limit)


# --- patients ----------------------------------------------------------------------------------

@router.get("/patients", response_model=list[PatientSummary])
async def list_patients(principal: OrgAdminOrDoctor, conn: Conn):
    """Org admin: every patient of the organisation. Doctor: their current patients."""
    return await many(conn, f"""
        SELECT p.patient_id, p.pseudonym, p.user_id, u.status AS account_status, p.created_at,
               c.doctor_id, a.device_id AS wearable_id
        FROM patients p
        LEFT JOIN users u ON u.user_id = p.user_id
        LEFT JOIN care_assignments c ON c.patient_id = p.patient_id AND c.valid_to IS NULL
        LEFT JOIN device_assignments a ON a.patient_id = p.patient_id AND a.unassigned_at IS NULL
        WHERE p.org_id = :org {"AND c.doctor_id = :user" if principal.role == "doctor" else ""}
        ORDER BY p.pseudonym
    """, org=principal.org_id, user=principal.user_id)


@router.put("/patients/{patient_id}/doctor", response_model=CareAssignment)
async def assign_doctor(patient_id: UUID, body: DoctorIn, admin: OrgAdmin, conn: Conn):
    """Make the doctor the patient's one active doctor, ending the previous assignment."""
    patient = await patient_in_scope(conn, admin, patient_id, lock=True)
    await require_active_account(conn, patient)
    # FOR SHARE: a concurrent disable of the doctor either commits first (no row here) or waits and
    # then ends this assignment too.
    doctor = await one(conn, """
        SELECT 1 FROM users WHERE user_id = :d AND org_id = :o AND role = 'doctor' AND status = 'active'
        FOR SHARE
    """, d=body.doctor_id, o=admin.org_id)
    if doctor is None:
        raise not_found("doctor")
    current = await one(conn, "SELECT * FROM care_assignments WHERE patient_id = :p AND valid_to IS NULL",
                        p=patient_id)
    if current and current["doctor_id"] == body.doctor_id:
        return current
    if current:
        await conn.execute(text("UPDATE care_assignments SET valid_to = now() WHERE assignment_id = :a"),
                           {"a": current["assignment_id"]})
    assignment = await one(conn, """
        INSERT INTO care_assignments (patient_id, doctor_id, assigned_by) VALUES (:p, :d, :by) RETURNING *
    """, p=patient_id, d=body.doctor_id, by=admin.user_id)
    await audit(conn, admin.user_id, "organisation", "doctor.assigned", org_id=admin.org_id, target_id=patient_id,
                doctor_id=body.doctor_id, previous_doctor_id=current["doctor_id"] if current else None)
    return assignment


@router.post("/patients/{patient_id}/wearable", status_code=status.HTTP_201_CREATED, response_model=WearableAssignment)
async def issue_wearable(patient_id: UUID, body: WearableIn, admin: OrgAdmin, conn: Conn):
    """Issue an active wearable granted to the organisation. From now on its data is the patient's."""
    patient = await patient_in_scope(conn, admin, patient_id, lock=True)
    await require_active_account(conn, patient)
    # The grant row is locked too: a concurrent grant revoke either commits first (no row here) or
    # waits, and then ends the assignment made here.
    device = await one(conn, """
        SELECT d.type, d.status FROM devices d
        JOIN device_grants g ON g.device_id = d.device_id AND g.revoked_at IS NULL AND g.org_id = :o
        WHERE d.device_id = :d FOR SHARE OF d, g
    """, d=body.device_id, o=admin.org_id)
    if device is None:
        raise not_found("device")
    if device["type"] != "wearable":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "only a wearable can be issued to a patient")
    if device["status"] != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, f"the wearable is {device['status']}")
    # The partial unique indexes refuse a second open assignment for the device or the patient (409).
    assignment = await one(conn, """
        INSERT INTO device_assignments (device_id, patient_id, issued_by) VALUES (:d, :p, :by) RETURNING *
    """, d=body.device_id, p=patient_id, by=admin.user_id)
    await audit(conn, admin.user_id, "organisation", "wearable.issued", org_id=admin.org_id, target_id=patient_id,
                device_id=body.device_id)
    return assignment


@router.delete("/patients/{patient_id}/wearable", response_model=WearableAssignment)
async def return_wearable(patient_id: UUID, admin: OrgAdmin, conn: Conn):
    await patient_in_scope(conn, admin, patient_id, lock=True)
    ended = await end_wearable_assignment(conn, patient_id)
    if ended is None:
        raise not_found("wearable assignment")
    await audit(conn, admin.user_id, "organisation", "wearable.returned", org_id=admin.org_id, target_id=patient_id,
                device_id=ended["device_id"])
    return ended


@router.get("/patients/{patient_id}/disorders", response_model=list[Disorder])
async def list_disorders(patient_id: UUID, principal: OrgAdminOrDoctor, conn: Conn):
    await patient_in_scope(conn, principal, patient_id)
    return await many(conn, "SELECT * FROM patient_disorders WHERE patient_id = :p ORDER BY recorded_at, disorder",
                      p=patient_id)


@router.post("/patients/{patient_id}/disorders", status_code=status.HTTP_201_CREATED, response_model=Disorder)
async def record_disorder(patient_id: UUID, body: DisorderIn, admin: OrgAdmin, conn: Conn):
    await patient_in_scope(conn, admin, patient_id)
    disorder = await one(conn, """
        INSERT INTO patient_disorders (patient_id, disorder, recorded_by) VALUES (:p, :d, :by) RETURNING *
    """, p=patient_id, d=body.disorder, by=admin.user_id)
    await audit(conn, admin.user_id, "organisation", "disorder.recorded", org_id=admin.org_id, target_id=patient_id,
                disorder=body.disorder)
    return disorder


@router.post("/patients/{patient_id}/exports", status_code=status.HTTP_201_CREATED, response_model=PatientExport)
async def export_patient(patient_id: UUID, body: ExportIn, admin: OrgAdmin, conn: Conn):
    """The patient's record (pseudonym, disorders, care and wearable history), logged as an export."""
    patient = await patient_in_scope(conn, admin, patient_id)
    export = await one(conn, """
        INSERT INTO patient_exports (patient_id, exported_by, destination) VALUES (:p, :by, :dest) RETURNING *
    """, p=patient_id, by=admin.user_id, dest=body.destination)
    await audit(conn, admin.user_id, "organisation", "patient.exported", org_id=admin.org_id, target_id=patient_id,
                export_id=export["export_id"], destination=body.destination)
    return {
        **export,
        "patient": {"patient_id": patient["patient_id"], "pseudonym": patient["pseudonym"],
                    "created_at": patient["created_at"]},
        "disorders": await many(conn, "SELECT * FROM patient_disorders WHERE patient_id = :p ORDER BY recorded_at",
                                p=patient_id),
        "care_assignments": await many(conn, "SELECT * FROM care_assignments WHERE patient_id = :p ORDER BY valid_from",
                                       p=patient_id),
        "wearable_assignments": await many(conn, """
            SELECT * FROM device_assignments WHERE patient_id = :p ORDER BY assigned_at""", p=patient_id),
        "ecg_included": False,
    }
