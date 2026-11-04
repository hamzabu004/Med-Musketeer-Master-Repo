"""A populated database for the access-control tests (TC-C09 to TC-C11), arranged as the owner.

Two organisations, A and B, each with an org admin, two doctors and their patients, wearables
issued and granted, a gateway the first wearable is connected through, a monitoring session with an
ECG segment, chunk, classification and alert (through the gateway), and a recorded disorder. Organisation A also has the spare rows the matrix's write endpoints act on.
"""
import uuid
from dataclasses import dataclass, field

from sqlalchemy import text

from app.auth import Principal


def insert(db, sql: str, **params):
    return db.scalar(text(sql), params)


@dataclass
class Org:
    org_id: uuid.UUID
    admin: Principal
    doctor: Principal  # treats `patient`
    other_doctor: Principal  # treats `other_patient`
    patient: Principal  # the patient's own login
    patient_id: uuid.UUID
    other_patient_id: uuid.UUID
    wearable: uuid.UUID  # issued to `patient`
    other_wearable: uuid.UUID  # issued to `other_patient`
    gateway: uuid.UUID  # granted; online, with `wearable` on its fixed path
    segment: uuid.UUID
    alert: uuid.UUID
    other_segment: uuid.UUID
    other_alert: uuid.UUID
    secrets: set[str] = field(default_factory=set)  # values that identify patients and doctors


def make_user(db, role: str, org_id) -> uuid.UUID:
    return insert(db, "INSERT INTO users (zitadel_sub, role, org_id) VALUES (:s, :r, :o) RETURNING user_id",
                  s=f"sub-{uuid.uuid4()}", r=role, o=org_id)


def make_device(db, device_type: str, org_id, granted_by, status: str = "active") -> uuid.UUID:
    device_id = insert(db, """INSERT INTO devices (device_id, type, status, is_testbed, registered_by)
                              VALUES (:d, :t, :s, true, :by) RETURNING device_id""",
                       d=uuid.uuid4(), t=device_type, s=status, by=granted_by)
    insert(db, """INSERT INTO device_credentials (device_id, auth_method, credential_ref)
                  VALUES (:d, 'x509_mtls', :ref) RETURNING credential_id""", d=device_id, ref=uuid.uuid4().hex * 2)
    if org_id is not None:
        insert(db, "INSERT INTO device_grants (device_id, org_id, granted_by) VALUES (:d, :o, :by) RETURNING grant_id",
               d=device_id, o=org_id, by=granted_by)
    return device_id


def make_patient(db, org_id, admin_id, doctor_id, wearable, gateway, user_id=None) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]:
    """A patient with a doctor, an issued wearable, a session, one alert segment; returns
    (patient_id, segment_id, alert_id, pseudonym)."""
    pseudonym = f"P-{uuid.uuid4().hex[:8]}"
    patient_id = insert(db, "INSERT INTO patients (user_id, org_id, pseudonym) VALUES (:u, :o, :p) RETURNING patient_id",
                        u=user_id, o=org_id, p=pseudonym)
    insert(db, "INSERT INTO care_assignments (patient_id, doctor_id, assigned_by) VALUES (:p, :d, :by) RETURNING 1",
           p=patient_id, d=doctor_id, by=admin_id)
    insert(db, "INSERT INTO device_assignments (device_id, patient_id, issued_by) VALUES (:d, :p, :by) RETURNING 1",
           d=wearable, p=patient_id, by=admin_id)
    insert(db, "INSERT INTO patient_disorders (patient_id, disorder, recorded_by) VALUES (:p, :d, :by) RETURNING 1",
           p=patient_id, d=f"disorder-{pseudonym}", by=admin_id)
    session = insert(db, """INSERT INTO monitoring_sessions (device_id, patient_id, org_id, path)
                            VALUES (:d, :p, :o, 'fixed') RETURNING session_id""", d=wearable, p=patient_id, o=org_id)
    segment = insert(db, """INSERT INTO ecg_segments (session_id, patient_id, device_id, kind, fs_hz, started_at)
                            VALUES (:s, :p, :d, 'alert', 360, now()) RETURNING segment_id""",
                     s=session, p=patient_id, d=wearable)
    insert(db, """INSERT INTO ecg_chunks (segment_id, seq, ts, n_samples, samples, auth_method)
                  VALUES (:g, 0, now(), 2, '\\x01000200'::bytea, 'x509_mtls') RETURNING 1""", g=segment)
    classification = insert(db, """INSERT INTO classifications (segment_id, source, model_version, label, confidence)
                                   VALUES (:g, 'wearable', 'tinydl-0.1', 'abnormal', 0.9) RETURNING classification_id""",
                            g=segment)
    alert = insert(db, """INSERT INTO alerts (device_id, patient_id, classification_id, origin, gateway_id)
                          VALUES (:d, :p, :c, 'wearable', :g) RETURNING alert_id""",
                   d=wearable, p=patient_id, c=classification, g=gateway)
    return patient_id, segment, alert, pseudonym


def make_org(db, system_admin_id, name: str) -> Org:
    org_id = insert(db, """INSERT INTO organisations (name, kind, zitadel_org_id, registered_by)
                           VALUES (:n, 'public', :z, :by) RETURNING org_id""",
                    n=name, z=f"z-{name}-{uuid.uuid4().hex[:6]}", by=system_admin_id)
    admin, doctor, other_doctor, patient_user = (make_user(db, role, org_id)
                                                 for role in ("org_admin", "doctor", "doctor", "patient"))
    wearable = make_device(db, "wearable", org_id, system_admin_id)
    other_wearable = make_device(db, "wearable", org_id, system_admin_id)
    gateway = make_device(db, "fixed_gateway", org_id, system_admin_id)
    for device in (gateway, wearable):
        insert(db, """INSERT INTO connectivity_events (device_id, gateway_id, state, at)
                      VALUES (:d, :g, 'online', now()) RETURNING 1""", d=device, g=gateway)
    db.execute(text("UPDATE devices SET current_mode = 'fixed', current_gateway_id = :g, last_seen = now() WHERE device_id = :d"),
               {"g": gateway, "d": wearable})
    patient_id, segment, alert, pseudonym = make_patient(db, org_id, admin, doctor, wearable, gateway, patient_user)
    other_patient_id, other_segment, other_alert, other_pseudonym = make_patient(
        db, org_id, admin, other_doctor, other_wearable, gateway)
    secrets = {str(value) for value in (doctor, other_doctor, patient_user, patient_id, other_patient_id,
                                        segment, alert, other_segment, other_alert)}
    secrets |= {pseudonym, other_pseudonym, f"disorder-{pseudonym}", f"disorder-{other_pseudonym}"}
    return Org(
        org_id=org_id,
        admin=Principal(admin, "org_admin", org_id),
        doctor=Principal(doctor, "doctor", org_id),
        other_doctor=Principal(other_doctor, "doctor", org_id),
        patient=Principal(patient_user, "patient", org_id, patient_id),
        patient_id=patient_id, other_patient_id=other_patient_id,
        wearable=wearable, other_wearable=other_wearable, gateway=gateway,
        segment=segment, alert=alert, other_segment=other_segment, other_alert=other_alert,
        secrets=secrets,
    )


@dataclass
class World:
    system_admin: Principal
    a: Org
    b: Org
    # spare rows in organisation A for the matrix's write endpoints
    spare_patient: uuid.UUID  # no doctor, no wearable
    spare_doctor: uuid.UUID
    spare_wearable: uuid.UUID  # granted to A, not issued
    pending_device: uuid.UUID  # with a credential, not granted
    credential: uuid.UUID  # of pending_device
    grant: uuid.UUID  # open grant of spare_wearable

    def principal(self, role: str) -> Principal:
        return {"system_admin": self.system_admin, "org_admin": self.a.admin,
                "doctor": self.a.doctor, "patient": self.a.patient}[role]


def build_world(db) -> World:
    system_admin = insert(db, "INSERT INTO users (zitadel_sub, role) VALUES (:s, 'system_admin') RETURNING user_id",
                          s=f"sub-{uuid.uuid4()}")
    a, b = make_org(db, system_admin, "A"), make_org(db, system_admin, "B")
    spare_patient = insert(db, "INSERT INTO patients (org_id, pseudonym) VALUES (:o, 'P-spare') RETURNING patient_id",
                           o=a.org_id)
    spare_wearable = make_device(db, "wearable", a.org_id, system_admin)
    pending_device = make_device(db, "wearable", None, system_admin, status="pending")
    return World(
        system_admin=Principal(system_admin, "system_admin", None),
        a=a, b=b,
        spare_patient=spare_patient,
        spare_doctor=make_user(db, "doctor", a.org_id),
        spare_wearable=spare_wearable,
        pending_device=pending_device,
        credential=insert(db, "SELECT credential_id FROM device_credentials WHERE device_id = :d", d=pending_device),
        grant=insert(db, "SELECT grant_id FROM device_grants WHERE device_id = :d", d=spare_wearable),
    )
