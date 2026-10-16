from __future__ import annotations

import base64
import getpass
import hashlib
import shlex
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import paramiko
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from .audit import append_event
from .ca import validate_gateway_material
from .config import Settings
from .errors import MMCAError, SafetyError
from .profiles import cert_fingerprint, validate_device_id


def host_fingerprint(key: paramiko.PKey) -> str:
    digest = hashlib.sha256(base64.b64decode(key.get_base64())).digest()
    import base64 as b64
    return "SHA256:" + b64.b64encode(digest).decode("ascii").rstrip("=")


class _ApprovalPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, *, input_fn=input, output_fn=print, known_hosts: Path):
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.known_hosts = known_hosts

    def missing_host_key(self, client, hostname, key):
        fingerprint = host_fingerprint(key)
        self.output_fn(f"Unknown SSH host key for {hostname}: {fingerprint}")
        answer = self.input_fn("Trust this host key and save it to known_hosts? [y/N] ").strip().lower()
        if answer != "y":
            raise SafetyError("Unknown SSH host was not approved")
        client.get_host_keys().add(hostname, key.get_name(), key)
        self.known_hosts.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        client.save_host_keys(str(self.known_hosts))


def _remote(client: paramiko.SSHClient, command: str, *, sudo_password: str | None = None,
            timeout: int = 30) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, get_pty=False, timeout=timeout)
    if sudo_password is not None:
        stdin.write(sudo_password + "\n")
        stdin.flush()
        # EOF prevents sudo from waiting forever for another password after a
        # rejected attempt. The command itself does not need stdin afterward.
        stdin_channel = getattr(stdin, "channel", None)
        if stdin_channel is not None:
            stdin_channel.shutdown_write()

    channel = stdout.channel
    if not all(hasattr(channel, method) for method in
               ("recv_ready", "recv_stderr_ready", "recv", "recv_stderr", "exit_status_ready")):
        # Small adapters and test doubles may expose only the basic stream API.
        exit_code = channel.recv_exit_status()
        return (exit_code, stdout.read().decode("utf-8", errors="replace"),
                stderr.read().decode("utf-8", errors="replace"))

    output = bytearray()
    errors = bytearray()
    deadline = time.monotonic() + timeout
    while True:
        try:
            while channel.recv_ready():
                output.extend(channel.recv(32768))
            while channel.recv_stderr_ready():
                errors.extend(channel.recv_stderr(32768))
            if channel.exit_status_ready():
                # Drain any data that arrived with the exit status before
                # collecting it. Reading both streams avoids SSH channel-window
                # backpressure while the remote command is running.
                while channel.recv_ready():
                    output.extend(channel.recv(32768))
                while channel.recv_stderr_ready():
                    errors.extend(channel.recv_stderr(32768))
                exit_code = channel.recv_exit_status()
                return (exit_code, output.decode("utf-8", errors="replace"),
                        errors.decode("utf-8", errors="replace"))
        except (OSError, paramiko.SSHException) as exc:
            channel.close()
            raise MMCAError("SSH remote command failed while reading its response") from exc

        if time.monotonic() >= deadline:
            channel.close()
            raise MMCAError("SSH remote command timed out; check sudo access and the broker connection")
        time.sleep(0.02)


def _sudo(client: paramiko.SSHClient, command: str, password: str, *, timeout: int = 30) -> tuple[int, str, str]:
    return _remote(client, "sudo -S -p '' sh -c " + shlex.quote(command),
                   sudo_password=password, timeout=timeout)


def _fingerprint_remote(client: paramiko.SSHClient, path: str, password: str) -> str:
    quoted = shlex.quote(path)
    script = (
        f"if [ ! -f {quoted} ]; then exit 3; fi; "
        f"case {quoted} in *.key) openssl pkey -in {quoted} -pubout -outform DER 2>/dev/null | openssl dgst -sha256 -r;; "
        f"*) openssl x509 -in {quoted} -outform DER 2>/dev/null | openssl dgst -sha256 -r;; esac"
    )
    code, out, err = _sudo(client, script, password)
    if code == 3:
        return ""
    if code:
        raise MMCAError(f"Unable to inspect remote file {path}: {err.strip() or 'remote command failed'}")
    return out.strip().split()[0] if out.strip() else ""


def _local_key_fingerprint(key_path: Path) -> str:
    try:
        private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        public_der = private_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return hashlib.sha256(public_der).hexdigest()
    except (OSError, ValueError, TypeError) as exc:
        raise MMCAError("Unable to calculate the gateway key fingerprint") from exc


def _validate_host(host: str) -> str:
    if not host or any(char.isspace() or ord(char) < 0x20 for char in host) or any(c in host for c in "@/\\"):
        raise SafetyError("SSH host must be a hostname or IP address without userinfo or a URL")
    return host


def _deploy_gateway(settings: Settings, device_id: str, host: str, *, port: int = 22,
                   username: str = "pi", remote_cert_dir: str = "/etc/mosquitto/certs",
                   restart: bool = False, input_fn=input, password_fn=getpass.getpass,
                   output_fn=print, known_hosts: Path | None = None) -> dict:
    device_id = validate_device_id(device_id)
    host = _validate_host(host)
    if not 1 <= port <= 65535:
        raise SafetyError("SSH port must be between 1 and 65535")
    key_path, cert_path, ca_path, cert = validate_gateway_material(settings, device_id)
    remote_cert_dir = remote_cert_dir.rstrip("/") or "/"
    cert_fp = cert_fingerprint(cert)
    ca_cert_data = ca_path.read_bytes()
    known_hosts = (known_hosts or Path.home() / ".ssh" / "known_hosts").expanduser()
    client = paramiko.SSHClient()
    try:
        if known_hosts.exists():
            client.load_host_keys(str(known_hosts))
        client.set_missing_host_key_policy(_ApprovalPolicy(input_fn=input_fn, output_fn=output_fn,
                                                           known_hosts=known_hosts))
        try:
            client.connect(host, port=port, username=username, look_for_keys=True,
                           allow_agent=True, timeout=15, banner_timeout=15, auth_timeout=20)
        except paramiko.AuthenticationException:
            ssh_password = password_fn("SSH password: ")
            client.connect(host, port=port, username=username, password=ssh_password,
                           look_for_keys=False, allow_agent=False, timeout=15,
                           banner_timeout=15, auth_timeout=20)
        sudo_password = password_fn("Sudo password: ")
        remote_paths = {"ca.crt": remote_cert_dir + "/ca.crt",
                        "gateway.crt": remote_cert_dir + "/gateway.crt",
                        "gateway.key": remote_cert_dir + "/gateway.key"}
        existing: dict[str, str] = {}
        for name, remote_path in remote_paths.items():
            existing[name] = _fingerprint_remote(client, remote_path, sudo_password)
        present = {name: fp for name, fp in existing.items() if fp}
        if present:
            output_fn("Existing remote files:")
            for name, fingerprint in present.items():
                output_fn(f"  {name}: {fingerprint}")
            if input_fn("Back up and overwrite these files? [y/N] ").strip().lower() != "y":
                raise MMCAError("Gateway deployment cancelled")
        temp_dir = "/tmp/mmca-" + uuid.uuid4().hex
        try:
            sftp = client.open_sftp()
            try:
                sftp.mkdir(temp_dir, mode=0o700)
                sftp.chmod(temp_dir, 0o700)
                sftp.put(str(ca_path), temp_dir + "/ca.crt")
                sftp.put(str(cert_path), temp_dir + "/gateway.crt")
                sftp.put(str(key_path), temp_dir + "/gateway.key")
                for name in ("ca.crt", "gateway.crt", "gateway.key"):
                    sftp.chmod(temp_dir + "/" + name, 0o600)
            finally:
                sftp.close()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
            commands = [f"install -d -o root -g mosquitto -m 0750 {shlex.quote(remote_cert_dir)}"]
            for name, old_fp in existing.items():
                destination = remote_paths[name]
                if old_fp:
                    commands.append(f"cp -p {shlex.quote(destination)} {shlex.quote(destination + '.bak.' + timestamp)}")
                commands.append(f"install -o root -g mosquitto -m 0640 {shlex.quote(temp_dir + '/' + name)} {shlex.quote(destination)}")
            code, _out, err = _sudo(client, " && ".join(commands), sudo_password, timeout=60)
            if code:
                raise MMCAError(f"Gateway install failed: {err.strip() or 'remote install command failed'}")
        finally:
            # Best-effort cleanup also covers failed installs; never print remote command input.
            try:
                _sudo(client, f"rm -rf {shlex.quote(temp_dir)}", sudo_password, timeout=15)
            except Exception:
                pass
        expected = {
            "ca.crt": x509.load_pem_x509_certificate(ca_cert_data).fingerprint(hashes.SHA256()).hex(),
            "gateway.crt": cert.fingerprint(hashes.SHA256()).hex(),
            "gateway.key": _local_key_fingerprint(key_path),
        }
        for name, remote_path in remote_paths.items():
            actual = _fingerprint_remote(client, remote_path, sudo_password)
            if actual.lower() != expected[name].lower():
                raise SafetyError(f"Remote verification failed for {name}")
        if restart:
            code, out, err = _sudo(client, "systemctl restart mosquitto && systemctl is-active mosquitto",
                                   sudo_password, timeout=45)
            if code or out.strip().splitlines()[-1:] != ["active"]:
                raise MMCAError(f"Mosquitto restart did not become active: {err.strip() or out.strip()}")
        append_event(settings.audit_path, "deploy", device_id=device_id,
                     fingerprint=cert_fp, details={"host": host,
                     "files": ["ca.crt", "gateway.crt", "gateway.key"]})
        return {"host": host, "device_id": device_id, "fingerprint": cert_fp,
                "restarted": restart}
    except paramiko.BadHostKeyException as exc:
        raise SafetyError(f"SSH host key mismatch for {host}; refusing connection") from exc
    except (paramiko.SSHException, OSError) as exc:
        raise MMCAError(f"SSH deployment failed for {host}: {exc}") from exc
    finally:
        client.close()


def deploy_gateway(settings: Settings, device_id: str, host: str, *, port: int = 22,
                   username: str = "pi", remote_cert_dir: str = "/etc/mosquitto/certs",
                   restart: bool = False, input_fn=input, password_fn=getpass.getpass,
                   output_fn=print, known_hosts: Path | None = None) -> dict:
    try:
        return _deploy_gateway(settings, device_id, host, port=port, username=username,
            remote_cert_dir=remote_cert_dir, restart=restart, input_fn=input_fn,
            password_fn=password_fn, output_fn=output_fn, known_hosts=known_hosts)
    except Exception as exc:
        try:
            append_event(settings.audit_path, "deploy", device_id=device_id,
                         result="failed", details={"host": host, "reason": type(exc).__name__})
        except Exception:
            pass
        raise


def _erase_gateway_credentials(settings: Settings, device_id: str, host: str, *, port: int = 22,
                                username: str = "pi", remote_cert_dir: str = "/etc/mosquitto/certs",
                                input_fn=input, password_fn=getpass.getpass, output_fn=print,
                                known_hosts: Path | None = None) -> dict:
    device_id = validate_device_id(device_id)
    host = _validate_host(host)
    if not 1 <= port <= 65535:
        raise SafetyError("SSH port must be between 1 and 65535")
    validate_gateway_material(settings, device_id)
    remote_cert_dir = remote_cert_dir.rstrip("/")
    if (not remote_cert_dir.startswith("/") or not remote_cert_dir
            or any(ord(char) < 0x20 for char in remote_cert_dir)):
        raise SafetyError("Remote certificate directory must be an absolute path")

    known_hosts = (known_hosts or Path.home() / ".ssh" / "known_hosts").expanduser()
    client = paramiko.SSHClient()
    files_expr = "\\( -name 'ca.crt' -o -name 'gateway.crt' -o -name 'gateway.key' " \
                 "-o -name 'ca.crt.bak.*' -o -name 'gateway.crt.bak.*' " \
                 "-o -name 'gateway.key.bak.*' \\)"
    quoted_dir = shlex.quote(remote_cert_dir)
    find_files = f"find {quoted_dir} -maxdepth 1 \\( -type f -o -type l \\) {files_expr} -print"
    try:
        if known_hosts.exists():
            client.load_host_keys(str(known_hosts))
        client.set_missing_host_key_policy(_ApprovalPolicy(input_fn=input_fn, output_fn=output_fn,
                                                           known_hosts=known_hosts))
        try:
            client.connect(host, port=port, username=username, look_for_keys=True,
                           allow_agent=True, timeout=15, banner_timeout=15, auth_timeout=20)
        except paramiko.AuthenticationException:
            ssh_password = password_fn("SSH password: ")
            client.connect(host, port=port, username=username, password=ssh_password,
                           look_for_keys=False, allow_agent=False, timeout=15,
                           banner_timeout=15, auth_timeout=20)

        sudo_password = password_fn("Sudo password: ")
        code, output, err = _sudo(client, f"test -d {quoted_dir} || exit 4; {find_files}", sudo_password)
        if code == 4:
            raise MMCAError(f"Remote certificate directory does not exist: {remote_cert_dir}")
        if code:
            raise MMCAError(f"Unable to inspect remote certificate directory: {err.strip() or 'remote command failed'}")
        files = [line.strip() for line in output.splitlines() if line.strip()]
        if not files:
            raise MMCAError(f"No gateway TLS credential files found in {remote_cert_dir}")

        output_fn(f"Gateway: {host}")
        output_fn("TLS files and deployment backups to erase:")
        for path in files:
            output_fn(f"  {Path(path).name}")
        output_fn("Mosquitto will be stopped if it is running. Its config, ACLs, and password file will remain.")
        if input_fn("Type ERASE GATEWAY TLS CREDENTIALS to continue: ").strip() != "ERASE GATEWAY TLS CREDENTIALS":
            raise MMCAError("Gateway credential erasure cancelled")

        erase_script = (
            "set -eu; "
            "if systemctl is-active --quiet mosquitto; then systemctl stop mosquitto; fi; "
            f"find {quoted_dir} -maxdepth 1 \\( -type f -o -type l \\) {files_expr} -delete; "
            f"remaining=$(find {quoted_dir} -maxdepth 1 \\( -type f -o -type l \\) {files_expr} -print -quit); "
            "[ -z \"$remaining\" ]"
        )
        code, _out, err = _sudo(client, erase_script, sudo_password, timeout=60)
        if code:
            raise MMCAError(f"Gateway credential erasure failed: {err.strip() or 'remote command failed'}")

        removed_names = [Path(path).name for path in files]
        append_event(settings.audit_path, "erase_gateway", device_id=device_id,
                     details={"host": host, "files": removed_names})
        return {"host": host, "device_id": device_id, "files": removed_names}
    except paramiko.BadHostKeyException as exc:
        raise SafetyError(f"SSH host key mismatch for {host}; refusing connection") from exc
    except (paramiko.SSHException, OSError) as exc:
        raise MMCAError(f"SSH credential erasure failed for {host}: {exc}") from exc
    finally:
        client.close()


def erase_gateway_credentials(settings: Settings, device_id: str, host: str, *, port: int = 22,
                              username: str = "pi", remote_cert_dir: str = "/etc/mosquitto/certs",
                              input_fn=input, password_fn=getpass.getpass, output_fn=print,
                              known_hosts: Path | None = None) -> dict:
    try:
        return _erase_gateway_credentials(settings, device_id, host, port=port,
            username=username, remote_cert_dir=remote_cert_dir, input_fn=input_fn,
            password_fn=password_fn, output_fn=output_fn, known_hosts=known_hosts)
    except Exception as exc:
        try:
            append_event(settings.audit_path, "erase_gateway", device_id=device_id,
                         result="failed", details={"host": host, "reason": type(exc).__name__})
        except Exception:
            pass
        raise
