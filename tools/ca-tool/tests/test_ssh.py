import uuid
import re
import shlex

import paramiko
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from mmca.core.ca import init_ca, issue_device, validate_gateway_material
from mmca.core.config import ensure_layout
from mmca.core.errors import SafetyError
from mmca.core.ssh import _ApprovalPolicy, deploy_gateway, host_fingerprint

PASSPHRASE = "local-test-ca-passphrase"


def gateway(settings):
    ensure_layout(settings)
    init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    device_id = str(uuid.uuid4())
    issue_device(settings, "gateway", device_id, "ec_p256", 365, PASSPHRASE,
                 confirm=lambda _preview: True)
    return device_id


def test_gateway_material_preflight_checks_role_san_and_key_match(settings):
    device_id = gateway(settings)
    key_path, cert_path, ca_path, cert = validate_gateway_material(settings, device_id)
    assert key_path.exists() and cert_path.exists() and ca_path.exists()
    assert "gateway.medmusketeer.local" in cert.extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)


def test_host_fingerprint_and_explicit_new_host_approval(tmp_path):
    key = paramiko.RSAKey.generate(2048)
    expected = host_fingerprint(key)
    assert expected.startswith("SHA256:")
    known_hosts = tmp_path / "ssh" / "known_hosts"
    client = paramiko.SSHClient()
    policy = _ApprovalPolicy(input_fn=lambda _prompt: "y", output_fn=lambda *_: None,
                             known_hosts=known_hosts)
    policy.missing_host_key(client, "gateway.local", key)
    assert known_hosts.exists()
    loaded = paramiko.HostKeys(str(known_hosts))
    assert loaded.lookup("gateway.local")[key.get_name()] == key


def test_new_host_rejection_does_not_save_key(tmp_path):
    key = paramiko.RSAKey.generate(2048)
    known_hosts = tmp_path / "known_hosts"
    policy = _ApprovalPolicy(input_fn=lambda _prompt: "n", output_fn=lambda *_: None,
                             known_hosts=known_hosts)
    with pytest.raises(SafetyError, match="not approved"):
        policy.missing_host_key(paramiko.SSHClient(), "gateway.local", key)
    assert not known_hosts.exists()


class _FakeChannel:
    def __init__(self, code):
        self.code = code

    def recv_exit_status(self):
        return self.code


class _FakeStream:
    def __init__(self, data, code=0):
        self.data = data.encode()
        self.channel = _FakeChannel(code)

    def read(self):
        return self.data


class _FakeStdin:
    def write(self, _value):
        pass

    def flush(self):
        pass


class _FakeSFTP:
    def __init__(self, client):
        self.client = client

    def mkdir(self, path, mode=0o777):
        self.client.directories.add(path)

    def chmod(self, _path, _mode):
        pass

    def put(self, local, remote):
        self.client.files[remote] = open(local, "rb").read()

    def close(self):
        pass


class _FakeSSHClient:
    instances = []
    initial_files = {}

    def __init__(self, server_key=None):
        self.server_key = server_key or paramiko.RSAKey.generate(2048)
        self.host_keys = paramiko.HostKeys()
        self.policy = None
        self.files = dict(self.initial_files)
        self.directories = set()
        self.instances.append(self)

    def load_host_keys(self, path):
        if __import__("pathlib").Path(path).exists():
            self.host_keys = paramiko.HostKeys(path)

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def get_host_keys(self):
        return self.host_keys

    def save_host_keys(self, path):
        self.host_keys.save(path)

    def connect(self, host, port=22, **_kwargs):
        hostname = host if port == 22 else f"[{host}]:{port}"
        known = self.host_keys.lookup(hostname)
        if known:
            expected = known[self.server_key.get_name()]
            if expected != self.server_key:
                raise paramiko.BadHostKeyException(hostname, self.server_key, expected)
        else:
            self.policy.missing_host_key(self, hostname, self.server_key)

    def exec_command(self, command, **_kwargs):
        script = shlex.split(command)[-1]
        if "if [ ! -f" in script:
            match = re.search(r"-f\s+('([^']+)'|(\S+))", script)
            path = match.group(2) or match.group(3)
            data = self.files.get(path)
            if data is None:
                return _FakeStdin(), _FakeStream("" , 3), _FakeStream("")
            if path.endswith(".key"):
                key = serialization.load_pem_private_key(data, password=None)
                public_der = key.public_key().public_bytes(serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo)
            else:
                cert = x509.load_pem_x509_certificate(data)
                public_der = cert.public_bytes(serialization.Encoding.DER)
            digest = hashes.Hash(hashes.SHA256())
            digest.update(public_der)
            return _FakeStdin(), _FakeStream(digest.finalize().hex() + "  -\n"), _FakeStream("")
        for fragment in script.split(" && "):
            parts = shlex.split(fragment)
            if parts[:2] == ["install", "-d"]:
                continue
            if parts[:2] == ["cp", "-p"]:
                self.files[parts[3]] = self.files[parts[2]]
            elif parts[:1] == ["install"] and "0640" in parts:
                self.files[parts[-1]] = self.files[parts[-2]]
            elif parts[:2] == ["rm", "-rf"]:
                prefix = parts[2].rstrip("/") + "/"
                for path in list(self.files):
                    if path.startswith(prefix):
                        del self.files[path]
            elif parts[:2] == ["systemctl", "restart"]:
                continue
            elif parts[:2] == ["systemctl", "is-active"]:
                return _FakeStdin(), _FakeStream("active\n"), _FakeStream("")
        return _FakeStdin(), _FakeStream(""), _FakeStream("")

    def open_sftp(self):
        return _FakeSFTP(self)

    def close(self):
        pass


def test_deploy_approves_new_host_uploads_and_verifies_gateway_files(settings, monkeypatch, tmp_path):
    device_id = gateway(settings)
    Fake = _FakeSSHClient
    Fake.instances.clear()
    Fake.initial_files = {}
    monkeypatch.setattr("mmca.core.ssh.paramiko.SSHClient", lambda: Fake())
    answers = iter(["y"])
    result = deploy_gateway(settings, device_id, "gateway.local", restart=True,
        input_fn=lambda _prompt: next(answers), password_fn=lambda _prompt: "sudo-secret",
        output_fn=lambda *_: None, known_hosts=tmp_path / "known_hosts")
    assert result["restarted"] is True
    client = Fake.instances[-1]
    assert set(client.files) >= {
        "/etc/mosquitto/certs/ca.crt", "/etc/mosquitto/certs/gateway.crt",
        "/etc/mosquitto/certs/gateway.key"}
    assert "/tmp/" not in " ".join(client.files)
    assert (tmp_path / "known_hosts").exists()


def test_deploy_stops_on_known_host_key_mismatch(settings, monkeypatch, tmp_path):
    device_id = gateway(settings)
    known_hosts = tmp_path / "known_hosts"
    hosts = paramiko.HostKeys()
    hosts.add("gateway.local", "ssh-rsa", paramiko.RSAKey.generate(2048))
    hosts.save(str(known_hosts))
    Fake = _FakeSSHClient
    Fake.instances.clear()
    Fake.initial_files = {}
    monkeypatch.setattr("mmca.core.ssh.paramiko.SSHClient", lambda: Fake())
    with pytest.raises(SafetyError, match="host key mismatch"):
        deploy_gateway(settings, device_id, "gateway.local", input_fn=lambda _prompt: "y",
            password_fn=lambda _prompt: "sudo-secret", output_fn=lambda *_: None,
            known_hosts=known_hosts)
    assert Fake.instances[-1].files == {}


def test_deploy_requires_confirmation_before_remote_overwrite(settings, monkeypatch, tmp_path):
    device_id = gateway(settings)
    directory = settings.issued_dir / device_id
    old_files = {
        "/etc/mosquitto/certs/ca.crt": (settings.ca_dir / "ca.crt").read_bytes(),
        "/etc/mosquitto/certs/gateway.crt": (directory / "device.crt").read_bytes(),
        "/etc/mosquitto/certs/gateway.key": (directory / "device.key").read_bytes(),
    }
    Fake = _FakeSSHClient
    Fake.instances.clear()
    Fake.initial_files = old_files
    monkeypatch.setattr("mmca.core.ssh.paramiko.SSHClient", lambda: Fake())
    answers = iter(["y", "n"])
    with pytest.raises(Exception, match="cancelled"):
        deploy_gateway(settings, device_id, "gateway.local", input_fn=lambda _prompt: next(answers),
            password_fn=lambda _prompt: "sudo-secret", output_fn=lambda *_: None,
            known_hosts=tmp_path / "known_hosts")
    client = Fake.instances[-1]
    assert set(client.files) == set(old_files)
    assert all(client.files[path] == data for path, data in old_files.items())


def test_deploy_backs_up_confirmed_existing_files(settings, monkeypatch, tmp_path):
    device_id = gateway(settings)
    directory = settings.issued_dir / device_id
    old_files = {
        "/etc/mosquitto/certs/ca.crt": (settings.ca_dir / "ca.crt").read_bytes(),
        "/etc/mosquitto/certs/gateway.crt": (directory / "device.crt").read_bytes(),
        "/etc/mosquitto/certs/gateway.key": (directory / "device.key").read_bytes(),
    }
    Fake = _FakeSSHClient
    Fake.instances.clear()
    Fake.initial_files = old_files
    monkeypatch.setattr("mmca.core.ssh.paramiko.SSHClient", lambda: Fake())
    answers = iter(["y", "y"])
    deploy_gateway(settings, device_id, "gateway.local",
        input_fn=lambda _prompt: next(answers), password_fn=lambda _prompt: "sudo-secret",
        output_fn=lambda *_: None, known_hosts=tmp_path / "known_hosts")
    client = Fake.instances[-1]
    for old_path, old_data in old_files.items():
        backup_paths = [path for path in client.files if path.startswith(old_path + ".bak.")]
        assert len(backup_paths) == 1
        assert client.files[backup_paths[0]] == old_data
