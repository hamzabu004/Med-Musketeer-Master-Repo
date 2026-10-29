"""The wearable revocation list as the gateway keeps it (cloud-backend.md D16).

The cloud publishes the full list, retained, on mm/revocations/wearables. The gateway keeps the
last valid list it received in `state_file`, loads it at start before anything else, and so keeps
enforcing it while the cloud is unreachable. A list is accepted only if:
- it is valid revocation-list-v1 (the shared schema, shipped with this package);
- every device id is a canonical UUID, because the ids are written into Mosquitto's ACL file;
- its version is newer than the one held, so a delayed duplicate cannot undo a newer list.
"""
import json
import logging
import uuid
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from mm_uplink import files

log = logging.getLogger(__name__)

TOPIC = "mm/revocations/wearables"
_SCHEMA = json.loads(resources.files("mm_uplink").joinpath("schemas/revocation-list-v1.schema.json").read_text())
_VALIDATOR = Draft202012Validator(_SCHEMA)


class Invalid(ValueError):
    pass


def is_device_id(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


def parse(payload: bytes | str) -> dict:
    """A revocation-list-v1 document, or Invalid with the reason."""
    try:
        listing = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as error:
        raise Invalid(f"not JSON: {error}") from None
    errors = sorted(_VALIDATOR.iter_errors(listing), key=lambda e: list(e.path))
    if errors:
        raise Invalid("; ".join(f"{'.'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors[:5]))
    ids = [entry["device_id"] for entry in listing["devices"] + listing["certificates"]]
    if not all(is_device_id(device_id) for device_id in ids):
        raise Invalid("a device_id is not a canonical (lower-case) UUID")
    return listing


class RevocationStore:
    def __init__(self, path: Path):
        self.path = path
        self.current: dict | None = self._load()

    def _load(self) -> dict | None:
        if not self.path.exists():
            log.warning("no revocation list stored yet (%s): no wearable is refused until one arrives", self.path)
            return None
        try:
            listing = parse(self.path.read_bytes())
        except Invalid as error:
            # Should not happen (written atomically, only after validation); refusing to start would
            # stop monitoring, so carry on and take the cloud's next list.
            log.error("stored revocation list %s is unusable (%s): ignoring it", self.path, error)
            return None
        log.info("revocation list version %s loaded: %s wearables listed", listing["version"], len(listing["devices"]))
        return listing

    @property
    def version(self) -> int | None:
        return self.current["version"] if self.current else None

    def offer(self, payload: bytes | str) -> dict | None:
        """Keeps the list if it is valid and newer; returns it, or None if it was ignored."""
        try:
            listing = parse(payload)
        except Invalid as error:
            log.warning("revocation list ignored: %s", error)
            return None
        if self.version is not None and listing["version"] <= self.version:
            log.debug("revocation list version %s ignored: holding %s", listing["version"], self.version)
            return None
        files.replace(self.path, json.dumps(listing, indent=1) + "\n")
        self.current = listing
        log.info("revocation list version %s stored: %s wearables, %s certificates",
                 listing["version"], len(listing["devices"]), len(listing["certificates"]))
        return listing

    def listed(self, device_id: str) -> bool:
        """Whether messages from this wearable must be dropped (the services layer, D16)."""
        return self.current is not None and any(d["device_id"] == device_id for d in self.current["devices"])
