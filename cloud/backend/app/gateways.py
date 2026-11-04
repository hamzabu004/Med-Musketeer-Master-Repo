"""Gateway API: the organisation admin's view of its fixed gateways (D17).

For each gateway granted to the caller's organisation: whether it is connected to the cloud and
since when (from the connectivity log, app.ingest), the wearables now on its fixed path, the log
of its connections and of its wearables' presence, and when alerts came through it.

D9 keeps alerts from the organisation admin: an alert here is its time, wearable and patient only,
never its classification, confidence or ECG. Wearables of other organisations on the gateway are
counted, not named. A gateway that is not a fixed gateway granted to the organisation answers 404.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth import OrgAdmin
from app.db import Conn, many, not_found, one

router = APIRouter(tags=["gateways"])


class Connectivity(BaseModel):
    state: Literal["online", "offline", "unknown"]  # unknown: nothing logged yet
    since: datetime | None  # when the state began; online: the gateway's uptime


class OrgGateway(BaseModel):
    device_id: UUID
    status: str
    last_seen: datetime | None
    connectivity: Connectivity
    wearables_connected: int  # the organisation's wearables now on its fixed path
    other_wearables_connected: int  # other organisations' wearables on it, not named
    alerts_24h: int
    last_alert_at: datetime | None


class ConnectedWearable(BaseModel):
    device_id: UUID
    status: str
    last_seen: datetime | None
    connected_since: datetime | None  # its newest "online" through this gateway
    patient_id: UUID | None


class GatewayDetail(OrgGateway):
    wearables: list[ConnectedWearable]


class ConnectivityEvent(BaseModel):
    event_id: UUID
    at: datetime
    device_id: UUID
    device_type: str
    state: str
    reason: str | None


class GatewayAlert(BaseModel):
    """When an alert came through the gateway, and from whom. Not the alert's content (D9)."""
    at: datetime
    device_id: UUID
    patient_id: UUID


ORG_WEARABLE = """EXISTS (SELECT 1 FROM device_grants wg WHERE wg.device_id = w.device_id AND wg.revoked_at IS NULL
                          AND wg.org_id = :org)"""

GATEWAY_SQL = f"""
    SELECT d.device_id, d.status, d.last_seen, c.state AS connectivity_state, c.at AS connectivity_since,
           (SELECT count(*) FROM devices w WHERE w.current_gateway_id = d.device_id AND w.current_mode = 'fixed'
                                             AND {ORG_WEARABLE}) AS wearables_connected,
           (SELECT count(*) FROM devices w WHERE w.current_gateway_id = d.device_id AND w.current_mode = 'fixed'
                                             AND NOT {ORG_WEARABLE}) AS other_wearables_connected,
           (SELECT count(*) FROM alerts a JOIN patients p ON p.patient_id = a.patient_id AND p.org_id = :org
            WHERE a.gateway_id = d.device_id AND a.created_at > now() - interval '24 hours') AS alerts_24h,
           (SELECT max(a.created_at) FROM alerts a JOIN patients p ON p.patient_id = a.patient_id AND p.org_id = :org
            WHERE a.gateway_id = d.device_id) AS last_alert_at
    FROM devices d
    JOIN device_grants g ON g.device_id = d.device_id AND g.revoked_at IS NULL AND g.org_id = :org
    LEFT JOIN LATERAL (SELECT state, at FROM connectivity_events e
                       WHERE e.device_id = d.device_id AND e.gateway_id = d.device_id
                       ORDER BY e.at DESC LIMIT 1) c ON TRUE
    WHERE d.type = 'fixed_gateway'
"""


def gateway_view(row: dict) -> dict:
    state, since = row.pop("connectivity_state"), row.pop("connectivity_since")
    return {**row, "connectivity": {"state": state or "unknown", "since": since}}


async def gateway_in_scope(conn: AsyncConnection, admin, gateway_id: UUID) -> dict:
    row = await one(conn, GATEWAY_SQL + " AND d.device_id = :g", org=admin.org_id, g=gateway_id)
    if row is None:
        raise not_found("gateway")
    return gateway_view(row)


@router.get("/gateways", response_model=list[OrgGateway])
async def organisation_gateways(admin: OrgAdmin, conn: Conn):
    return [gateway_view(row) for row in await many(conn, GATEWAY_SQL + " ORDER BY d.device_id", org=admin.org_id)]


@router.get("/gateways/{gateway_id}", response_model=GatewayDetail)
async def gateway_detail(gateway_id: UUID, admin: OrgAdmin, conn: Conn):
    gateway = await gateway_in_scope(conn, admin, gateway_id)
    wearables = await many(conn, f"""
        SELECT w.device_id, w.status, w.last_seen, c.at AS connected_since, a.patient_id
        FROM devices w
        LEFT JOIN device_assignments a ON a.device_id = w.device_id AND a.unassigned_at IS NULL
        LEFT JOIN LATERAL (SELECT at FROM connectivity_events e
                           WHERE e.device_id = w.device_id AND e.gateway_id = :g AND e.state = 'online'
                           ORDER BY e.at DESC LIMIT 1) c ON TRUE
        WHERE w.current_gateway_id = :g AND w.current_mode = 'fixed' AND {ORG_WEARABLE}
        ORDER BY w.device_id
    """, g=gateway_id, org=admin.org_id)
    return {**gateway, "wearables": wearables}


@router.get("/gateways/{gateway_id}/connectivity", response_model=list[ConnectivityEvent])
async def gateway_connectivity(gateway_id: UUID, admin: OrgAdmin, conn: Conn, limit: int = Query(200, ge=1, le=1000)):
    """The gateway's connections and its wearables' presence through it, newest first. Rows of
    wearables not granted to the organisation are left out."""
    await gateway_in_scope(conn, admin, gateway_id)
    return await many(conn, f"""
        SELECT e.event_id, e.at, e.device_id, w.type AS device_type, e.state, e.reason
        FROM connectivity_events e JOIN devices w ON w.device_id = e.device_id
        WHERE e.gateway_id = :g AND (e.device_id = :g OR {ORG_WEARABLE})
        ORDER BY e.at DESC, e.event_id LIMIT :n
    """, g=gateway_id, org=admin.org_id, n=limit)


@router.get("/gateways/{gateway_id}/alerts", response_model=list[GatewayAlert])
async def gateway_alerts(gateway_id: UUID, admin: OrgAdmin, conn: Conn, limit: int = Query(200, ge=1, le=1000)):
    """When the organisation's patients' alerts came through the gateway, newest first."""
    await gateway_in_scope(conn, admin, gateway_id)
    return await many(conn, """
        SELECT a.created_at AS at, a.device_id, a.patient_id
        FROM alerts a JOIN patients p ON p.patient_id = a.patient_id AND p.org_id = :org
        WHERE a.gateway_id = :g
        ORDER BY a.created_at DESC, a.alert_id LIMIT :n
    """, g=gateway_id, org=admin.org_id, n=limit)
