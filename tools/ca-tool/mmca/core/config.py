from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import MMCAError


@dataclass(frozen=True)
class Settings:
    root: Path
    ca_dir: Path
    issued_dir: Path
    cloud_dir: Path
    audit_path: Path
    serial_db: Path
    default_key_type: str = "ec_p256"
    ca_validity_days: int = 3650
    leaf_validity_days: int = 365
    creds_partition_name: str = "creds"
    app_nvs_partition_name: str = "nvs"
    gateway_host: str = ""
    gateway_port: int = 22
    gateway_user: str = "pi"
    remote_cert_dir: str = "/etc/mosquitto/certs"


def load_settings(root: Path | None = None) -> Settings:
    base = (root or Path.home() / "medmusketeer-ca").expanduser().resolve()
    config_file = base / "config.toml"
    values: dict = {}
    if config_file.exists():
        try:
            with config_file.open("rb") as stream:
                values = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise MMCAError(f"Cannot read config file {config_file}: {exc}") from exc
    paths = values.get("paths", {})
    defaults = values.get("defaults", {})
    esp = values.get("esp", {})
    gateway = values.get("gateway_ssh", {})
    configured_root = Path(paths.get("ca_dir", str(base))).expanduser()
    if root is not None:
        configured_root = base
    else:
        base = configured_root.resolve()
    return Settings(
        root=base,
        ca_dir=base / "ca",
        issued_dir=base / "issued",
        cloud_dir=base / "cloud",
        audit_path=base / "audit.log.jsonl",
        serial_db=base / "ca" / "serial_db",
        default_key_type=defaults.get("tls_key_type", "ec_p256"),
        ca_validity_days=int(defaults.get("ca_validity_days", 3650)),
        leaf_validity_days=int(defaults.get("leaf_validity_days", 365)),
        creds_partition_name=esp.get("creds_partition_name", "creds"),
        app_nvs_partition_name=esp.get("app_nvs_partition_name", "nvs"),
        gateway_host=gateway.get("host", ""),
        gateway_port=int(gateway.get("port", 22)),
        gateway_user=gateway.get("user", "pi"),
        remote_cert_dir=gateway.get("remote_cert_dir", "/etc/mosquitto/certs"),
    )


def ensure_layout(settings: Settings) -> None:
    settings.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(settings.root, 0o700)
    settings.ca_dir.mkdir(mode=0o700, exist_ok=True)
    settings.issued_dir.mkdir(mode=0o700, exist_ok=True)
    config_path = settings.root / "config.toml"
    if not config_path.exists():
        config_path.write_text(
            "[paths]\nca_dir = \"~/medmusketeer-ca\"\n\n"
            "[defaults]\ntls_key_type = \"ec_p256\"\nca_validity_days = 3650\n"
            "leaf_validity_days = 365\n\n[esp]\ncreds_partition_name = \"creds\"\n"
            "app_nvs_partition_name = \"nvs\"\n\n"
            "[gateway_ssh]\nhost = \"\"\nport = 22\nuser = \"pi\"\n"
            "remote_cert_dir = \"/etc/mosquitto/certs\"\n",
            encoding="utf-8",
        )
        os.chmod(config_path, 0o600)
