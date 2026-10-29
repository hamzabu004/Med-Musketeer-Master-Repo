"""Message contracts (D6, D7, D15): what gateways publish and what the ingestion API accepts.

The models here are the source of shared/contracts/*.schema.json, which the firmware and gateway
work read; `python -m app.contracts` rewrites the files and a unit test fails if they differ.
Unknown fields are refused: a change to a payload is a new version (`v`).

- alert-payload-v1: a wearable's alert with its ECG segment and TinyDL screening (D6).
- status-v1: presence, of a wearable (forwarded by its gateway) or of the gateway itself.
- ids-event-v1: one detection of the gateway's IDS/IPS.
- ingest-v1: the normalised message the adapter builds around one of them (D7).
- revocation-list-v1: the other direction, what the cloud publishes to every gateway (D16).
"""
import base64
import binascii
import json
import sys
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, model_validator

MAX_SAMPLES = 65536  # about 3 minutes at 360 Hz; one alert is a few seconds


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Screening(Contract):
    label: str = Field(min_length=1, max_length=64, description="The wearable's TinyDL screening label")
    confidence: float = Field(ge=0, le=1)
    model: str = Field(min_length=1, max_length=64, description="Model name and version")


class AlertPayload(Contract):
    """alert-payload-v1, published by a wearable on mm/fixed/{device_id}/alert (D6)."""
    model_config = ConfigDict(title="alert-payload-v1")

    v: Literal[1]
    msg_id: UUID = Field(description="Makes a QoS 1 redelivery idempotent")
    seq: int = Field(ge=0, le=2**63 - 1, description="Per-device counter; shows gaps")
    type: Literal["alert"]
    fs_hz: int = Field(ge=1, le=2000, description="Sampling rate")
    lead: str = Field(min_length=1, max_length=16, examples=["MLII"])
    n_samples: int = Field(ge=1, le=MAX_SAMPLES)
    encoding: Literal["int16le-base64"]
    samples: str = Field(max_length=(MAX_SAMPLES * 2 + 2) // 3 * 4,
                         description="n_samples little-endian int16 values, Base64 with padding")
    screening: Screening
    segment_start: AwareDatetime = Field(description="Time of the first sample")
    sent_at: AwareDatetime | None = Field(None, description="Benchmark only; never used in a security decision")

    @model_validator(mode="after")
    def samples_match_count(self):
        size = len(self.decoded())
        if size != 2 * self.n_samples:
            raise ValueError(f"samples decode to {size} bytes, n_samples needs {2 * self.n_samples}")
        return self

    def decoded(self) -> bytes:
        try:
            return base64.b64decode(self.samples, validate=True)
        except binascii.Error as error:
            raise ValueError(f"samples are not Base64: {error}") from error


class StatusPayload(Contract):
    """status-v1: presence. A gateway forwards its wearables' presence on mm/fixed/{device_id}/status
    and reports its own on mm/gateway/{gateway_id}/status; the adapter also builds one from EMQX's
    connect and disconnect events for each gateway."""
    model_config = ConfigDict(title="status-v1")

    v: Literal[1]
    state: Literal["online", "offline"]
    reason: str | None = Field(None, min_length=1, max_length=64,
                               description='Why it went offline; "mode_switch" before the wearable changes path')
    revocation_version: int | None = Field(
        None, ge=0, le=2**63 - 1,
        description="A gateway's own status only: the revocation-list-v1 version it enforces (D16)")
    sent_at: AwareDatetime | None = Field(None, description="Benchmark only")


class IdsEventPayload(Contract):
    """ids-event-v1, published by a gateway on mm/gateway/{gateway_id}/ids_event."""
    model_config = ConfigDict(title="ids-event-v1")

    v: Literal[1]
    msg_id: UUID = Field(description="Makes a QoS 1 redelivery idempotent; stored as the event id")
    ts: AwareDatetime = Field(description="Time of the detection")
    device_id: UUID | None = Field(None, description="The registered device the traffic concerned, if any")
    mode: Literal["ids", "ips"]
    predicted_class: str = Field(min_length=1, max_length=64)
    outcome: str = Field(min_length=1, max_length=64)
    action: str | None = Field(None, min_length=1, max_length=64, description="IPS mode only: the mitigation applied")
    action_result: str | None = Field(None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def only_ips_acts(self):
        if self.mode == "ids" and (self.action is not None or self.action_result is not None):
            raise ValueError("IDS mode detects and logs only; action and action_result are for IPS mode")
        return self


class RevokedDevice(Contract):
    device_id: UUID
    status: Literal["suspended", "revoked"]
    since: AwareDatetime = Field(description="When the wearable got this status")


class RevokedCertificate(Contract):
    device_id: UUID = Field(description="An active wearable that holds another, valid certificate")
    fingerprint: str = Field(pattern=r"^[0-9A-F]{64}$", description="SHA-256 of the certificate, upper-case hex")
    not_after: AwareDatetime | None = Field(description="Dropped from the list once expired; null: no expiry recorded")


class RevocationList(Contract):
    """revocation-list-v1 (D16): the wearables every gateway must refuse. Retained on
    mm/revocations/wearables, published only by the cloud. Always the full list; a gateway keeps a
    list only if its version is newer than the one it holds."""
    model_config = ConfigDict(title="revocation-list-v1")

    v: Literal[1]
    version: int = Field(ge=1, le=2**63 - 1, description="Goes up with every change to the list")
    issued_at: AwareDatetime
    devices: list[RevokedDevice] = Field(description="Suspended or revoked wearables")
    certificates: list[RevokedCertificate] = Field(
        description="Revoked, unexpired certificates of wearables that are not on `devices`")


# What each kind of device may send, and the payload contract of each message type.
MESSAGES: dict[str, dict[str, type[Contract]]] = {
    "wearable": {"alert": AlertPayload, "status": StatusPayload},
    "fixed_gateway": {"status": StatusPayload, "ids_event": IdsEventPayload},
}


class Hops(Contract):
    sent_at: AwareDatetime | None = None
    broker_at: AwareDatetime
    adapter_at: AwareDatetime


class Ingest(Contract):
    """ingest-v1 (D7): the only message the ingestion API accepts. A new protocol means a new
    adapter producing it."""
    model_config = ConfigDict(title="ingest-v1")

    device_id: UUID = Field(description="The device the message is about: the wearable, or the gateway itself")
    device_type: Literal["wearable", "fixed_gateway"]
    auth_method: Literal["x509_mtls", "ecdh_envelope"]
    attested_by: UUID | None = Field(description="The gateway the broker says published it (D1); null on the mobile path")
    authenticated: bool
    auth_metadata: dict[str, Any] = Field(default_factory=dict, description="Benchmark and debugging only")
    msg_type: Literal["alert", "status", "ids_event"]
    received_at: AwareDatetime = Field(description="When the cloud received it (the broker's time on the fixed path)")
    hops: Hops
    payload: dict[str, Any] = Field(description="One of the payload contracts, by msg_type")
    _message: Contract = PrivateAttr()

    @model_validator(mode="after")
    def payload_matches_type(self):
        contract = MESSAGES[self.device_type].get(self.msg_type)
        if contract is None:
            raise ValueError(f"a {self.device_type} does not send {self.msg_type}")
        try:
            self._message = contract.model_validate(self.payload)
        except ValidationError as error:
            raise ValueError(f"payload: {describe(error)}") from None
        return self

    @property
    def message(self) -> Contract:
        return self._message


def describe(error: ValidationError) -> str:
    """One line per problem, for logs: `field.path: message`."""
    def line(item: dict) -> str:
        message = item["msg"].removeprefix("Value error, ")
        return f"{'.'.join(str(part) for part in item['loc'])}: {message}" if item["loc"] else message
    return "; ".join(line(item) for item in error.errors(include_url=False))


# --- the shared schema files -------------------------------------------------------------------

PAYLOADS = {"alert-payload-v1": AlertPayload, "status-v1": StatusPayload, "ids-event-v1": IdsEventPayload}


def schemas() -> dict[str, dict]:
    files = {name: model.model_json_schema()
             for name, model in {**PAYLOADS, "ingest-v1": Ingest, "revocation-list-v1": RevocationList}.items()}
    files["ingest-v1"]["properties"]["payload"] = {
        "description": "alert-payload-v1 (msg_type alert), status-v1 (status) or ids-event-v1 (ids_event)",
        "anyOf": [{"$ref": f"{name}.schema.json"} for name in PAYLOADS],
    }
    return {name: {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"{name}.schema.json", **schema}
            for name, schema in files.items()}


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2) + "\n"


def schema_dir() -> Path:
    """shared/contracts/ of the repository (the API image has only the package)."""
    return Path(__file__).resolve().parents[3] / "shared" / "contracts"


def write(directory: Path) -> None:
    for name, schema in schemas().items():
        (directory / f"{name}.schema.json").write_text(render(schema))


if __name__ == "__main__":
    write(Path(sys.argv[1]) if len(sys.argv) > 1 else schema_dir())
