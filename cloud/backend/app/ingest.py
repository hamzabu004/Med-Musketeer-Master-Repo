"""Ingestion API (D7, D15): stores ingest-v1 messages from the MQTT adapter. Called only by the
adapter, with a shared secret; not in the API description.

Every message is checked against the registry before anything is written:
- the attesting gateway (D1) must be an active fixed_gateway, and a gateway reports only for itself;
- a wearable must be registered as one and active; an alert also needs the wearable to be issued
  to a patient of the organisation it is granted to.
An alert opens (or continues) the wearable's monitoring session for that patient and path, and
writes the segment, its samples, the wearable's screening and the alert, in one transaction. An
alert has no severity: the wearable gives a label and a confidence, and the cloud does not rate it. An
IDS event becomes a security event of the attesting gateway. Messages with a msg_id are recorded
in ingested_messages, so a redelivery is answered "duplicate" and stored once.

Presence (stack.md, liveness): any message refreshes the gateway's last_seen, and a wearable's
alert or online status sets it on the fixed path through that gateway. A wearable that goes
offline, or whose gateway goes offline, is shown as `unknown`, never as offline: it may have moved
to the other path. An offline report older than the device's last_seen is stale and ignored.

Connectivity log (D17): each change of state of a gateway's connection, and of a wearable's
presence through a gateway, is appended to connectivity_events. A report of the state already
logged (the broker's connect event and the gateway's own status both say online) or older than the
newest row adds nothing, so the newest row's time is when the current state began.

A gateway's own status may carry the revocation list version it enforces (D16); it is stored on
the gateway, so the system admin sees which gateways are behind.

Answers: 200 {"result": "stored" | "duplicate"}, or 422 {"rejected": reason} for a message that
will never be accepted as it is (the adapter drops it). Every rejection is logged with its reason.
"""
import hmac
import json
import logging
import time
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.contracts import AlertPayload, IdsEventPayload, Ingest, StatusPayload, describe
from app.db import Conn, one

log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", include_in_schema=False)

MAX_CLOCK_SKEW = timedelta(minutes=5)  # how far a device's timestamp may lead the broker's
ALERTS_CHANNEL = "mm_alerts"  # NOTIFY channel for new alerts (Iteration 6 alert push)


def adapter_caller(request: Request) -> None:
    secret = request.app.state.settings.ingest_secret
    if secret is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ingestion is not configured")
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), secret.get_secret_value().encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not the adapter")


Adapter = Annotated[None, Depends(adapter_caller)]


class Rejected(Exception):
    """The message is refused for good; the reason is logged and returned to the adapter."""


@router.post("/ingest")
async def ingest(body: Annotated[dict[str, Any], Body()], _: Adapter, conn: Conn) -> dict:
    started = time.perf_counter()
    try:
        message = Ingest.model_validate(body)
    except ValidationError as error:
        raise rejection(body.get("device_id"), body.get("msg_type"), describe(error)) from None
    try:
        result = await store(conn, message)
    except Rejected as error:
        # Raised, so the request's transaction rolls back whatever was written before.
        raise rejection(message.device_id, message.msg_type, str(error)) from None
    log.info("ingest %s device=%s msg_type=%s attested_by=%s ms=%.1f", result["result"], message.device_id,
             message.msg_type, message.attested_by, (time.perf_counter() - started) * 1000)
    return result


def rejection(device_id, msg_type, reason: str) -> HTTPException:
    log.warning("ingest rejected device=%s msg_type=%s reason=%s", device_id, msg_type, reason)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"rejected": reason})


async def store(conn: AsyncConnection, m: Ingest) -> dict:
    if not m.authenticated:
        raise Rejected("the device was not authenticated")
    if m.attested_by is None:
        raise Rejected("no attesting gateway: the mobile path is not ingested yet")
    # Lock order: the gateway, then the wearable, as in every path here.
    gateway = await one(conn, "SELECT type, status, last_seen FROM devices WHERE device_id = :g FOR UPDATE",
                        g=m.attested_by)
    if m.device_type == "fixed_gateway" and m.device_id != m.attested_by:
        raise Rejected("a gateway reports only for itself")
    # A suspended gateway's disconnect still counts, so its wearables do not stay on its path.
    going_offline = m.device_type == "fixed_gateway" and getattr(m.message, "state", None) == "offline"
    if gateway is None or gateway["type"] != "fixed_gateway" or (gateway["status"] != "active" and not going_offline):
        raise Rejected("the attesting gateway is not an active fixed gateway")
    await seen(conn, m.attested_by, m.received_at)

    if m.device_type == "fixed_gateway":
        if isinstance(m.message, StatusPayload):
            return await gateway_status(conn, m, m.message, gateway["last_seen"])
        return await ids_event(conn, m, m.message)

    device = await one(conn, "SELECT type, status, last_seen FROM devices WHERE device_id = :d FOR UPDATE",
                       d=m.device_id)
    if device is None:
        raise Rejected("unknown device")
    if device["type"] != "wearable":
        raise Rejected(f"the device is a {device['type']}, not a wearable")
    if device["status"] != "active":
        raise Rejected(f"the wearable is {device['status']}")
    if isinstance(m.message, StatusPayload):
        if m.message.revocation_version is not None:
            raise Rejected("revocation_version is reported by a gateway for itself, not for a wearable")
        return await wearable_status(conn, m, m.message, device["last_seen"])
    return await alert(conn, m, m.message)


# --- presence ----------------------------------------------------------------------------------

async def seen(conn: AsyncConnection, device_id: UUID, at) -> None:
    await conn.execute(text("UPDATE devices SET last_seen = greatest(last_seen, :t) WHERE device_id = :d"),
                       {"t": at, "d": device_id})


async def on_fixed_path(conn: AsyncConnection, m: Ingest) -> None:
    await conn.execute(text("""
        UPDATE devices SET last_seen = greatest(last_seen, :t), current_mode = 'fixed', current_gateway_id = :g
        WHERE device_id = :d
    """), {"t": m.received_at, "g": m.attested_by, "d": m.device_id})


def stale(m: Ingest, last_seen) -> bool:
    return last_seen is not None and m.received_at < last_seen


async def log_connectivity(conn: AsyncConnection, m: Ingest, p: StatusPayload) -> None:
    """Appends the report to the connectivity log if it changes the device's state on this gateway."""
    await conn.execute(text("""
        INSERT INTO connectivity_events (device_id, gateway_id, state, reason, at)
        SELECT :d, :g, :s, :r, :t
        WHERE NOT EXISTS (
            SELECT 1 FROM (SELECT state, at FROM connectivity_events WHERE device_id = :d AND gateway_id = :g
                           ORDER BY at DESC LIMIT 1) newest
            WHERE newest.state = :s OR newest.at > :t)
    """), {"d": m.device_id, "g": m.attested_by, "s": p.state, "r": p.reason, "t": m.received_at})


async def wearable_status(conn: AsyncConnection, m: Ingest, p: StatusPayload, last_seen) -> dict:
    if p.state == "online":
        await on_fixed_path(conn, m)
    elif not stale(m, last_seen):
        # Not heard from, so last_seen stays; the path is unknown until it shows up on one.
        await conn.execute(text("""
            UPDATE devices SET current_mode = 'unknown', current_gateway_id = NULL WHERE device_id = :d
        """), {"d": m.device_id})
    await log_connectivity(conn, m, p)
    return {"result": "stored", "state": p.state, "reason": p.reason}


async def gateway_status(conn: AsyncConnection, m: Ingest, p: StatusPayload, last_seen) -> dict:
    if p.revocation_version is not None and not stale(m, last_seen):
        await conn.execute(text("UPDATE devices SET revocation_version = :v WHERE device_id = :d"),
                           {"v": p.revocation_version, "d": m.device_id})
    unknown = 0
    if p.state == "offline" and not stale(m, last_seen):
        # Gateway unreachable is not wearable offline: its wearables are unknown until it is back.
        unknown = (await conn.execute(text("""
            UPDATE devices SET current_mode = 'unknown' WHERE current_gateway_id = :g AND current_mode = 'fixed'
        """), {"g": m.device_id})).rowcount
    await log_connectivity(conn, m, p)
    return {"result": "stored", "state": p.state, "wearables_unknown": unknown}


# --- alerts and IDS events ---------------------------------------------------------------------

async def first_delivery(conn: AsyncConnection, m: Ingest, msg_id: UUID, seq: int | None = None) -> bool:
    """Records the message; False if it was stored before (a redelivery)."""
    return await conn.scalar(text("""
        INSERT INTO ingested_messages (device_id, msg_id, msg_type, seq, attested_by, sent_at, broker_at, adapter_at)
        VALUES (:d, :m, :t, :seq, :g, :sent, :broker, :adapter)
        ON CONFLICT DO NOTHING RETURNING true
    """), {"d": m.device_id, "m": msg_id, "t": m.msg_type, "seq": seq, "g": m.attested_by, "sent": m.hops.sent_at,
           "broker": m.hops.broker_at, "adapter": m.hops.adapter_at}) is not None


async def current_session(conn: AsyncConnection, device_id: UUID, patient_id: UUID, org_id: UUID, path: str) -> UUID:
    """The open session of this device for this patient and path, or a new one. A session's patient
    and path never change (migration 0001), so an open session for anything else is ended first."""
    open_session = await one(conn, """
        SELECT session_id, patient_id, org_id, path FROM monitoring_sessions WHERE device_id = :d AND ended_at IS NULL
    """, d=device_id)
    if open_session is not None:
        if (open_session["patient_id"], open_session["org_id"], open_session["path"]) == (patient_id, org_id, path):
            return open_session["session_id"]
        await conn.execute(text("UPDATE monitoring_sessions SET ended_at = now() WHERE session_id = :s"),
                           {"s": open_session["session_id"]})
    return await conn.scalar(text("""
        INSERT INTO monitoring_sessions (device_id, patient_id, org_id, path) VALUES (:d, :p, :o, :path)
        RETURNING session_id
    """), {"d": device_id, "p": patient_id, "o": org_id, "path": path})


async def alert(conn: AsyncConnection, m: Ingest, p: AlertPayload) -> dict:
    if p.segment_start > m.received_at + MAX_CLOCK_SKEW:
        raise Rejected("segment_start is in the future")
    issued = await one(conn, """
        SELECT a.patient_id, p.org_id FROM device_assignments a
        JOIN patients p ON p.patient_id = a.patient_id
        JOIN device_grants g ON g.device_id = a.device_id AND g.revoked_at IS NULL AND g.org_id = p.org_id
        WHERE a.device_id = :d AND a.unassigned_at IS NULL
        FOR SHARE OF a, g
    """, d=m.device_id)  # locked: a concurrent return or grant revoke waits, or has ended it already
    if issued is None:
        raise Rejected("the wearable is not issued to a patient")
    if not await first_delivery(conn, m, p.msg_id, p.seq):
        return {"result": "duplicate", "msg_id": str(p.msg_id)}

    patient_id = issued["patient_id"]
    session_id = await current_session(conn, m.device_id, patient_id, issued["org_id"], "fixed")
    segment_id = await conn.scalar(text("""
        INSERT INTO ecg_segments (session_id, patient_id, device_id, kind, fs_hz, lead, started_at, ended_at)
        VALUES (:s, :p, :d, 'alert', :fs, :lead, :start, :end) RETURNING segment_id
    """), {"s": session_id, "p": patient_id, "d": m.device_id, "fs": p.fs_hz, "lead": p.lead, "start": p.segment_start,
           "end": p.segment_start + timedelta(seconds=p.n_samples / p.fs_hz)})
    await conn.execute(text("""
        INSERT INTO ecg_chunks (segment_id, seq, ts, n_samples, samples, attested_by, auth_method)
        VALUES (:g, 0, :ts, :n, :b, :by, :method)
    """), {"g": segment_id, "ts": p.segment_start, "n": p.n_samples, "b": p.decoded(), "by": m.attested_by,
           "method": m.auth_method})
    classification_id = await conn.scalar(text("""
        INSERT INTO classifications (segment_id, source, model_version, label, confidence)
        VALUES (:g, 'wearable', :model, :label, :c) RETURNING classification_id
    """), {"g": segment_id, "model": p.screening.model, "label": p.screening.label, "c": p.screening.confidence})
    alert_id = await conn.scalar(text("""
        INSERT INTO alerts (device_id, patient_id, classification_id, origin, gateway_id)
        VALUES (:d, :p, :c, 'wearable', :g) RETURNING alert_id
    """), {"d": m.device_id, "p": patient_id, "c": classification_id, "g": m.attested_by})
    await on_fixed_path(conn, m)
    # Delivered to listeners when the transaction commits, and only then.
    await conn.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": ALERTS_CHANNEL, "payload": json.dumps(
        {"alert_id": str(alert_id), "patient_id": str(patient_id), "device_id": str(m.device_id)})})
    return {"result": "stored", "msg_id": str(p.msg_id), "alert_id": str(alert_id), "segment_id": str(segment_id),
            "session_id": str(session_id)}


async def ids_event(conn: AsyncConnection, m: Ingest, p: IdsEventPayload) -> dict:
    if p.ts > m.received_at + MAX_CLOCK_SKEW:
        raise Rejected("ts is in the future")
    if p.device_id is not None and await one(conn, "SELECT 1 FROM devices WHERE device_id = :d", d=p.device_id) is None:
        raise Rejected("the event names an unknown device")
    if not await first_delivery(conn, m, p.msg_id):
        return {"result": "duplicate", "msg_id": str(p.msg_id)}
    # The gateway is the attested publisher (D1), never a field of the payload.
    await conn.execute(text("""
        INSERT INTO security_events (event_id, ts, gateway_id, device_id, mode, predicted_class, outcome, action,
                                     action_result)
        VALUES (:e, :ts, :g, :d, :mode, :cls, :outcome, :action, :result)
    """), {"e": p.msg_id, "ts": p.ts, "g": m.attested_by, "d": p.device_id, "mode": p.mode, "cls": p.predicted_class,
           "outcome": p.outcome, "action": p.action, "result": p.action_result})
    return {"result": "stored", "msg_id": str(p.msg_id), "event_id": str(p.msg_id)}
