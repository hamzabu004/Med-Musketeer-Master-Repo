from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .errors import MMCAError

KEY_TYPES = {"ec_p256", "rsa_2048"}


def validate_device_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise MMCAError("device_id must be a UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise MMCAError("device_id must be a canonical UUIDv4")
    return str(parsed)


def make_key(key_type: str):
    if key_type == "ec_p256":
        return ec.generate_private_key(ec.SECP256R1())
    if key_type == "rsa_2048":
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)
    raise MMCAError(f"Unsupported TLS key type: {key_type}")


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def build_ca_certificate(private_key, cn: str, validity_days: int, serial: int) -> x509.Certificate:
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(_name(cn))
        .issuer_name(_name(cn))
        .public_key(private_key.public_key())
        .serial_number(serial)
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=validity_days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False,
            key_cert_sign=True, crl_sign=True, encipher_only=None, decipher_only=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )


def build_leaf_certificate(csr: x509.CertificateSigningRequest, ca_cert: x509.Certificate,
                           ca_key, device_id: str, profile: str, key_type: str,
                           validity_days: int, serial: int) -> x509.Certificate:
    del key_type  # Kept in the signature to make the profile preview explicit.
    now = datetime.now(timezone.utc)
    subject = _name(device_id)
    sans = [x509.DNSName(device_id)]
    if profile == "gateway":
        sans.append(x509.DNSName("gateway.medmusketeer.local"))
        eku = [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]
        usage = x509.KeyUsage(digital_signature=True, content_commitment=False,
            key_encipherment=True, data_encipherment=False, key_agreement=False,
            key_cert_sign=False, crl_sign=False, encipher_only=None, decipher_only=None)
    elif profile == "wearable":
        eku = [ExtendedKeyUsageOID.CLIENT_AUTH]
        usage = x509.KeyUsage(digital_signature=True, content_commitment=False,
            key_encipherment=True, data_encipherment=False, key_agreement=False,
            key_cert_sign=False, crl_sign=False, encipher_only=None, decipher_only=None)
    else:
        raise MMCAError(f"Unknown certificate profile: {profile}")
    if csr.subject != subject:
        raise MMCAError("CSR subject does not match the requested device_id")
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(serial)
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=validity_days))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(usage, critical=True)
        .add_extension(x509.ExtendedKeyUsage(eku), critical=False)
        .sign(ca_key, hashes.SHA256())
    )


def random_serial() -> int:
    import secrets
    return secrets.randbits(128) | 1


def cert_fingerprint(certificate: x509.Certificate) -> str:
    return certificate.fingerprint(hashes.SHA256()).hex().upper()
