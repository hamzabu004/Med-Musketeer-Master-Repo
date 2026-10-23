"""TC-C01: the compose stack comes up healthy from empty volumes.

Runs under its own compose project name and ports, so a running development stack is not
touched, and removes its containers and volumes afterwards. Needs Docker with Compose v2
(override the command with MM_COMPOSE, e.g. MM_COMPOSE="podman compose").
"""
import json
import os
import shlex
import subprocess
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CLOUD_DIR = Path(__file__).resolve().parents[3]
PROJECT = "mm-cloud-tc"
PORTS = {"PROXY_HTTP_PUBLISHED_PORT": "18080", "API_PUBLISHED_PORT": "18000", "EMQX_DASHBOARD_PUBLISHED_PORT": "28083"}
SERVICES = {"postgres", "zitadel-api", "zitadel-login", "proxy", "emqx", "api"}


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
    return {row["Service"]: row.get("Health") or row.get("State", "") for row in rows}


def test_tc_c01_every_service_is_healthy(stack):
    states = service_states(stack)
    assert set(states) == SERVICES
    assert all(state == "healthy" for state in states.values()), states


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
