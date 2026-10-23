"""System-admin registry API: organisations and their admins, devices, credentials, device grants,
the registry audit log and security events (D9). The system admin sees no patient or doctor data.

Creating an organisation also creates its ZITADEL organisation, with the MedMusketeer project
granted to it (D3); its first organisation admin is created here too (app.accounts).

Device status moves pending -> active <-> suspended, and any state -> revoked (final). A device
becomes active only with an active credential. Revoking a device revokes its credentials and
closes its grant; closing a grant ends the device's open assignment and monitoring session, so
data arriving afterwards cannot be attributed to the previous patient.
"""
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.accounts import NewAccount, PersonIn, create_account, idp_error
from app.auth import SystemAdmin, Zitadel
from app.db import Conn, audit, many, not_found, one
from app.organisation import AuditEvent
from app.zitadel import ZitadelError

router = APIRouter(prefix="/admin", tags=["system admin"])

DeviceStatus = Literal["pending", "active", "suspended", "revoked"]
TRANSITIONS: dict[str, set[str]] = {
    "activate": {"pending", "suspended"},
    "suspend": {"active"},
    "revoke": {"pending", "active", "suspended"},
}


# --- models ------------------------------------------------------------------------------------

class OrganisationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["public", "private"]


class OrganisationPatch(BaseModel):
    status: Literal["active", "suspended"]


class Organisation(BaseModel):
    org_id: UUID
    name: str
    kind: str
    status: str
    zitadel_org_id: str | None
    registered_by: UUID | None
    created_at: datetime


class DeviceIn(BaseModel):
    device_id: UUID  # the certificate CN issued by mmca
    type: Literal["wearable", "fixed_gateway"]
    is_testbed: bool  # required: attack tests are refused against production devices


class Device(BaseModel):
    device_id: UUID
    type: str
    status: DeviceStatus
    is_testbed: bool
    current_mode: str
    current_gateway_id: UUID | None
    last_seen: datetime | None
    registered_by: UUID | None
    created_at: datetime


class CredentialIn(BaseModel):
    auth_method: str = Field(min_length=1, max_length=64)
    key_type: str | None = Field(default=None, max_length=32)
    credential_ref: str = Field(min_length=1, max_length=256)  # serial or fingerprint, never key material
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Credential(BaseModel):
    credential_id: UUID
    device_id: UUID
    auth_method: str
    key_type: str | None
    credential_ref: str
    status: str
    created_at: datetime
    expires_at: datetime | None
    metadata: dict[str, Any]


class GrantIn(BaseModel):
    org_id: UUID


class Grant(BaseModel):
    grant_id: UUID
    device_id: UUID
    org_id: UUID
    granted_by: UUID
    granted_at: datetime
    revoked_by: UUID | None
    revoked_at: datetime | None


class SecurityEvent(BaseModel):
    event_id: UUID
    ts: datetime
    gateway_id: UUID
    device_id: UUID | None
    mode: str
    predicted_class: str
    outcome: str
    action: str | None
    action_result: str | None


# --- helpers -----------------------------------------------------------------------------------

async def close_grant(conn: AsyncConnection, grant_id: UUID, device_id: UUID, by: UUID) -> None:
    org_id = await conn.scalar(
        text("UPDATE device_grants SET revoked_at = now(), revoked_by = :by WHERE grant_id = :grant_id RETURNING org_id"),
        {"grant_id": grant_id, "by": by},
    )
    await audit(conn, by, "registry", "grant.revoked", org_id=org_id, target_id=device_id, grant_id=grant_id)
    await conn.execute(
        text("UPDATE device_assignments SET unassigned_at = now() WHERE device_id = :device_id AND unassigned_at IS NULL"),
        {"device_id": device_id},
    )
    await conn.execute(
        text("UPDATE monitoring_sessions SET ended_at = now() WHERE device_id = :device_id AND ended_at IS NULL"),
        {"device_id": device_id},
    )


# --- organisations -----------------------------------------------------------------------------

@router.post("/organisations", status_code=status.HTTP_201_CREATED, response_model=Organisation)
async def create_organisation(body: OrganisationIn, admin: SystemAdmin, conn: Conn, zitadel: Zitadel):
    try:
        zitadel_org_id = await zitadel.create_organisation(body.name)
    except ZitadelError as error:
        raise idp_error(error) from error
    try:
        organisation = await one(
            conn,
            """INSERT INTO organisations (name, kind, registered_by, zitadel_org_id)
               VALUES (:name, :kind, :by, :zitadel_org_id) RETURNING *""",
            name=body.name, kind=body.kind, by=admin.user_id, zitadel_org_id=zitadel_org_id,
        )
    except IntegrityError:
        await zitadel.undo(zitadel.delete_organisation, zitadel_org_id)
        raise
    await audit(conn, admin.user_id, "registry", "organisation.created", org_id=organisation["org_id"],
                target_id=organisation["org_id"], name=body.name)
    return organisation


@router.post("/organisations/{org_id}/admins", status_code=status.HTTP_201_CREATED, response_model=NewAccount)
async def create_organisation_admin(org_id: UUID, body: PersonIn, admin: SystemAdmin, conn: Conn, zitadel: Zitadel):
    """An organisation admin account, in ZITADEL and in `users`; the invite code is shown once."""
    return await create_account(conn, zitadel, admin, org_id, "org_admin", body)


@router.get("/organisations", response_model=list[Organisation])
async def list_organisations(admin: SystemAdmin, conn: Conn):
    return await many(conn, "SELECT * FROM organisations ORDER BY created_at, org_id")


@router.patch("/organisations/{org_id}", response_model=Organisation)
async def update_organisation(org_id: UUID, body: OrganisationPatch, admin: SystemAdmin, conn: Conn):
    row = await one(
        conn, "UPDATE organisations SET status = :status WHERE org_id = :org_id RETURNING *",
        status=body.status, org_id=org_id,
    )
    if row is None:
        raise not_found("organisation")
    await audit(conn, admin.user_id, "registry", f"organisation.{body.status}", org_id=org_id, target_id=org_id)
    return row


# --- devices -----------------------------------------------------------------------------------

@router.post("/devices", status_code=status.HTTP_201_CREATED, response_model=Device)
async def register_device(body: DeviceIn, admin: SystemAdmin, conn: Conn):
    device = await one(
        conn,
        """INSERT INTO devices (device_id, type, is_testbed, registered_by)
           VALUES (:device_id, :type, :is_testbed, :by) RETURNING *""",
        device_id=body.device_id, type=body.type, is_testbed=body.is_testbed, by=admin.user_id,
    )
    await audit(conn, admin.user_id, "registry", "device.registered", target_id=body.device_id, type=body.type)
    return device


@router.get("/devices", response_model=list[Device])
async def list_devices(admin: SystemAdmin, conn: Conn):
    return await many(conn, "SELECT * FROM devices ORDER BY created_at, device_id")


@router.get("/devices/{device_id}", response_model=Device)
async def get_device(device_id: UUID, admin: SystemAdmin, conn: Conn):
    row = await one(conn, "SELECT * FROM devices WHERE device_id = :device_id", device_id=device_id)
    if row is None:
        raise not_found("device")
    return row


@router.post("/devices/{device_id}/activate", response_model=Device)
async def activate_device(device_id: UUID, admin: SystemAdmin, conn: Conn):
    return await change_device_status(conn, device_id, "activate", admin.user_id)


@router.post("/devices/{device_id}/suspend", response_model=Device)
async def suspend_device(device_id: UUID, admin: SystemAdmin, conn: Conn):
    return await change_device_status(conn, device_id, "suspend", admin.user_id)


@router.post("/devices/{device_id}/revoke", response_model=Device)
async def revoke_device(device_id: UUID, admin: SystemAdmin, conn: Conn):
    return await change_device_status(conn, device_id, "revoke", admin.user_id)


async def change_device_status(conn: AsyncConnection, device_id: UUID, action: str, by: UUID) -> dict:
    device = await one(conn, "SELECT * FROM devices WHERE device_id = :device_id FOR UPDATE", device_id=device_id)
    if device is None:
        raise not_found("device")
    if device["status"] not in TRANSITIONS[action]:
        raise HTTPException(status.HTTP_409_CONFLICT, f"cannot {action} a {device['status']} device")

    if action == "activate":
        has_credential = await one(
            conn,
            """SELECT 1 FROM device_credentials WHERE device_id = :device_id AND status = 'active'
               AND (expires_at IS NULL OR expires_at > now())""",
            device_id=device_id,
        )
        if has_credential is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "a device needs an active credential to be activated")
    elif action == "revoke":
        await conn.execute(
            text("UPDATE device_credentials SET status = 'revoked' WHERE device_id = :device_id AND status = 'active'"),
            {"device_id": device_id},
        )
        grant = await one(
            conn, "SELECT grant_id FROM device_grants WHERE device_id = :device_id AND revoked_at IS NULL",
            device_id=device_id,
        )
        if grant:
            await close_grant(conn, grant["grant_id"], device_id, by)

    new_status = {"activate": "active", "suspend": "suspended", "revoke": "revoked"}[action]
    await audit(conn, by, "registry", f"device.{new_status}", target_id=device_id)
    return await one(
        conn, "UPDATE devices SET status = :status WHERE device_id = :device_id RETURNING *",
        status=new_status, device_id=device_id,
    )


# --- credentials -------------------------------------------------------------------------------

@router.post("/devices/{device_id}/credentials", status_code=status.HTTP_201_CREATED, response_model=Credential)
async def add_credential(device_id: UUID, body: CredentialIn, admin: SystemAdmin, conn: Conn):
    device = await one(conn, "SELECT status FROM devices WHERE device_id = :device_id", device_id=device_id)
    if device is None:
        raise not_found("device")
    if device["status"] == "revoked":
        raise HTTPException(status.HTTP_409_CONFLICT, "a revoked device cannot get new credentials")
    credential = await one(
        conn,
        """INSERT INTO device_credentials (device_id, auth_method, key_type, credential_ref, expires_at, metadata)
           VALUES (:device_id, :auth_method, :key_type, :credential_ref, :expires_at, CAST(:metadata AS jsonb))
           RETURNING *""",
        device_id=device_id, auth_method=body.auth_method, key_type=body.key_type,
        credential_ref=body.credential_ref, expires_at=body.expires_at,
        metadata=json.dumps(body.metadata),
    )
    await audit(conn, admin.user_id, "registry", "credential.added", target_id=device_id,
                credential_id=credential["credential_id"], auth_method=body.auth_method)
    return credential


@router.get("/devices/{device_id}/credentials", response_model=list[Credential])
async def list_credentials(device_id: UUID, admin: SystemAdmin, conn: Conn):
    return await many(
        conn, "SELECT * FROM device_credentials WHERE device_id = :device_id ORDER BY created_at",
        device_id=device_id,
    )


@router.post("/credentials/{credential_id}/revoke", response_model=Credential)
async def revoke_credential(credential_id: UUID, admin: SystemAdmin, conn: Conn):
    row = await one(
        conn, "UPDATE device_credentials SET status = 'revoked' WHERE credential_id = :id RETURNING *",
        id=credential_id,
    )
    if row is None:
        raise not_found("credential")
    await audit(conn, admin.user_id, "registry", "credential.revoked", target_id=row["device_id"],
                credential_id=credential_id)
    return row


# --- device grants -----------------------------------------------------------------------------

@router.post("/devices/{device_id}/grants", status_code=status.HTTP_201_CREATED, response_model=Grant)
async def grant_device(device_id: UUID, body: GrantIn, admin: SystemAdmin, conn: Conn):
    device = await one(conn, "SELECT status FROM devices WHERE device_id = :device_id", device_id=device_id)
    if device is None:
        raise not_found("device")
    if device["status"] == "revoked":
        raise HTTPException(status.HTTP_409_CONFLICT, "a revoked device cannot be granted")
    organisation = await one(conn, "SELECT status FROM organisations WHERE org_id = :org_id", org_id=body.org_id)
    if organisation is None:
        raise not_found("organisation")
    if organisation["status"] != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "devices can only be granted to an active organisation")
    grant = await one(
        conn,
        "INSERT INTO device_grants (device_id, org_id, granted_by) VALUES (:device_id, :org_id, :by) RETURNING *",
        device_id=device_id, org_id=body.org_id, by=admin.user_id,
    )
    await audit(conn, admin.user_id, "registry", "grant.created", org_id=body.org_id, target_id=device_id,
                grant_id=grant["grant_id"])
    return grant


@router.get("/devices/{device_id}/grants", response_model=list[Grant])
async def list_grants(device_id: UUID, admin: SystemAdmin, conn: Conn):
    return await many(
        conn, "SELECT * FROM device_grants WHERE device_id = :device_id ORDER BY granted_at", device_id=device_id
    )


@router.post("/grants/{grant_id}/revoke", response_model=Grant)
async def revoke_grant(grant_id: UUID, admin: SystemAdmin, conn: Conn):
    grant = await one(conn, "SELECT * FROM device_grants WHERE grant_id = :id FOR UPDATE", id=grant_id)
    if grant is None:
        raise not_found("grant")
    if grant["revoked_at"] is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "grant already revoked")
    await close_grant(conn, grant_id, grant["device_id"], admin.user_id)
    return await one(conn, "SELECT * FROM device_grants WHERE grant_id = :id", id=grant_id)


# --- audit log and security events -------------------------------------------------------------

@router.get("/audit", response_model=list[AuditEvent])
async def registry_audit(admin: SystemAdmin, conn: Conn, limit: int = Query(200, ge=1, le=1000)):
    """Registry actions only; organisation actions (patients, doctors) belong to that organisation."""
    return await many(conn, "SELECT * FROM audit_log WHERE scope = 'registry' ORDER BY at DESC, event_id LIMIT :n",
                      n=limit)


@router.get("/security-events", response_model=list[SecurityEvent])
async def security_events(admin: SystemAdmin, conn: Conn, limit: int = Query(200, ge=1, le=1000)):
    return await many(conn, "SELECT * FROM security_events ORDER BY ts DESC, event_id LIMIT :n", n=limit)
