"""Settings, from a TOML file (deploy/uplink.toml.example documents every key)."""
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    cloud_host: str
    cloud_port: int
    cloud_name: str  # the name the cloud's certificate must carry, whatever address is used
    ca_file: Path
    cert_file: Path
    key_file: Path
    state_file: Path  # the last revocation list received
    acl_file: Path  # the wearable listener's ACL file, generated from the list
    mosquitto_pid_file: Path
    reload_command: tuple[str, ...] | None  # replaces SIGHUP to the PID in mosquitto_pid_file
    retry_s: float

    @classmethod
    def load(cls, path: Path) -> "Config":
        data = tomllib.loads(path.read_text())
        cloud, tls, revocation = data["cloud"], data["tls"], data["revocation"]
        reload_command = revocation.get("reload_command")
        return cls(
            cloud_host=cloud["host"],
            cloud_port=int(cloud.get("port", 8883)),
            cloud_name=cloud.get("name", "cloud.medmusketeer.local"),
            ca_file=Path(tls["ca"]),
            cert_file=Path(tls["cert"]),
            key_file=Path(tls["key"]),
            state_file=Path(revocation.get("state_file", "/var/lib/medmusketeer/revocations.json")),
            acl_file=Path(revocation.get("acl_file", "/var/lib/medmusketeer/wearables.acl")),
            mosquitto_pid_file=Path(revocation.get("mosquitto_pid_file", "/run/mosquitto/mosquitto.pid")),
            reload_command=tuple(reload_command) if reload_command else None,
            retry_s=float(revocation.get("retry_s", 30)),
        )
