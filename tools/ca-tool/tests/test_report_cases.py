"""Test cases traced to the FYP-1 mid report (TC-P01, TC-P02, TC-A01 to TC-A06, TC-A09).

Cases already covered by test_ca.py, test_flash.py, and test_ssh.py are not repeated here;
see docs/testing/test_traceability.md for the full mapping.
"""
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from mmca.cli import main
from mmca.core.ca import _load_ca, init_ca, issue_device, validate_gateway_material
from mmca.core.config import ensure_layout, load_settings
from mmca.core.errors import SafetyError
from mmca.core.flash import _lookup_nvs_partition, parse_partition_table
from mmca.core.profiles import cert_fingerprint
from mmca.core.ssh import deploy_gateway

from test_flash import run_mocked_flash
from test_ssh import _FakeSSHClient

PASSPHRASE = "local-test-ca-passphrase"
SUDO_PASSWORD = "sudo-test-password"
ROLE_NAME = "gateway.medmusketeer.local"
REPO_ROOT = Path(__file__).resolve().parents[3]
PARTITIONS_CSV = REPO_ROOT / "firmware" / "wearable" / "partitions.csv"


def _openssl(*args):
    return subprocess.run(["openssl", *args], capture_output=True, text=True)


needs_openssl = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")


def _run_cli(monkeypatch, root, args, answers):
    feed = iter(answers)
    monkeypatch.setattr("mmca.cli.getpass.getpass", lambda _prompt: next(feed))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(feed))
    return main(["--root", str(root), *args])


def _issue(settings, profile, key_type="ec_p256", device_id=None):
    device_id = device_id or str(uuid.uuid4())
    _fingerprint, output = issue_device(settings, profile, device_id, key_type, 365,
                                        PASSPHRASE, confirm=lambda _preview: True)
    return device_id, output


@pytest.fixture
def ca(settings):
    ensure_layout(settings)
    init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    return settings


def test_tc_p01_cli_creates_ca_in_designated_location(tmp_path, monkeypatch, capsys):
    root = tmp_path / "mmca"
    assert _run_cli(monkeypatch, root, ["init-ca"], [PASSPHRASE, PASSPHRASE]) == 0
    key_path, cert_path = root / "ca" / "ca.key", root / "ca" / "ca.crt"
    assert key_path.is_file() and cert_path.is_file()
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert cert_path.stat().st_mode & 0o777 == 0o644
    assert b"ENCRYPTED PRIVATE KEY" in key_path.read_bytes()
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    assert cert_fingerprint(cert) in capsys.readouterr().out


@needs_openssl
@pytest.mark.parametrize("profile, purpose", [("wearable", "sslclient"), ("gateway", "sslserver")])
def test_tc_p02_cli_issued_certificate_verifies_against_ca(tmp_path, monkeypatch, profile, purpose):
    root = tmp_path / "mmca"
    assert _run_cli(monkeypatch, root, ["init-ca"], [PASSPHRASE, PASSPHRASE]) == 0
    device_id = str(uuid.uuid4())
    assert _run_cli(monkeypatch, root, ["issue", profile, "--device-id", device_id],
                    ["y", PASSPHRASE]) == 0
    result = _openssl("verify", "-CAfile", str(root / "ca" / "ca.crt"), "-purpose", purpose,
                      str(root / "issued" / device_id / "device.crt"))
    assert result.returncode == 0, result.stderr
    assert ": OK" in result.stdout


@pytest.mark.parametrize("key_type", ["ec_p256", "rsa_2048"])
def test_tc_a01_leaf_profiles_match_design(ca, key_type):
    _ca_key, ca_cert = _load_ca(ca, PASSPHRASE)
    for profile in ("wearable", "gateway"):
        device_id, output = _issue(ca, profile, key_type)
        cert = x509.load_pem_x509_certificate((output / "device.crt").read_bytes())
        constraints = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert constraints.critical and constraints.value.ca is False
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage)
        assert usage.critical and usage.value.digital_signature
        assert not usage.value.key_cert_sign and not usage.value.crl_sign
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        expected_sans = {device_id, ROLE_NAME} if profile == "gateway" else {device_id}
        assert set(sans.get_values_for_type(x509.DNSName)) == expected_sans
        assert cert.issuer == ca_cert.subject
        assert (cert.not_valid_after_utc - cert.not_valid_before_utc).days == 365
    ca_usage = ca_cert.extensions.get_extension_for_class(x509.KeyUsage)
    assert ca_usage.critical
    ca_constraints = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints)
    assert ca_constraints.critical and ca_constraints.value.path_length == 0


@needs_openssl
def test_tc_a02_chain_verification_and_foreign_ca_rejection(ca, tmp_path):
    _device_id, wearable = _issue(ca, "wearable")
    _gateway_id, gateway = _issue(ca, "gateway")
    ca_file = str(ca.ca_dir / "ca.crt")
    ok = _openssl("verify", "-CAfile", ca_file, "-purpose", "sslclient", str(wearable / "device.crt"))
    assert ok.returncode == 0, ok.stderr
    ok = _openssl("verify", "-CAfile", ca_file, "-purpose", "sslserver",
                  "-verify_hostname", ROLE_NAME, str(gateway / "device.crt"))
    assert ok.returncode == 0, ok.stderr
    # The wearable profile has no serverAuth EKU, so it cannot pose as the gateway.
    bad = _openssl("verify", "-CAfile", ca_file, "-purpose", "sslserver", str(wearable / "device.crt"))
    assert bad.returncode != 0
    # A leaf from an unrelated CA does not chain to this CA.
    foreign = load_settings(tmp_path / "foreign-ca")
    ensure_layout(foreign)
    init_ca(foreign, "MedMusketeer CA", 3650, PASSPHRASE)
    _foreign_id, foreign_leaf = _issue(foreign, "wearable")
    bad = _openssl("verify", "-CAfile", ca_file, str(foreign_leaf / "device.crt"))
    assert bad.returncode != 0


def test_tc_a03_mismatched_gateway_key_is_rejected_by_preflight(ca):
    device_id, output = _issue(ca, "gateway")
    validate_gateway_material(ca, device_id)
    other = ec.generate_private_key(ec.SECP256R1()).private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    (output / "device.key").write_bytes(other)
    os.chmod(output / "device.key", 0o600)
    with pytest.raises(SafetyError, match="does not match"):
        validate_gateway_material(ca, device_id)


def test_tc_a03_gateway_key_with_open_permissions_is_rejected(ca):
    device_id, output = _issue(ca, "gateway")
    os.chmod(output / "device.key", 0o644)
    with pytest.raises(SafetyError, match="permissions"):
        validate_gateway_material(ca, device_id)


def test_tc_a04_many_certificates_have_unique_recorded_serials(ca):
    count = 50
    serials = []
    for index in range(count):
        _device_id, output = _issue(ca, "wearable" if index % 2 else "gateway")
        serials.append(x509.load_pem_x509_certificate((output / "device.crt").read_bytes()).serial_number)
    assert len(set(serials)) == count
    records = [json.loads(line) for line in ca.serial_db.read_text().splitlines()]
    recorded = {int(record["serial"], 16) for record in records if record["profile"] != "ca"}
    assert recorded == set(serials)
    assert len(records) == count + 1


def _gen_esp32part():
    candidates = [Path(os.environ.get("IDF_PATH", "")), Path.home() / "esp" / "esp-idf"]
    for base in candidates:
        tool = base / "components" / "partition_table" / "gen_esp32part.py"
        if tool.is_file():
            return tool
    return None


@pytest.mark.skipif(_gen_esp32part() is None or not PARTITIONS_CSV.is_file(),
                    reason="ESP-IDF gen_esp32part.py or firmware partitions.csv not available")
def test_tc_a06_parses_binary_built_from_firmware_partitions_csv(tmp_path):
    binary = tmp_path / "partition-table.bin"
    subprocess.run([sys.executable, str(_gen_esp32part()), "-q", str(PARTITIONS_CSV), str(binary)],
                   check=True)
    table = binary.read_bytes()
    creds = _lookup_nvs_partition(table, "creds")
    assert (creds.offset, creds.size) == (0x1D0000, 0x30000)
    nvs = _lookup_nvs_partition(table, "nvs")
    assert (nvs.offset, nvs.size) == (0x9000, 0x6000)
    names = [partition.name for partition in parse_partition_table(table)]
    assert names == ["nvs", "phy_init", "factory", "creds"]


@pytest.mark.skipif(_gen_esp32part() is None, reason="ESP-IDF gen_esp32part.py not available")
def test_tc_a06_default_single_app_table_is_rejected(tmp_path):
    csv = tmp_path / "single_app.csv"
    csv.write_text("nvs,data,nvs,0x9000,0x6000,\nphy_init,data,phy,0xf000,0x1000,\n"
                   "factory,app,factory,0x10000,1M,\n")
    binary = tmp_path / "single_app.bin"
    subprocess.run([sys.executable, str(_gen_esp32part()), "-q", str(csv), str(binary)], check=True)
    with pytest.raises(SafetyError, match="No `creds` partition"):
        _lookup_nvs_partition(binary.read_bytes(), "creds")


def test_tc_a10_audit_log_after_issue_flash_deploy_has_every_action_and_no_secret(
        ca, monkeypatch, tmp_path):
    wearable_id, wearable_dir = _issue(ca, "wearable")
    wearable_key = (wearable_dir / "device.key").read_text()
    run_mocked_flash(monkeypatch, ca, wearable_id)
    gateway_id, gateway_dir = _issue(ca, "gateway")
    gateway_key = (gateway_dir / "device.key").read_text()
    _FakeSSHClient.instances.clear()
    _FakeSSHClient.initial_files = {}
    monkeypatch.setattr("mmca.core.ssh.paramiko.SSHClient", lambda: _FakeSSHClient())
    deploy_gateway(ca, gateway_id, "gateway.local", restart=True,
                   input_fn=lambda _prompt: "y", password_fn=lambda _prompt: SUDO_PASSWORD,
                   output_fn=lambda *_: None, known_hosts=tmp_path / "known_hosts")

    log = ca.audit_path.read_text()
    events = [json.loads(line) for line in log.splitlines()]
    assert [(event["action"], event["result"]) for event in events] == [
        ("init_ca", "success"), ("issue", "success"), ("flash", "success"),
        ("issue", "success"), ("deploy", "success")]
    assert {event["device_id"] for event in events[1:]} == {wearable_id, gateway_id}
    assert PASSPHRASE not in log and SUDO_PASSWORD not in log
    assert "PRIVATE KEY" not in log and "BEGIN" not in log
    for pem in (wearable_key, gateway_key, (ca.ca_dir / "ca.key").read_text()):
        body = "".join(line for line in pem.splitlines() if not line.startswith("-----"))
        assert body[:40] not in log
    assert ca.audit_path.stat().st_mode & 0o777 == 0o600
