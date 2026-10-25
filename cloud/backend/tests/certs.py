"""Test helper: certificates issued by the real CA tool (tools/ca-tool, `mmca`), as the custodian
would issue them, for the broker hook and EMQX tests."""
import base64
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

CA_TOOL = Path(__file__).resolve().parents[3] / "tools" / "ca-tool"
if str(CA_TOOL) not in sys.path:
    sys.path.insert(0, str(CA_TOOL))

from mmca.core.ca import init_ca, issue_cloud, issue_device  # noqa: E402
from mmca.core.config import ensure_layout, load_settings  # noqa: E402

PASSPHRASE = "test-ca-passphrase"


@dataclass(frozen=True)
class Issued:
    device_id: str
    cert: Path
    key: Path

    @property
    def fingerprint(self) -> str:
        return x509.load_pem_x509_certificate(self.cert.read_bytes()).fingerprint(hashes.SHA256()).hex().upper()

    @property
    def emqx_cert_pem(self) -> str:
        """The certificate as EMQX renders ${cert_pem}: Base64 DER, no PEM armour."""
        der = x509.load_pem_x509_certificate(self.cert.read_bytes()).public_bytes(serialization.Encoding.DER)
        return base64.b64encode(der).decode()


class TestCA:
    __test__ = False  # not a pytest class

    def __init__(self, root: Path):
        self.settings = load_settings(root)
        ensure_layout(self.settings)
        init_ca(self.settings, "MedMusketeer CA", 3650, PASSPHRASE)
        self.root = root
        self.ca_cert = self.settings.ca_dir / "ca.crt"

    def issue(self, profile: str, device_id: str | None = None) -> Issued:
        """A wearable or gateway certificate; a second one for the same device_id is put in a
        separate CA-tool root, as mmca keeps one live certificate per device."""
        device_id = device_id or str(uuid.uuid4())
        settings = self.settings
        if (settings.issued_dir / device_id).exists():
            settings = load_settings(self.root / "extra" / uuid.uuid4().hex)
            ensure_layout(settings)
            settings.ca_dir.mkdir(parents=True, exist_ok=True)
            for name in ("ca.key", "ca.crt"):
                (settings.ca_dir / name).write_bytes((self.settings.ca_dir / name).read_bytes())
                (settings.ca_dir / name).chmod(0o600)
        _fp, output = issue_device(settings, profile, device_id, "ec_p256", 365, PASSPHRASE,
                                   confirm=lambda _preview: True)
        return Issued(device_id, output / "device.crt", output / "device.key")

    def issue_cloud(self) -> Issued:
        _fp, output = issue_cloud(self.settings, 365, PASSPHRASE, confirm=lambda _preview: True)
        return Issued("cloud.medmusketeer.local", output / "server.crt", output / "server.key")
