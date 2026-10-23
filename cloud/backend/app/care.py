"""Care API: ECG segments, classifications and alerts, for doctors and patients only (D9).

A doctor reads the data of their current patients and acknowledges their alerts; a patient reads
their own. ECG queries are also limited to monitoring sessions of the caller's organisation, as a
session's patient and organisation are fixed when it opens. Rows are written by ingestion (Slice 5).
"""
import base64
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import CareReader, Doctor
from app.db import Conn, many, not_found, one
from app.organisation import patient_in_scope

router = APIRouter(tags=["care"])


class Alert(BaseModel):
    alert_id: UUID
    device_id: UUID
    patient_id: UUID
    origin: str
    severity: str
    created_at: datetime
    acknowledged_by: UUID | None
    acknowledged_at: datetime | None
    classification_id: UUID | None
    segment_id: UUID | None
    label: str | None
    confidence: float | None


class Segment(BaseModel):
    segment_id: UUID
    session_id: UUID
    patient_id: UUID
    device_id: UUID
    kind: str
    fs_hz: int
    started_at: datetime
    ended_at: datetime | None


class Classification(BaseModel):
    classification_id: UUID
    source: str
    model_version: str
    label: str
    confidence: float | None
    created_at: datetime


class Chunk(BaseModel):
    seq: int
    ts: datetime
    n_samples: int
    encoding: Literal["int16le-base64"] = "int16le-base64"
    samples: str


class SegmentDetail(Segment):
    classifications: list[Classification]
    chunks: list[Chunk]


ALERT_SQL = """
    SELECT a.alert_id, a.device_id, a.patient_id, a.origin, a.severity, a.created_at,
           a.acknowledged_by, a.acknowledged_at, a.classification_id,
           c.segment_id, c.label, c.confidence
    FROM alerts a LEFT JOIN classifications c ON c.classification_id = a.classification_id
"""


def unacknowledged_only(flag: bool) -> str:
    return "AND a.acknowledged_at IS NULL" if flag else ""


@router.get("/alerts", response_model=list[Alert])
async def my_alerts(principal: CareReader, conn: Conn, unacknowledged: bool = False,
                    limit: int = Query(200, ge=1, le=1000)):
    """Doctor: the alerts of their current patients. Patient: their own."""
    if principal.role == "doctor":
        scope = """a.patient_id IN (SELECT c.patient_id FROM care_assignments c JOIN patients p USING (patient_id)
                                    WHERE c.doctor_id = :user AND c.valid_to IS NULL AND p.org_id = :org)"""
    else:
        scope = "a.patient_id = :patient"
    return await many(conn, f"""{ALERT_SQL} WHERE {scope} {unacknowledged_only(unacknowledged)}
                                ORDER BY a.created_at DESC, a.alert_id LIMIT :n""",
                      user=principal.user_id, org=principal.org_id, patient=principal.patient_id, n=limit)


@router.get("/patients/{patient_id}/alerts", response_model=list[Alert])
async def patient_alerts(patient_id: UUID, principal: CareReader, conn: Conn, unacknowledged: bool = False,
                         limit: int = Query(200, ge=1, le=1000)):
    await patient_in_scope(conn, principal, patient_id)
    return await many(conn, f"""{ALERT_SQL} WHERE a.patient_id = :p {unacknowledged_only(unacknowledged)}
                                ORDER BY a.created_at DESC, a.alert_id LIMIT :n""", p=patient_id, n=limit)


@router.post("/alerts/{alert_id}/acknowledge", response_model=Alert)
async def acknowledge_alert(alert_id: UUID, doctor: Doctor, conn: Conn):
    alert = await one(conn, "SELECT patient_id, acknowledged_at FROM alerts WHERE alert_id = :a FOR UPDATE", a=alert_id)
    if alert is None:
        raise not_found("alert")
    await patient_in_scope(conn, doctor, alert["patient_id"])  # 404 if not the doctor's patient
    if alert["acknowledged_at"] is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "alert already acknowledged")
    await conn.execute(text("UPDATE alerts SET acknowledged_by = :u, acknowledged_at = now() WHERE alert_id = :a"),
                       {"u": doctor.user_id, "a": alert_id})
    return await one(conn, ALERT_SQL + " WHERE a.alert_id = :a", a=alert_id)


@router.get("/patients/{patient_id}/segments", response_model=list[Segment])
async def patient_segments(patient_id: UUID, principal: CareReader, conn: Conn,
                           limit: int = Query(200, ge=1, le=1000)):
    await patient_in_scope(conn, principal, patient_id)
    return await many(conn, """
        SELECT g.* FROM ecg_segments g
        JOIN monitoring_sessions s ON s.session_id = g.session_id AND s.org_id = :org
        WHERE g.patient_id = :p ORDER BY g.started_at DESC, g.segment_id LIMIT :n
    """, p=patient_id, org=principal.org_id, n=limit)


@router.get("/segments/{segment_id}", response_model=SegmentDetail)
async def segment_detail(segment_id: UUID, principal: CareReader, conn: Conn):
    """One segment with its samples (little-endian int16, Base64 per chunk) and classifications."""
    segment = await one(conn, """
        SELECT g.* FROM ecg_segments g
        JOIN monitoring_sessions s ON s.session_id = g.session_id AND s.org_id = :org
        WHERE g.segment_id = :g
    """, g=segment_id, org=principal.org_id)
    if segment is None:
        raise not_found("segment")
    await patient_in_scope(conn, principal, segment["patient_id"])
    chunks = await many(conn, "SELECT seq, ts, n_samples, samples FROM ecg_chunks WHERE segment_id = :g ORDER BY seq, ts",
                        g=segment_id)
    return {
        **segment,
        "classifications": await many(conn, "SELECT * FROM classifications WHERE segment_id = :g ORDER BY created_at",
                                      g=segment_id),
        "chunks": [{**chunk, "samples": base64.b64encode(chunk["samples"]).decode()} for chunk in chunks],
    }
