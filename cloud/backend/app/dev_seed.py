"""Development data for the dashboard, before ingestion (Slice 5) fills the ECG tables (D14).

`python -m app.manage seed-dev` creates, in ZITADEL and the database:
- a system admin in the default organisation, and the organisation "Dev Hospital" with an org admin,
  two doctors and three patients, all human users with one printed password, so each role can sign
  in to the dashboard;
- a fixed gateway and four wearables granted to the organisation, two of them issued;
- monitoring sessions with alert segments of synthetic ECG (360 Hz, MLII-like, int16), gateway
  classifications (AAMI labels), alerts, and IDS events from the gateway.

The ECG is generated, not recorded: it exists to exercise the screens and carries no clinical
meaning. The command refuses to run when the database already has an organisation (unless told otherwise,
for the stack tests). If any step fails, what it created in ZITADEL is deleted again, so the guard
(which looks at the database) stays truthful and the command can be re-run.
"""
import json
import math
import random
import secrets
import struct
import sys
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import create_engine, text

from app.settings import Settings
from app.tokens import ZitadelConfig
from app.zitadel import ORG_ROLES
from app.zitadel_bootstrap import Zitadel

ORG_NAME = "Dev Hospital"
EMAIL_DOMAIN = "medmusketeer.example"
FS_HZ = 360
ADC_PER_MV = 200  # MIT-BIH's gain, so the samples look like the training data's
SEGMENT_S = 10


@dataclass
class Person:
    key: str
    role: str
    given_name: str
    family_name: str
    pseudonym: str | None = None
    zitadel_sub: str = ""
    user_id: uuid.UUID | None = None

    @property
    def email(self) -> str:
        return f"{self.key}@{EMAIL_DOMAIN}"


# Templates: seed() works on fresh copies, so nothing carries over between runs in one process.
PEOPLE = (
    Person("sysadmin", "system_admin", "Sana", "Sysadmin"),
    Person("orgadmin", "org_admin", "Omar", "Admin"),
    Person("doctor1", "doctor", "Sarah", "Ahmed"),
    Person("doctor2", "doctor", "Bilal", "Raza"),
    Person("patient1", "patient", "Ali", "Khan", pseudonym="P-1001"),
    Person("patient2", "patient", "Fatima", "Noor", pseudonym="P-1002"),
    Person("patient3", "patient", "Usman", "Iqbal", pseudonym="P-1003"),
)


# --- synthetic ECG ---------------------------------------------------------------------------

def beat(t: float, ectopic: bool) -> float:
    """One heartbeat in mV at t seconds from its R peak: a sum of Gaussian waves. An ectopic
    (PVC-like) beat has no P wave, a wide QRS and an inverted T wave."""
    waves = ([(1.6, 0.0, 0.035), (-0.4, 0.07, 0.03), (-0.45, 0.3, 0.07)] if ectopic else
             [(0.12, -0.2, 0.025), (-0.12, -0.03, 0.01), (1.1, 0.0, 0.012), (-0.25, 0.035, 0.012), (0.3, 0.26, 0.045)])
    return sum(a * math.exp(-((t - mu) ** 2) / (2 * w * w)) for a, mu, w in waves)


def ecg(seconds: int, bpm: float, ectopic_every: int | None, rng: random.Random) -> list[int]:
    n = seconds * FS_HZ
    peaks, t, index = [], 0.4, 0
    while t < seconds + 1:
        index += 1
        ectopic = ectopic_every is not None and index % ectopic_every == 0
        peaks.append((t, ectopic))
        t += 60 / bpm * (0.75 if ectopic else 1) * rng.uniform(0.96, 1.04)
    samples = []
    for i in range(n):
        x = i / FS_HZ
        mv = sum(beat(x - peak, ectopic) for peak, ectopic in peaks if -0.5 < x - peak < 0.6)
        mv += 0.05 * math.sin(2 * math.pi * 0.3 * x) + rng.gauss(0, 0.01)  # baseline wander, noise
        samples.append(max(-32768, min(32767, round(mv * ADC_PER_MV))))
    return samples


def pack(samples: list[int]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


# --- ZITADEL ---------------------------------------------------------------------------------

def create_zitadel_people(zitadel: Zitadel, config: ZitadelConfig, people: list[Person], password: str,
                          created: list[str]) -> str:
    """Creates the organisation and every person in ZITADEL; returns the ZITADEL organisation id.
    Appends to `created` what to delete if seeding fails: the organisation (which takes its users
    with it) and the system admin, who lives in the default organisation."""
    zitadel_org = zitadel.call("POST", "/v2/organizations", ok=(200, 201), json={"name": ORG_NAME})["organizationId"]
    created.append(f"/v2/organizations/{zitadel_org}")
    grant_id = zitadel.call("POST", f"/management/v1/projects/{config.project_id}/grants", org=config.default_org_id,
                            json={"grantedOrgId": zitadel_org, "roleKeys": list(ORG_ROLES)})["grantId"]
    for person in people:
        org = config.default_org_id if person.role == "system_admin" else zitadel_org
        person.zitadel_sub = zitadel.call("POST", "/v2/users/human", ok=(200, 201), json={
            "organization": {"orgId": org},
            "username": person.email,
            "profile": {"givenName": person.given_name, "familyName": person.family_name},
            "email": {"email": person.email, "isVerified": True},
            "password": {"password": password, "changeRequired": False},
        })["userId"]
        if person.role == "system_admin":
            created.append(f"/v2/users/{person.zitadel_sub}")
        zitadel.ensure_user_grant(org, person.zitadel_sub, config.project_id, [person.role],
                                  None if person.role == "system_admin" else grant_id)
    return zitadel_org


# --- database --------------------------------------------------------------------------------

def insert(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar()


def undo(zitadel: Zitadel, created: list[str]) -> None:
    for path in reversed(created):
        try:
            zitadel.call("DELETE", path)
        except (RuntimeError, httpx.HTTPError) as error:
            print(f"seed-dev: could not delete {path} from ZITADEL, delete it by hand: {error}", file=sys.stderr)


def seed_database(conn, zitadel_org: str, people: list[Person], rng: random.Random) -> dict:
    now = datetime.now(UTC)
    by = {person.key: person for person in people}
    for person in people:
        person.user_id = insert(conn, "INSERT INTO users (zitadel_sub, role, org_id) VALUES (:s, :r, NULL) RETURNING user_id",
                                s=person.zitadel_sub, r=person.role) if person.role == "system_admin" else None
    sysadmin = by["sysadmin"].user_id
    org_id = insert(conn, """INSERT INTO organisations (name, kind, zitadel_org_id, registered_by)
                             VALUES (:n, 'public', :z, :by) RETURNING org_id""", n=ORG_NAME, z=zitadel_org, by=sysadmin)
    patients = {}
    for person in people:
        if person.role == "system_admin":
            continue
        person.user_id = insert(conn, "INSERT INTO users (zitadel_sub, role, org_id) VALUES (:s, :r, :o) RETURNING user_id",
                                s=person.zitadel_sub, r=person.role, o=org_id)
        if person.pseudonym:
            patients[person.key] = insert(conn, """INSERT INTO patients (user_id, org_id, pseudonym)
                                                   VALUES (:u, :o, :p) RETURNING patient_id""",
                                          u=person.user_id, o=org_id, p=person.pseudonym)
    admin = by["orgadmin"].user_id

    def device(kind: str) -> uuid.UUID:
        device_id = insert(conn, """INSERT INTO devices (device_id, type, status, is_testbed, registered_by)
                                    VALUES (:d, :t, 'active', true, :by) RETURNING device_id""",
                           d=uuid.uuid4(), t=kind, by=sysadmin)
        insert(conn, """INSERT INTO device_credentials (device_id, auth_method, key_type, credential_ref)
                        VALUES (:d, 'x509_mtls', 'ec_p256', :ref) RETURNING credential_id""",
               d=device_id, ref=secrets.token_hex(32).upper())
        insert(conn, "INSERT INTO device_grants (device_id, org_id, granted_by) VALUES (:d, :o, :by) RETURNING grant_id",
               d=device_id, o=org_id, by=sysadmin)
        return device_id

    gateway = device("fixed_gateway")
    wearables = [device("wearable") for _ in range(4)]
    conn.execute(text("UPDATE devices SET current_mode = 'fixed', last_seen = :t WHERE device_id = :d"),
                 {"t": now - timedelta(seconds=20), "d": gateway})
    # patient1: on the fixed path via the gateway; patient2: on the mobile path; patient3: no wearable
    live = [(wearables[0], "fixed", gateway, now - timedelta(seconds=40)),
            (wearables[1], "mobile", None, now - timedelta(minutes=6))]
    for wearable, mode, via, seen in live:
        conn.execute(text("UPDATE devices SET current_mode = :m, current_gateway_id = :g, last_seen = :t WHERE device_id = :d"),
                     {"m": mode, "g": via, "t": seen, "d": wearable})
    # Connectivity log (D17): the gateway was down for 20 minutes this morning and has been up since;
    # patient1's wearable joined it after, patient2's left it for the mobile path.
    for device, state, reason, minutes_ago in (
            (gateway, "online", None, 60 * 26), (wearables[1], "online", None, 60 * 25),
            (wearables[1], "offline", "mode_switch", 60 * 8), (gateway, "offline", None, 60 * 3 + 40),
            (gateway, "online", None, 60 * 3 + 20), (wearables[0], "online", None, 60 * 3 + 15)):
        insert(conn, """INSERT INTO connectivity_events (device_id, gateway_id, state, reason, at)
                        VALUES (:d, :g, :s, :r, :t) RETURNING 1""",
               d=device, g=gateway, s=state, r=reason, t=now - timedelta(minutes=minutes_ago))

    assignments = [("patient1", "doctor1"), ("patient2", "doctor1"), ("patient3", "doctor2")]
    for patient, doctor in assignments:
        insert(conn, "INSERT INTO care_assignments (patient_id, doctor_id, assigned_by) VALUES (:p, :d, :by) RETURNING 1",
               p=patients[patient], d=by[doctor].user_id, by=admin)
    for patient, disorder in (("patient1", "Premature ventricular contractions"), ("patient2", "Paroxysmal atrial fibrillation"),
                              ("patient3", "Hypertension")):
        insert(conn, "INSERT INTO patient_disorders (patient_id, disorder, recorded_by) VALUES (:p, :d, :by) RETURNING 1",
               p=patients[patient], d=disorder, by=admin)

    # (patient, wearable, path, alerts as (minutes ago, label, confidence, ectopic every n beats, bpm, acked))
    monitored = [
        ("patient1", wearables[0], "fixed", [(5, "V", 0.94, 4, 78, False), (95, "V", 0.81, 6, 74, True),
                                              (400, "N", 0.62, None, 70, True)]),
        ("patient2", wearables[1], "mobile", [(30, "S", 0.77, 5, 96, False), (720, "F", 0.58, 7, 88, False)]),
    ]
    alerts = 0
    for patient, wearable, path, events in monitored:
        patient_id = patients[patient]
        insert(conn, "INSERT INTO device_assignments (device_id, patient_id, issued_by, assigned_at) VALUES (:d, :p, :by, :t) RETURNING 1",
               d=wearable, p=patient_id, by=admin, t=now - timedelta(days=2))
        session = insert(conn, """INSERT INTO monitoring_sessions (device_id, patient_id, org_id, path, started_at)
                                  VALUES (:d, :p, :o, :path, :t) RETURNING session_id""",
                         d=wearable, p=patient_id, o=org_id, path=path, t=now - timedelta(days=2))
        for minutes_ago, label, confidence, ectopic_every, bpm, acked in events:
            start = now - timedelta(minutes=minutes_ago)
            segment = insert(conn, """INSERT INTO ecg_segments (session_id, patient_id, device_id, kind, fs_hz, started_at, ended_at)
                                      VALUES (:s, :p, :d, 'alert', :fs, :t, :e) RETURNING segment_id""",
                             s=session, p=patient_id, d=wearable, fs=FS_HZ, t=start, e=start + timedelta(seconds=SEGMENT_S))
            samples = ecg(SEGMENT_S, bpm, ectopic_every, rng)
            for second in range(SEGMENT_S):
                chunk = samples[second * FS_HZ:(second + 1) * FS_HZ]
                insert(conn, """INSERT INTO ecg_chunks (segment_id, seq, ts, n_samples, samples, attested_by, auth_method)
                                VALUES (:g, :seq, :ts, :n, :b, :by, :m) RETURNING 1""",
                       g=segment, seq=second, ts=start + timedelta(seconds=second), n=len(chunk), b=pack(chunk),
                       by=gateway if path == "fixed" else None, m="x509_mtls" if path == "fixed" else "envelope")
            insert(conn, """INSERT INTO classifications (segment_id, source, model_version, label, confidence, created_at)
                            VALUES (:g, 'wearable', 'tinydl-screen-0.1', 'abnormal', :c, :t) RETURNING 1""",
                   g=segment, c=min(0.99, confidence + 0.05), t=start + timedelta(seconds=SEGMENT_S))
            classification = insert(conn, """
                INSERT INTO classifications (segment_id, source, model_version, label, confidence, created_at)
                VALUES (:g, :src, 'aami-cnn-0.1', :l, :c, :t) RETURNING classification_id""",
                g=segment, src="gateway" if path == "fixed" else "cloud", l=label, c=confidence,
                t=start + timedelta(seconds=SEGMENT_S + 1))
            insert(conn, """INSERT INTO alerts (device_id, patient_id, classification_id, origin, created_at,
                                                acknowledged_by, acknowledged_at, gateway_id)
                            VALUES (:d, :p, :c, :origin, :t, :ab, :at, :gw) RETURNING 1""",
                   d=wearable, p=patient_id, c=classification, origin="gateway" if path == "fixed" else "cloud",
                   gw=gateway if path == "fixed" else None,
                   t=start + timedelta(seconds=SEGMENT_S + 1), ab=by["doctor1"].user_id if acked else None,
                   at=start + timedelta(minutes=12) if acked else None)
            alerts += 1

    for minutes_ago, target, mode, predicted, outcome, action, result in (
            (3, wearables[2], "ids", "dos_flood", "detected", None, None),
            (50, None, "ips", "port_scan", "blocked", "drop_source", "applied"),
            (300, wearables[0], "ids", "benign", "no_threat", None, None)):
        insert(conn, """INSERT INTO security_events (ts, gateway_id, device_id, mode, predicted_class, outcome, action, action_result)
                        VALUES (:t, :g, :d, :m, :p, :o, :a, :r) RETURNING 1""",
               t=now - timedelta(minutes=minutes_ago), g=gateway, d=target, m=mode, p=predicted, o=outcome, a=action, r=result)

    return {"org_id": str(org_id), "gateway": str(gateway), "wearables": [str(w) for w in wearables], "alerts": alerts}


def seed(settings: Settings, password: str | None = None, allow_existing: bool = False) -> dict:
    """Seeds ZITADEL and the database; returns what was created, with the shared password.
    allow_existing: also on a stack with other organisations (the stack tests share one stack)."""
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with engine.connect() as conn:
            if not allow_existing and conn.execute(text("SELECT count(*) FROM organisations")).scalar():
                raise SystemExit("the database already has organisations; seed-dev runs only on an empty stack")
        config = ZitadelConfig.load(settings.zitadel_config_file)
        token = settings.zitadel_api_token_file.read_text().strip()
        zitadel = Zitadel(settings.zitadel_url, config.issuer, token)
        # ZITADEL's default password policy needs upper and lower case, a digit and a symbol.
        password = password or f"Dev-{secrets.token_urlsafe(9)}1a!"
        people = [replace(person) for person in PEOPLE]
        in_zitadel: list[str] = []
        try:
            zitadel_org = create_zitadel_people(zitadel, config, people, password, in_zitadel)
            with engine.begin() as conn:
                created = seed_database(conn, zitadel_org, people, random.Random(1))
        except BaseException:
            undo(zitadel, in_zitadel)
            raise
    finally:
        engine.dispose()
    created["password"] = password
    created["people"] = [{"email": p.email, "role": p.role, "name": f"{p.given_name} {p.family_name}",
                          "user_id": str(p.user_id), "pseudonym": p.pseudonym} for p in people]
    return created


def describe(created: dict) -> str:
    return json.dumps(created, indent=2)
