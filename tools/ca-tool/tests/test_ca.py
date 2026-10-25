import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID

from mmca.core.audit import append_event, read_events
from mmca.core.ca import _load_ca, cert_preview, init_ca, issue_device
from mmca.core.config import ensure_layout
from mmca.core.errors import MMCAError, SafetyError
from mmca.core.profiles import cert_fingerprint


PASSPHRASE = "local-test-ca-passphrase"


def issue(settings, profile="wearable", key_type="ec_p256", device_id=None):
    ensure_layout(settings)
    init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    device_id = device_id or str(uuid.uuid4())
    return issue_device(settings, profile, device_id, key_type, 365, PASSPHRASE,
                        confirm=lambda _preview: True)


def test_ca_and_leaf_profiles_and_encrypted_ca_key(settings):
    ensure_layout(settings)
    fingerprint = init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    assert len(fingerprint) == 64
    key_data = (settings.ca_dir / "ca.key").read_bytes()
    assert b"ENCRYPTED" in key_data
    assert (settings.ca_dir / "ca.key").stat().st_mode & 0o777 == 0o600
    with pytest.raises(SafetyError, match="already exists"):
        init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    with pytest.raises(SafetyError, match="passphrase"):
        _load_ca(settings, "incorrect")
    ca_key, ca_cert = _load_ca(settings, PASSPHRASE)
    assert ca_key.public_key().public_numbers() == ca_cert.public_key().public_numbers()
    ca_constraints = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert ca_constraints.ca and ca_constraints.path_length == 0
    ca_usage = ca_cert.extensions.get_extension_for_class(x509.KeyUsage).value
    assert ca_usage.key_cert_sign and ca_usage.crl_sign

    device_id = str(uuid.uuid4())
    _fingerprint, output = issue_device(settings, "wearable", device_id, "ec_p256", 365,
        PASSPHRASE, confirm=lambda _preview: True)
    cert = x509.load_pem_x509_certificate((output / "device.crt").read_bytes())
    assert cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value == device_id
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert sans.get_values_for_type(x509.DNSName) == [device_id]
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert list(eku) == [ExtendedKeyUsageOID.CLIENT_AUTH]
    assert cert.issuer == ca_cert.subject
    cert.verify_directly_issued_by(ca_cert)
    private_key = serialization.load_pem_private_key((output / "device.key").read_bytes(), None)
    assert private_key.public_key().public_numbers() == cert.public_key().public_numbers()
    assert (output / "device.key").stat().st_mode & 0o777 == 0o600
    assert json.loads((output / "meta.json").read_text())["flashed"] is False


@pytest.mark.parametrize("key_type", ["ec_p256", "rsa_2048"])
def test_gateway_profile_includes_role_san_and_both_ekus(settings, key_type):
    _fingerprint, output = issue(settings, profile="gateway", key_type=key_type)
    cert = x509.load_pem_x509_certificate((output / "device.crt").read_bytes())
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "gateway.medmusketeer.local" in sans.get_values_for_type(x509.DNSName)
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert set(eku) == {ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH}
    assert cert_fingerprint(cert) == json.loads((output / "meta.json").read_text())["fingerprint_sha256"]


def test_serials_are_unique_and_device_ids_are_uuid4(settings):
    first_fp, first = issue(settings)
    second_id = str(uuid.uuid4())
    second_fp, second = issue_device(settings, "wearable", second_id, "ec_p256", 365,
                                     PASSPHRASE, confirm=lambda _preview: True)
    one = x509.load_pem_x509_certificate((first / "device.crt").read_bytes())
    two = x509.load_pem_x509_certificate((second / "device.crt").read_bytes())
    assert one.serial_number != two.serial_number
    assert first_fp != second_fp
    with pytest.raises(MMCAError, match="UUIDv4"):
        cert_preview("wearable", "not-a-uuid", "ec_p256", 365)


def test_replacement_archives_old_encrypted_key(settings):
    ensure_layout(settings)
    old_fingerprint = init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    new_fingerprint = init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE,
                               replace_existing=True)
    assert old_fingerprint != new_fingerprint
    archives = list((settings.ca_dir / "archive").iterdir())
    assert len(archives) == 1
    assert (archives[0] / "ca.key").read_bytes() != (settings.ca_dir / "ca.key").read_bytes()
    assert (archives[0] / "ca.key").stat().st_mode & 0o777 == 0o600


def test_successfully_flashed_wearable_can_be_reissued_for_same_device_id(settings):
    device_id = str(uuid.uuid4())
    _fingerprint, output = issue(settings, device_id=device_id)
    first_cert = (output / "device.crt").read_bytes()
    first_meta = json.loads((output / "meta.json").read_text())
    (output / "device.key").unlink()
    first_meta["flashed"] = True
    (output / "meta.json").write_text(json.dumps(first_meta), encoding="utf-8")
    _next_fingerprint, next_output = issue_device(settings, "wearable", device_id,
        "rsa_2048", 365, PASSPHRASE, confirm=lambda _preview: True)
    assert next_output == output
    assert (output / "device.key").exists()
    next_meta = json.loads((output / "meta.json").read_text())
    assert next_meta["flashed"] is False
    assert next_meta["key_type"] == "rsa_2048"
    archived_cert = output / "history" / first_meta["serial"] / "device.crt"
    assert archived_cert.read_bytes() == first_cert


def test_audit_whitelists_details_and_never_records_secret_values(settings):
    append_event(settings.audit_path, "deploy", device_id="dev", details={
        "host": "gateway.local", "password": "do-not-log", "files": ["ca.crt"]})
    record = read_events(settings.audit_path)[0]
    assert record["details"] == {"host": "gateway.local", "files": ["ca.crt"]}
    assert "do-not-log" not in settings.audit_path.read_text()
    assert settings.audit_path.stat().st_mode & 0o777 == 0o600


# --- cloud server certificate (Iteration 3, Slice 4) -------------------------------------------

def issue_cloud_cert(settings, **kwargs):
    from mmca.core.ca import issue_cloud
    return issue_cloud(settings, 365, PASSPHRASE, confirm=lambda _preview: True, **kwargs)


def test_cloud_profile_is_a_server_certificate_for_the_pinned_name(settings):
    import subprocess
    from cryptography.hazmat.primitives.asymmetric import ec
    from mmca.core.profiles import CLOUD_NAME

    ensure_layout(settings)
    init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    fingerprint, output = issue_cloud_cert(settings)
    cert = x509.load_pem_x509_certificate((output / "server.crt").read_bytes())
    assert CLOUD_NAME == "cloud.medmusketeer.local"
    assert cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value == CLOUD_NAME
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert sans.get_values_for_type(x509.DNSName) == [CLOUD_NAME]
    assert list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) == [ExtendedKeyUsageOID.SERVER_AUTH]
    usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    assert usage.digital_signature and not usage.key_encipherment and not usage.key_cert_sign
    assert isinstance(cert.public_key(), ec.EllipticCurvePublicKey) and cert.public_key().curve.name == "secp256r1"
    _key, ca_cert = _load_ca(settings, PASSPHRASE)
    cert.verify_directly_issued_by(ca_cert)
    key = serialization.load_pem_private_key((output / "server.key").read_bytes(), None)
    assert key.public_key().public_numbers() == cert.public_key().public_numbers()
    assert (output / "server.key").stat().st_mode & 0o777 == 0o600
    meta = json.loads((output / "meta.json").read_text())
    assert meta["fingerprint_sha256"] == fingerprint and meta["profile"] == "cloud"
    assert [event["action"] for event in read_events(settings.audit_path)][-1] == "issue_cloud"
    # As a TLS client would check it: chain, server purpose, and the pinned host name.
    verify = subprocess.run(["openssl", "verify", "-CAfile", str(settings.ca_dir / "ca.crt"), "-purpose", "sslserver",
                             "-verify_hostname", CLOUD_NAME, str(output / "server.crt")], capture_output=True, text=True)
    assert verify.returncode == 0, verify.stderr
    wrong = subprocess.run(["openssl", "verify", "-CAfile", str(settings.ca_dir / "ca.crt"),
                            "-verify_hostname", "gateway.medmusketeer.local", str(output / "server.crt")],
                           capture_output=True, text=True)
    assert wrong.returncode != 0


def test_cloud_certificate_is_replaced_only_on_request(settings):
    ensure_layout(settings)
    init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    _fp, output = issue_cloud_cert(settings)
    first_serial = json.loads((output / "meta.json").read_text())["serial"]
    with pytest.raises(SafetyError, match="already exists"):
        issue_cloud_cert(settings)
    _fp, output = issue_cloud_cert(settings, replace=True)
    meta = json.loads((output / "meta.json").read_text())
    assert meta["serial"] != first_serial and meta["replaced"] == first_serial
    history = output / "history" / first_serial
    assert sorted(p.name for p in history.iterdir()) == ["meta.json", "server.crt"]  # the old key is removed


def test_cloud_certificate_rejects_other_key_types_and_names(settings):
    from mmca.core.ca import cloud_preview
    from mmca.core.profiles import build_leaf_certificate

    with pytest.raises(MMCAError, match="ec_p256"):
        cloud_preview("rsa_2048", 365)
    ensure_layout(settings)
    init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    ca_key, ca_cert = _load_ca(settings, PASSPHRASE)
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "evil.example")])).sign(key, hashes.SHA256())
    with pytest.raises(MMCAError, match="cloud certificate is issued for"):
        build_leaf_certificate(csr, ca_cert, ca_key, "evil.example", "cloud", "ec_p256", 365, 7)


@pytest.mark.parametrize("profile", ["wearable", "gateway", "cloud"])
def test_certificates_carry_key_identifiers_and_pass_strict_verification(settings, profile, tmp_path):
    # Python 3.13+ create_default_context() sets VERIFY_X509_STRICT, which requires an Authority Key
    # Identifier on leaves and a Subject Key Identifier on the CA (found in Iteration 3, Slice 4).
    import ssl
    import subprocess
    if profile == "cloud":
        ensure_layout(settings)
        init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
        _fp, output = issue_cloud_cert(settings)
        cert_path = output / "server.crt"
    else:
        _fp, output = issue(settings, profile=profile)
        cert_path = output / "device.crt"
    ca_cert = x509.load_pem_x509_certificate((settings.ca_dir / "ca.crt").read_bytes())
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    ca_ski = ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
    aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
    assert aki.key_identifier == ca_ski.digest
    assert cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    verify = subprocess.run(["openssl", "verify", "-x509_strict", "-CAfile", str(settings.ca_dir / "ca.crt"),
                             str(cert_path)], capture_output=True, text=True)
    assert verify.returncode == 0, verify.stderr
    assert ssl.create_default_context().verify_flags & ssl.VERIFY_X509_STRICT
