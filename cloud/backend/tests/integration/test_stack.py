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


def test_tc_c12_a_real_zitadel_token_works_once_the_user_is_registered(stack):
    from app.zitadel_bootstrap import Zitadel

    issuer = f"http://localhost:{PORTS['PROXY_HTTP_PUBLISHED_PORT']}"
    config = json.loads(read_volume_file("mm-config", "zitadel.json"))
    assert config["issuer"] == issuer
    zitadel = Zitadel(issuer, issuer, read_volume_file("zitadel-bootstrap", "admin.pat").strip())

    org = config["default_org_id"]
    user_id = zitadel.create_machine_user(org, "tc-c12-admin", "TC-C12 system admin")
    zitadel.ensure_user_grant(org, user_id, config["project_id"], ["system_admin"])
    client_id, secret = zitadel.client_secret(org, user_id)
    scope = (f"openid urn:zitadel:iam:org:project:id:{config['project_id']}:aud "
             "urn:zitadel:iam:org:projects:roles urn:zitadel:iam:user:resourceowner")
    issued = httpx.post(f"{issuer}/oauth/v2/token", data={"grant_type": "client_credentials", "scope": scope},
                        auth=(client_id, secret), timeout=15)
    assert issued.status_code == 200
    headers = {"Authorization": f"Bearer {issued.json()['access_token']}"}
    api = f"http://127.0.0.1:{PORTS['API_PUBLISHED_PORT']}"

    assert httpx.get(f"{api}/me", headers=headers).status_code == 403  # valid token, not registered yet
    registered = compose(stack, "exec", "-T", "api", "python", "-m", "app.manage", "register-user",
                         "--zitadel-sub", user_id, "--role", "system_admin")
    me = httpx.get(f"{api}/me", headers=headers)
    assert me.status_code == 200
    assert me.json() == {"user_id": registered.stdout.strip(), "role": "system_admin", "org_id": None}
    created = httpx.post(f"{api}/admin/organisations", headers=headers, json={"name": "Ward A", "kind": "public"})
    assert created.status_code == 201
    assert httpx.get(f"{api}/me").status_code == 401
