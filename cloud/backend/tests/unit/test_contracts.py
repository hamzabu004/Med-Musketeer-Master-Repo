"""TC-C23 (payload half) at the contracts: what the adapter and the API refuse before touching the
database, and the shared schema files staying in step with the models."""
import json
import uuid

import pytest
from pydantic import ValidationError

from app import contracts
from app.contracts import AlertPayload, IdsEventPayload, Ingest, StatusPayload
from tests.messages import alert_payload, encode, ids_payload, ingest, status_payload


def test_the_shared_schema_files_match_the_models():
    for name, schema in contracts.schemas().items():
        path = contracts.schema_dir() / f"{name}.schema.json"
        assert path.read_text() == contracts.render(schema), f"{path} is stale: run python -m app.contracts"


def test_ingest_v1_refers_to_each_payload_schema():
    payload = contracts.schemas()["ingest-v1"]["properties"]["payload"]
    assert [ref["$ref"] for ref in payload["anyOf"]] == [
        "alert-payload-v1.schema.json", "status-v1.schema.json", "ids-event-v1.schema.json"]


def test_valid_payloads_parse():
    alert = AlertPayload.model_validate(alert_payload(n_samples=4))
    assert len(alert.decoded()) == 8
    assert StatusPayload.model_validate(status_payload("offline", reason="mode_switch")).reason == "mode_switch"
    assert IdsEventPayload.model_validate(ids_payload(mode="ids", action=None, action_result=None)).mode == "ids"


ALERT_FAULTS = {
    "samples shorter than n_samples": {"n_samples": 5, "samples": encode([1, 2, 3, 4])},
    "samples not Base64": {"n_samples": 2, "samples": "!!!!"},
    "another version": {"v": 2},
    "an unknown field": {"patient": "P-1001"},
    "no screening": {"screening": None},
    "confidence above 1": {"screening": {"label": "abnormal", "confidence": 1.5, "model": "m"}},
    "zero sampling rate": {"fs_hz": 0},
    "a time without zone": {"segment_start": "2026-11-02T10:15:03"},
    "msg_id not a UUID": {"msg_id": "42"},
    "negative seq": {"seq": -1},
    "another encoding": {"encoding": "int16be-base64"},
}


@pytest.mark.parametrize("fault", ALERT_FAULTS, ids=list(ALERT_FAULTS))
def test_tc_c23_malformed_alert_payloads_are_refused(fault):
    with pytest.raises(ValidationError):
        AlertPayload.model_validate({**alert_payload(n_samples=4), **ALERT_FAULTS[fault]})


def test_ids_mode_does_not_act():
    with pytest.raises(ValidationError, match="IPS mode"):
        IdsEventPayload.model_validate(ids_payload(mode="ids"))


def test_status_has_two_states():
    with pytest.raises(ValidationError):
        StatusPayload.model_validate(status_payload("asleep"))


def test_ingest_checks_the_payload_against_its_message_type():
    wearable, gateway = uuid.uuid4(), uuid.uuid4()
    message = Ingest.model_validate(ingest(wearable, gateway, "alert", alert_payload(n_samples=4)))
    assert isinstance(message.message, AlertPayload)
    with pytest.raises(ValidationError, match="payload: samples"):
        Ingest.model_validate(ingest(wearable, gateway, "alert", alert_payload(n_samples=4, samples=encode([1]))))
    with pytest.raises(ValidationError, match="a wearable does not send ids_event"):
        Ingest.model_validate(ingest(wearable, gateway, "ids_event", ids_payload()))
    with pytest.raises(ValidationError, match="a fixed_gateway does not send alert"):
        Ingest.model_validate(ingest(gateway, gateway, "alert", alert_payload(n_samples=4), device_type="fixed_gateway"))


def test_describe_names_each_field():
    with pytest.raises(ValidationError) as caught:
        AlertPayload.model_validate(alert_payload(fs_hz=0, lead=""))
    described = contracts.describe(caught.value)
    assert "fs_hz:" in described and "lead:" in described


def test_the_d6_example_is_a_valid_alert_payload():
    example = {"v": 1, "msg_id": "6f1c2e0a-0000-4000-8000-000000000001", "seq": 1842, "type": "alert", "fs_hz": 360,
               "lead": "MLII", "n_samples": 3, "encoding": "int16le-base64", "samples": encode([1, 2, 3]),
               "screening": {"label": "abnormal", "confidence": 0.93, "model": "tinydl-0.1"},
               "segment_start": "2026-11-02T10:15:03.120Z", "sent_at": "2026-11-02T10:15:06.500Z"}
    assert AlertPayload.model_validate_json(json.dumps(example)).seq == 1842


def test_revocation_list_v1():
    from app.contracts import RevocationList
    device, fingerprint = str(uuid.uuid4()), "AB" * 32
    listing = RevocationList.model_validate({
        "v": 1, "version": 3, "issued_at": "2026-11-03T10:15:00Z",
        "devices": [{"device_id": device, "status": "revoked", "since": "2026-11-03T10:14:00Z"}],
        "certificates": [{"device_id": device, "fingerprint": fingerprint, "not_after": None}]})
    assert listing.certificates[0].fingerprint == fingerprint
    for fault in ({"version": 0}, {"devices": [{"device_id": device, "status": "active", "since": "2026-11-03T10:14:00Z"}]},
                  {"certificates": [{"device_id": device, "fingerprint": "ab" * 32, "not_after": None}]},
                  {"issued_at": "2026-11-03T10:15:00"}, {"extra": 1}):
        with pytest.raises(ValidationError):
            RevocationList.model_validate({"v": 1, "version": 1, "issued_at": "2026-11-03T10:15:00Z",
                                           "devices": [], "certificates": [], **fault})


def test_a_gateway_status_may_carry_its_revocation_version():
    assert StatusPayload.model_validate(status_payload("online", revocation_version=7)).revocation_version == 7
    with pytest.raises(ValidationError):
        StatusPayload.model_validate(status_payload("online", revocation_version=-1))
