"""Unit tests: accepting a revocation list (D16) and keeping it across restarts."""
import json
import uuid
from pathlib import Path

import pytest

from mm_uplink import revocations
from mm_uplink.revocations import Invalid, RevocationStore, parse

REPO = Path(__file__).resolve().parents[3]


def listing(version: int, *devices: str, certificates: tuple[str, ...] = ()) -> dict:
    return {"v": 1, "version": version, "issued_at": "2026-10-30T10:00:00Z",
            "devices": [{"device_id": d, "status": "revoked", "since": "2026-10-30T09:00:00Z"} for d in devices],
            "certificates": [{"device_id": c, "fingerprint": "AB" * 32, "not_after": None} for c in certificates]}


def encode(document: dict) -> bytes:
    return json.dumps(document).encode()


@pytest.mark.parametrize("name", ["revocation-list-v1", "status-v1"])
def test_the_shipped_schemas_match_shared_contracts(name):
    shipped = Path(revocations.__file__).parent / "schemas" / f"{name}.schema.json"
    assert shipped.read_text() == (REPO / "shared" / "contracts" / f"{name}.schema.json").read_text(), (
        f"copy shared/contracts/{name}.schema.json into mm_uplink/schemas/")


def test_a_valid_list_parses():
    device = str(uuid.uuid4())
    assert parse(encode(listing(3, device)))["devices"][0]["device_id"] == device


@pytest.mark.parametrize("fault", [
    b"not json",
    encode({"v": 1}),
    encode(listing(0)),
    encode({**listing(2), "extra": True}),
    encode(listing(2, "not-a-uuid")),
    encode(listing(2, str(uuid.uuid4()).upper())),                 # canonical ids are lower case
    encode(listing(2, f"{uuid.uuid4()}\ntopic readwrite #")),      # would inject an ACL line
    encode(listing(2, certificates=("x\nuser y",))),
])
def test_invalid_lists_are_refused(fault):
    with pytest.raises(Invalid):
        parse(fault)


def test_only_newer_versions_are_kept_and_survive_a_restart(tmp_path):
    path = tmp_path / "revocations.json"
    store = RevocationStore(path)
    assert store.version is None and not store.listed("x")
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    assert store.offer(encode(listing(2, first)))["version"] == 2
    assert store.offer(encode(listing(2))) is None          # equal: a redelivery
    assert store.offer(encode(listing(1))) is None          # older: a delayed duplicate
    assert store.offer(b"{broken") is None
    assert store.listed(first) and not store.listed(second)
    assert store.offer(encode(listing(5, second)))["version"] == 5
    restarted = RevocationStore(path)
    assert restarted.version == 5 and restarted.listed(second) and not restarted.listed(first)
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_an_unusable_stored_list_is_ignored_not_fatal(tmp_path):
    path = tmp_path / "revocations.json"
    path.write_text("{not json")
    store = RevocationStore(path)
    assert store.version is None
    assert store.offer(encode(listing(1)))["version"] == 1
