from __future__ import annotations

import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .audit import append_event
from .config import Settings, ensure_layout
from .errors import MMCAError, SafetyError
from .files import write_json_private, write_private, write_public
from .profiles import (KEY_TYPES, build_ca_certificate, build_leaf_certificate,
                       cert_fingerprint, make_key, random_serial, validate_device_id)

REPLACE_PHRASE = "REPLACE MEDMUSKETEER CA"


def _load_ca(settings: Settings, passphrase: str):
    key_path = settings.ca_dir / "ca.key"
    cert_path = settings.ca_dir / "ca.crt"
    if not key_path.is_file() or not cert_path.is_file():
        raise MMCAError("CA not initialized; run `mmca init-ca` first")
    if key_path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SafetyError("CA private-key permissions are too open; expected mode 600")
    try:
        key = serialization.load_pem_private_key(key_path.read_bytes(), passphrase.encode())
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    except (ValueError, TypeError) as exc:
        raise SafetyError("Unable to unlock or parse the CA material; check the passphrase") from exc
    if key.public_key().public_numbers() != cert.public_key().public_numbers():
        raise SafetyError("CA private key does not match ca.crt")
    return key, cert


def _serials(path: Path) -> set[int]:
    if not path.exists():
        return set()
    values = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(line)
            values.add(int(record["serial"], 16))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SafetyError(f"Invalid serial database record at line {line_no}") from exc
    return values


def _unique_serial(settings: Settings) -> int:
    used = _serials(settings.serial_db)
    for _ in range(10):
        serial = random_serial()
        if serial not in used:
            return serial
    raise SafetyError("Unable to allocate a unique certificate serial number")


def _record_serial(settings: Settings, serial: int, device_id: str | None, profile: str) -> None:
    settings.ca_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(settings.serial_db, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"serial": f"{serial:032X}", "device_id": device_id,
                                 "profile": profile, "issued_at": datetime.now(timezone.utc).isoformat()}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def init_ca(settings: Settings, cn: str, validity_days: int, passphrase: str,
            *, replace_existing: bool = False) -> str:
    if not cn or validity_days < 1:
        raise MMCAError("CA common name and positive validity are required")
    ensure_layout(settings)
    key_path = settings.ca_dir / "ca.key"
    cert_path = settings.ca_dir / "ca.crt"
    if key_path.exists() or cert_path.exists():
        if not replace_existing:
            raise SafetyError("A CA already exists; use `mmca replace-ca` with the confirmation phrase")
        if not key_path.exists() or not cert_path.exists():
            raise SafetyError("Existing CA is incomplete; inspect it before replacement")
        archive = settings.ca_dir / "archive" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive.mkdir(mode=0o700, parents=True, exist_ok=False)
        shutil.copy2(key_path, archive / "ca.key")
        shutil.copy2(cert_path, archive / "ca.crt")
        os.chmod(archive / "ca.key", 0o600)
        os.chmod(archive / "ca.crt", 0o644)
    key = ec.generate_private_key(ec.SECP256R1())
    serial = _unique_serial(settings)
    cert = build_ca_certificate(key, cn, validity_days, serial)
    key_data = key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(passphrase.encode()))
    cert_data = cert.public_bytes(serialization.Encoding.PEM)
    write_private(key_path, key_data, replace=replace_existing)
    write_public(cert_path, cert_data, replace=replace_existing)
    _record_serial(settings, serial, None, "ca")
    fingerprint = cert_fingerprint(cert)
    append_event(settings.audit_path, "replace_ca" if replace_existing else "init_ca",
                 fingerprint=fingerprint)
    return fingerprint


def cert_preview(profile: str, device_id: str, key_type: str, validity_days: int) -> dict:
    if profile not in {"wearable", "gateway"}:
        raise MMCAError(f"Unknown certificate profile: {profile}")
    if key_type not in KEY_TYPES:
        raise MMCAError(f"Unsupported TLS key type: {key_type}")
    device_id = validate_device_id(device_id)
    sans = [device_id]
    eku = ["clientAuth"]
    if profile == "gateway":
        sans.insert(0, "gateway.medmusketeer.local")
        eku = ["serverAuth", "clientAuth"]
    return {"profile": profile, "cn": device_id, "san": sans, "eku": eku,
            "key_type": key_type, "validity_days": validity_days}


def issue_device(settings: Settings, profile: str, device_id: str, key_type: str,
                 validity_days: int, passphrase: str, *, confirm) -> tuple[str, Path]:
    if validity_days < 1:
        raise MMCAError("Certificate validity must be positive")
    preview = cert_preview(profile, device_id, key_type, validity_days)
    device_id = preview["cn"]
    output_dir = settings.issued_dir / device_id
    previous_meta = None
    reissue = False
    if output_dir.exists():
        try:
            previous_meta = json.loads((output_dir / "meta.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SafetyError(f"Existing issuance record for {device_id} is unreadable") from exc
        if (profile != "wearable" or previous_meta.get("profile") != "wearable"
                or not previous_meta.get("flashed") or (output_dir / "device.key").exists()):
            raise SafetyError(f"Issued directory already exists for {device_id}; refusing to overwrite")
        reissue = True
    if not confirm(preview):
        raise MMCAError("Issuance cancelled")
    ca_key, ca_cert = _load_ca(settings, passphrase)
    leaf_key = make_key(key_type)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, device_id)])
    ).sign(leaf_key, hashes.SHA256())
    serial = _unique_serial(settings)
    cert = build_leaf_certificate(csr, ca_cert, ca_key, device_id, profile,
                                  key_type, validity_days, serial)
    key_data = leaf_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    cert_data = cert.public_bytes(serialization.Encoding.PEM)
    archive_dir = None
    if reissue:
        old_serial = str(previous_meta.get("serial", "unknown"))
        archive_dir = output_dir / "history" / old_serial
        archive_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        os.replace(output_dir / "device.crt", archive_dir / "device.crt")
        os.replace(output_dir / "meta.json", archive_dir / "meta.json")
    else:
        output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        write_private(output_dir / "device.key", key_data)
        write_public(output_dir / "device.crt", cert_data)
        write_json_private(output_dir / "meta.json", {
            **preview, "serial": f"{serial:032X}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "fingerprint_sha256": cert_fingerprint(cert), "flashed": False,
            "reissued_from": previous_meta.get("serial") if reissue else None,
        })
        _record_serial(settings, serial, device_id, profile)
    except Exception:
        for name in ("device.key", "device.crt", "meta.json"):
            (output_dir / name).unlink(missing_ok=True)
        if reissue and archive_dir:
            os.replace(archive_dir / "device.crt", output_dir / "device.crt")
            os.replace(archive_dir / "meta.json", output_dir / "meta.json")
        else:
            shutil.rmtree(output_dir, ignore_errors=True)
        raise
    fingerprint = cert_fingerprint(cert)
    append_event(settings.audit_path, "issue", device_id=device_id, fingerprint=fingerprint)
    return fingerprint, output_dir


def validate_gateway_material(settings: Settings, device_id: str) -> tuple[Path, Path, Path, x509.Certificate]:
    device_id = validate_device_id(device_id)
    path = settings.issued_dir / device_id
    try:
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        if (path / "device.key").stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise SafetyError("Gateway private-key permissions are too open; expected mode 600")
        key_data = (path / "device.key").read_bytes()
        cert = x509.load_pem_x509_certificate((path / "device.crt").read_bytes())
        ca = x509.load_pem_x509_certificate((settings.ca_dir / "ca.crt").read_bytes())
        key = serialization.load_pem_private_key(key_data, password=None)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MMCAError(f"Cannot load gateway material for {device_id}") from exc
    if meta.get("profile") != "gateway":
        raise SafetyError(f"{device_id} is not an issued gateway")
    if key.public_key().public_numbers() != cert.public_key().public_numbers():
        raise SafetyError("Gateway private key does not match its certificate")
    if cert.issuer != ca.subject:
        raise SafetyError("Gateway certificate does not chain to the configured CA")
    now = datetime.now(timezone.utc)
    if cert.not_valid_after_utc <= now or cert.not_valid_before_utc > now:
        raise SafetyError("Gateway certificate is not currently valid")
    if ca.not_valid_after_utc <= now or ca.not_valid_before_utc > now:
        raise SafetyError("CA certificate is not currently valid")
    try:
        cert.verify_directly_issued_by(ca)
    except Exception as exc:
        raise SafetyError("Gateway certificate signature verification failed") from exc
    try:
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    except x509.ExtensionNotFound as exc:
        raise SafetyError("Gateway certificate is missing required extensions") from exc
    if "gateway.medmusketeer.local" not in sans.get_values_for_type(x509.DNSName):
        raise SafetyError("Gateway certificate is missing the role SAN")
    common_names = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    if not common_names or common_names[0].value != device_id:
        raise SafetyError("Gateway certificate CN does not match the requested device_id")
    if device_id not in sans.get_values_for_type(x509.DNSName):
        raise SafetyError("Gateway certificate is missing its device_id SAN")
    if x509.oid.ExtendedKeyUsageOID.SERVER_AUTH not in eku or x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH not in eku:
        raise SafetyError("Gateway certificate must allow serverAuth and clientAuth")
    return path / "device.key", path / "device.crt", settings.ca_dir / "ca.crt", cert
