"""GET /directory (D14): each role gets the names of exactly the accounts it works with, read from
ZITADEL (faked here; the real one is covered by TC-C19 in test_stack). E-mail goes to the org admin
only."""
import pytest
from sqlalchemy import text

from tests.integration.world import World, build_world

pytestmark = pytest.mark.integration


@pytest.fixture
def world(db, zitadel) -> World:
    world = build_world(db)
    for user_id, sub in db.execute(text("SELECT user_id, zitadel_sub FROM users")):
        zitadel.names[sub] = ("Given", str(user_id))  # family name = user id, to tell people apart
        zitadel.users[sub] = {"email": f"{user_id}@x.example"}
    return world


def directory(make_client, principal) -> dict[str, dict]:
    response = make_client(principal).get("/directory")
    assert response.status_code == 200, response.text
    return {person["user_id"]: person for person in response.json()}


def test_an_org_admin_sees_every_account_of_the_organisation_with_email(make_client, world, db):
    people = directory(make_client, world.a.admin)
    org_users = {str(u) for u in db.scalars(text("SELECT user_id FROM users WHERE org_id = :o"), {"o": world.a.org_id})}
    assert set(people) == org_users
    for user_id, person in people.items():
        assert person["family_name"] == user_id and person["email"] == f"{user_id}@x.example"
    assert not any(secret in str(people) for secret in world.b.secrets)


def test_a_doctor_sees_themselves_and_their_current_patients_without_email(make_client, world):
    people = directory(make_client, world.a.doctor)
    assert set(people) == {str(world.a.doctor.user_id), str(world.a.patient.user_id)}
    assert all(person["email"] is None for person in people.values())
    assert people[str(world.a.patient.user_id)]["role"] == "patient"


def test_a_patient_sees_themselves_and_their_current_doctor(make_client, world):
    people = directory(make_client, world.a.patient)
    assert set(people) == {str(world.a.patient.user_id), str(world.a.doctor.user_id)}
    assert people[str(world.a.doctor.user_id)]["family_name"] == str(world.a.doctor.user_id)
    assert all(person["email"] is None for person in people.values())


def test_a_reassigned_patient_sees_the_new_doctor_only(make_client, world):
    admin = make_client(world.a.admin)
    assert admin.put(f"/patients/{world.a.patient_id}/doctor",
                     json={"doctor_id": str(world.a.other_doctor.user_id)}).status_code == 200
    assert set(directory(make_client, world.a.patient)) == {str(world.a.patient.user_id), str(world.a.other_doctor.user_id)}
    assert str(world.a.patient.user_id) not in directory(make_client, world.a.doctor)


def test_an_account_zitadel_has_no_profile_for_is_listed_without_a_name(make_client, world, zitadel, db):
    sub = db.scalar(text("SELECT zitadel_sub FROM users WHERE user_id = :u"), {"u": world.a.patient.user_id})
    del zitadel.names[sub]
    person = directory(make_client, world.a.doctor)[str(world.a.patient.user_id)]
    assert person["given_name"] is None and person["family_name"] is None


def test_a_zitadel_failure_is_a_502(make_client, world, zitadel):
    zitadel.fail("profiles", 503)
    assert make_client(world.a.admin).get("/directory").status_code == 502
