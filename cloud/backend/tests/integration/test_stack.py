"""TC-C01: the compose stack comes up healthy from empty volumes.

Runs under its own compose project name and ports, so a running development stack is not
touched, and removes its containers and volumes afterwards. Needs Docker with Compose v2
(override the command with MM_COMPOSE, e.g. MM_COMPOSE="podman compose").
"""
import json
import os
import shlex
import shutil
import subprocess
import urllib.request
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

CLOUD_DIR = Path(__file__).resolve().parents[3]
PROJECT = "mm-cloud-tc"
PORTS = {"PROXY_HTTP_PUBLISHED_PORT": "18080", "API_PUBLISHED_PORT": "18000", "EMQX_DASHBOARD_PUBLISHED_PORT": "28083"}
SERVICES = {"postgres", "zitadel-api", "zitadel-login", "proxy", "emqx", "api"}
JOBS = {"migrate", "zitadel-bootstrap"}


def compose(env_file: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    command = shlex.split(os.environ.get("MM_COMPOSE", "docker compose"))
    return subprocess.run(
        [*command, "-p", PROJECT, "--env-file", str(env_file), *args],
        cwd=CLOUD_DIR, capture_output=True, text=True, check=check, timeout=900,
    )


def evidence(name: str, content: str) -> None:
    directory = os.environ.get("MM_EVIDENCE_DIR")
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        (Path(directory) / name).write_text(content)


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    engine = shlex.split(os.environ.get("MM_COMPOSE", "docker compose"))[0]
    if shutil.which(engine) is None:
        pytest.skip(f"{engine} not found; TC-C01 needs a container engine with Compose")
    env_file = tmp_path_factory.mktemp("cloud") / "test.env"
    subprocess.run([str(CLOUD_DIR / "scripts" / "init-env.sh"), str(env_file)], check=True, capture_output=True)
    with env_file.open("a") as handle:
        handle.writelines(f"{name}={value}\n" for name, value in PORTS.items())
    compose(env_file, "down", "--volumes", "--remove-orphans", check=False)
    try:
        up = compose(env_file, "up", "--detach", "--wait", "--build", check=False)
        evidence("compose_up.txt", up.stdout + up.stderr)
        if up.returncode != 0:
            logs = compose(env_file, "logs", "--no-color", check=False)
            evidence("compose_logs.txt", logs.stdout + logs.stderr)
            pytest.fail(f"compose up failed:\n{up.stderr[-4000:]}")
        yield env_file
    finally:
        ps = compose(env_file, "ps", "--all", "--format", "json", check=False)
        evidence("compose_ps.json", ps.stdout)
        compose(env_file, "down", "--volumes", "--remove-orphans", check=False)


def service_states(env_file: Path) -> dict[str, str]:
    output = compose(env_file, "ps", "--all", "--format", "json").stdout
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    if len(rows) == 1 and isinstance(rows[0], list):
        rows = rows[0]
    return {
        row["Service"]: row.get("Health") or f"{row.get('State', '')}:{row.get('ExitCode', '')}"
        for row in rows
    }


def test_tc_c01_every_service_is_healthy(stack):
    states = service_states(stack)
    assert set(states) == SERVICES | JOBS
    assert all(states[name] == "healthy" for name in SERVICES), states
    assert all(states[name] == "exited:0" for name in JOBS), states


def test_tc_c01_healthz_reports_every_dependency_ok(stack):
    url = f"http://127.0.0.1:{PORTS['API_PUBLISHED_PORT']}/healthz"
    with urllib.request.urlopen(url, timeout=10) as response:
        body = json.load(response)
    evidence("healthz.json", json.dumps(body, indent=2))
    assert body == {"status": "ok", "checks": {"database": "ok", "zitadel": "ok", "emqx": "ok"}}


def test_tc_c01_zitadel_serves_oidc_discovery_through_the_proxy(stack):
    url = f"http://localhost:{PORTS['PROXY_HTTP_PUBLISHED_PORT']}/.well-known/openid-configuration"
    with urllib.request.urlopen(url, timeout=10) as response:
        body = json.load(response)
    assert body["issuer"] == f"http://localhost:{PORTS['PROXY_HTTP_PUBLISHED_PORT']}"


# --- TC-C12 end to end: a real ZITADEL token ---------------------------------------------------

def read_volume_file(volume: str, path: str) -> str:
    engine = shlex.split(os.environ.get("MM_COMPOSE", "docker compose"))[0]
    return subprocess.run([engine, "run", "--rm", "-v", f"{PROJECT}_{volume}:/v:ro", "alpine:3.22", "cat", f"/v/{path}"],
                          capture_output=True, text=True, check=True).stdout


def zitadel_admin(stack):
    """The bootstrap's IAM_OWNER client (stands in for ZITADEL's console) and the API's config."""
    from app.zitadel_bootstrap import Zitadel

    issuer = f"http://localhost:{PORTS['PROXY_HTTP_PUBLISHED_PORT']}"
    config = json.loads(read_volume_file("mm-config", "zitadel.json"))
    assert config["issuer"] == issuer
    return Zitadel(issuer, issuer, read_volume_file("zitadel-bootstrap", "admin.pat").strip()), config


def machine_token(zitadel, config: dict, org: str, username: str, role: str, project_grant_id: str | None = None):
    """A machine user in `org` with `role`, and a client-credentials access token for it."""
    user_id = zitadel.create_machine_user(org, username, username)
    zitadel.ensure_user_grant(org, user_id, config["project_id"], [role], project_grant_id)
    client_id, secret = zitadel.client_secret(org, user_id)
    scope = (f"openid urn:zitadel:iam:org:project:id:{config['project_id']}:aud "
             "urn:zitadel:iam:org:projects:roles urn:zitadel:iam:user:resourceowner")
    issued = httpx.post(f"{config['issuer']}/oauth/v2/token", data={"grant_type": "client_credentials", "scope": scope},
                        auth=(client_id, secret), timeout=15)
    assert issued.status_code == 200, issued.text
    return user_id, {"Authorization": f"Bearer {issued.json()['access_token']}"}


def register_user(stack, zitadel_sub: str, role: str, org_id: str | None = None) -> str:
    args = ["--org-id", org_id] if org_id else []
    registered = compose(stack, "exec", "-T", "api", "python", "-m", "app.manage", "register-user",
                         "--zitadel-sub", zitadel_sub, "--role", role, *args)
    return registered.stdout.strip()


API = f"http://127.0.0.1:{PORTS['API_PUBLISHED_PORT']}"


def test_tc_c12_a_real_zitadel_token_works_once_the_user_is_registered(stack):
    zitadel, config = zitadel_admin(stack)
    user_id, headers = machine_token(zitadel, config, config["default_org_id"], "tc-c12-admin", "system_admin")

    assert httpx.get(f"{API}/me", headers=headers).status_code == 403  # valid token, not registered yet
    registered = register_user(stack, user_id, "system_admin")
    me = httpx.get(f"{API}/me", headers=headers)
    assert me.status_code == 200
    assert me.json() == {"user_id": registered, "role": "system_admin", "org_id": None, "patient_id": None}
    created = httpx.post(f"{API}/admin/organisations", headers=headers, json={"name": "TC-C12 Ward", "kind": "public"})
    assert created.status_code == 201
    assert httpx.get(f"{API}/me").status_code == 401


# --- TC-C13: accounts created through the API, in ZITADEL and in `users` -----------------------

def zitadel_user(zitadel, org: str, user_id: str) -> dict:
    """The user's state, organisation and MedMusketeer roles as ZITADEL reports them."""
    user = zitadel.call("GET", f"/v2/users/{user_id}")["user"]
    grants = zitadel.call("POST", "/management/v1/users/grants/_search", org=org,
                          json={"queries": [{"userIdQuery": {"userId": user_id}}]}).get("result", [])
    return {"state": user["state"], "org": user["details"]["resourceOwner"],
            "roles": sorted(role for grant in grants for role in grant.get("roleKeys", []))}


def database_user(stack, zitadel_sub: str) -> str:
    query = f"SELECT role || ',' || status || ',' || coalesce(org_id::text, '') FROM users WHERE zitadel_sub = '{zitadel_sub}'"
    return compose(stack, "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "medmusketeer", "-Atc", query).stdout.strip()


def test_tc_c13_account_creation_shows_up_in_zitadel_and_in_users(stack):
    zitadel, config = zitadel_admin(stack)
    sa_id, sa = machine_token(zitadel, config, config["default_org_id"], "tc-c13-admin", "system_admin")
    register_user(stack, sa_id, "system_admin")
    record = {}

    # The system admin creates an organisation: a ZITADEL organisation with the project granted.
    org = httpx.post(f"{API}/admin/organisations", headers=sa, json={"name": "TC-C13 Hospital", "kind": "public"})
    assert org.status_code == 201, org.text
    org_id, zitadel_org = org.json()["org_id"], org.json()["zitadel_org_id"]
    assert zitadel.call("GET", "/management/v1/orgs/me", org=zitadel_org)["org"]["name"] == "TC-C13 Hospital"
    granted = zitadel.call("POST", "/management/v1/granted_projects/_search", org=zitadel_org, json={})["result"]
    assert [(g["projectId"], sorted(g["grantedRoleKeys"])) for g in granted] == [
        (config["project_id"], ["doctor", "org_admin", "patient"])]
    record["organisation"] = {"org_id": org_id, "zitadel_org_id": zitadel_org, "project_grant": granted[0]["grantId"]}

    # ... and its first organisation admin, a human user in that organisation.
    admin = httpx.post(f"{API}/admin/organisations/{org_id}/admins", headers=sa,
                       json={"email": "tc-c13-admin@hospital.example", "given_name": "Ada", "family_name": "Admin"})
    assert admin.status_code == 201, admin.text
    assert admin.json()["invite_code"]
    record["org_admin"] = zitadel_user(zitadel, zitadel_org, admin.json()["zitadel_sub"])
    assert record["org_admin"] == {"state": "USER_STATE_ACTIVE", "org": zitadel_org, "roles": ["org_admin"]}
    assert database_user(stack, admin.json()["zitadel_sub"]) == f"org_admin,active,{org_id}"

    # An org admin (a machine user here, as a human needs the browser login) creates a doctor and a patient.
    oa_id, oa = machine_token(zitadel, config, zitadel_org, "tc-c13-org-admin", "org_admin", granted[0]["grantId"])
    register_user(stack, oa_id, "org_admin", org_id)
    assert httpx.get(f"{API}/me", headers=oa).json()["role"] == "org_admin"
    created = {}
    for role, extra in (("doctor", {}), ("patient", {"pseudonym": "P-TC13"})):
        response = httpx.post(f"{API}/accounts", headers=oa, json={
            "role": role, "email": f"tc-c13-{role}@hospital.example", "given_name": role.title(),
            "family_name": "Test", **extra})
        assert response.status_code == 201, response.text
        created[role] = response.json()
        record[role] = zitadel_user(zitadel, zitadel_org, response.json()["zitadel_sub"])
        assert record[role] == {"state": "USER_STATE_ACTIVE", "org": zitadel_org, "roles": [role]}
        assert database_user(stack, response.json()["zitadel_sub"]) == f"{role},active,{org_id}"
    listed = {account["user_id"] for account in httpx.get(f"{API}/accounts", headers=oa).json()}
    assert {created["doctor"]["user_id"], created["patient"]["user_id"]} <= listed

    # A duplicate e-mail is refused by ZITADEL and leaves no row.
    duplicate = httpx.post(f"{API}/accounts", headers=oa, json={
        "role": "doctor", "email": "tc-c13-doctor@hospital.example", "given_name": "D", "family_name": "Two"})
    assert duplicate.status_code == 409, duplicate.text
    assert len(httpx.get(f"{API}/accounts", headers=oa).json()) == len(listed)

    # Disabling deactivates the ZITADEL user and the users row together.
    disabled = httpx.post(f"{API}/accounts/{created['doctor']['user_id']}/disable", headers=oa)
    assert disabled.status_code == 200, disabled.text
    record["doctor_disabled"] = zitadel_user(zitadel, zitadel_org, created["doctor"]["zitadel_sub"])
    assert record["doctor_disabled"]["state"] == "USER_STATE_INACTIVE"
    assert database_user(stack, created["doctor"]["zitadel_sub"]) == f"doctor,disabled,{org_id}"

    record["audit"] = [event["action"] for event in httpx.get(f"{API}/audit", headers=oa).json()]
    assert record["audit"][:3] == ["account.disabled", "account.created", "account.created"]
    evidence("tc_c13_accounts.json", json.dumps(record, indent=2))
