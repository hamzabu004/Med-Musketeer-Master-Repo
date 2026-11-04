"""TC-C33 to TC-C34: the connectivity log ingestion writes, and the org admin's gateway view of it
(D17). TC-C35, what the view leaves out of alerts, is with the access tests (test_access)."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.integration.test_ingest import SECRET, Ward, post
from tests.integration.world import make_device
from tests.messages import alert_payload, ingest, status_payload

pytestmark = pytest.mark.integration

T0 = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)  # before any message the test sends at now


@pytest.fixture
def api(make_client):
    return make_client(None, ingest_secret=SECRET)


@pytest.fixture
def ward(db, system_admin) -> Ward:
    return Ward(db, system_admin)


@pytest.fixture
def admin(make_client, ward):
    return make_client(ward.admin)


def gateway_status(ward, state: str, at: datetime) -> dict:
    return ingest(ward.gateway, ward.gateway, "status", status_payload(state), device_type="fixed_gateway",
                  received_at=at)


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def parsed(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def log(db, gateway) -> list[tuple]:
    return [tuple(row) for row in db.execute(text("""
        SELECT device_id, state, at FROM connectivity_events WHERE gateway_id = :g ORDER BY at, recorded_at
    """), {"g": gateway})]


# --- TC-C33 ------------------------------------------------------------------------------------

def test_tc_c33_the_log_holds_each_change_of_a_gateways_connection_once(api, db, ward, admin):
    assert admin.get(f"/gateways/{ward.gateway}").json()["connectivity"] == {"state": "unknown", "since": None}
    # On connect the broker's event and the gateway's own status both say online; later statuses
    # (a new revocation list) repeat it.
    for message in (gateway_status(ward, "online", at(0)), gateway_status(ward, "online", at(1)),
                    gateway_status(ward, "online", at(60))):
        post(api, message)
    assert log(db, ward.gateway) == [(ward.gateway, "online", at(0))]
    view = admin.get(f"/gateways/{ward.gateway}").json()
    assert (view["connectivity"]["state"], parsed(view["connectivity"]["since"])) == ("online", at(0))

    post(api, gateway_status(ward, "offline", at(120)))
    post(api, gateway_status(ward, "online", at(180)))
    assert [state for _, state, _ in log(db, ward.gateway)] == ["online", "offline", "online"]
    assert parsed(admin.get(f"/gateways/{ward.gateway}").json()["connectivity"]["since"]) == at(180)


def test_tc_c33_a_report_older_than_the_newest_row_is_not_logged(api, db, ward):
    post(api, gateway_status(ward, "online", at(100)))
    post(api, gateway_status(ward, "offline", at(50)))  # delayed: the gateway reconnected since
    assert log(db, ward.gateway) == [(ward.gateway, "online", at(100))]


def test_tc_c33_a_wearables_presence_is_logged_on_the_gateway_it_came_through(api, db, ward, admin):
    post(api, gateway_status(ward, "online", at(0)))
    post(api, ingest(ward.wearable, ward.gateway, "status", status_payload("online"), received_at=at(5)))
    post(api, ingest(ward.wearable, ward.gateway, "status", status_payload("offline", reason="mode_switch"),
                     received_at=at(30)))
    events = admin.get(f"/gateways/{ward.gateway}/connectivity").json()
    assert [(e["device_id"], e["device_type"], e["state"], e["reason"]) for e in events] == [
        (str(ward.wearable), "wearable", "offline", "mode_switch"),
        (str(ward.wearable), "wearable", "online", None),
        (str(ward.gateway), "fixed_gateway", "online", None),
    ]


# --- TC-C34 ------------------------------------------------------------------------------------

def test_tc_c34_the_view_lists_connected_wearables_and_when_their_alerts_came(api, ward, admin):
    post(api, gateway_status(ward, "online", at(0)))
    post(api, ingest(ward.wearable, ward.gateway, "status", status_payload("online"), received_at=at(5)))
    stored = post(api, ingest(ward.wearable, ward.gateway, "alert", alert_payload()))

    [summary] = admin.get("/gateways").json()
    assert (summary["device_id"], summary["wearables_connected"], summary["other_wearables_connected"],
            summary["alerts_24h"]) == (str(ward.gateway), 1, 0, 1)
    detail = admin.get(f"/gateways/{ward.gateway}").json()
    assert [(w["device_id"], w["patient_id"]) for w in detail["wearables"]] == [(str(ward.wearable), str(ward.patient_id))]
    assert parsed(detail["wearables"][0]["connected_since"]) == at(5)
    [alert] = admin.get(f"/gateways/{ward.gateway}/alerts").json()
    assert (alert["device_id"], alert["patient_id"]) == (str(ward.wearable), str(ward.patient_id))
    assert stored["alert_id"] not in admin.get(f"/gateways/{ward.gateway}/alerts").text

    # The gateway goes down: its wearables are unknown, so none is shown as connected.
    post(api, gateway_status(ward, "offline", datetime.now(UTC)))
    detail = admin.get(f"/gateways/{ward.gateway}").json()
    assert (detail["connectivity"]["state"], detail["wearables_connected"], detail["wearables"]) == ("offline", 0, [])


def test_tc_c34_another_organisations_wearable_on_the_gateway_is_counted_not_named(api, db, ward, admin, system_admin):
    other_org = db.scalar(text("INSERT INTO organisations (name, kind) VALUES ('Other', 'private') RETURNING org_id"))
    visitor = make_device(db, "wearable", other_org, system_admin.user_id)
    post(api, ingest(visitor, ward.gateway, "status", status_payload("online")))

    [summary] = admin.get("/gateways").json()
    assert (summary["wearables_connected"], summary["other_wearables_connected"]) == (0, 1)
    for path in ("", "/connectivity"):
        assert str(visitor) not in admin.get(f"/gateways/{ward.gateway}{path}").text, path


def test_tc_c34_a_wearable_or_ungranted_gateway_is_not_a_gateway_of_the_organisation(ward, admin, db, system_admin):
    ungranted = make_device(db, "fixed_gateway", None, system_admin.user_id)
    for device in (ward.wearable, ungranted):
        assert admin.get(f"/gateways/{device}").status_code == 404
    assert [g["device_id"] for g in admin.get("/gateways").json()] == [str(ward.gateway)]
