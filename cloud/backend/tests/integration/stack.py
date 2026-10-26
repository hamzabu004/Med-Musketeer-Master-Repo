"""The full compose stack for the A-stack tests (TC-C01, C12 to C18), shared by the test modules.

It runs under its own compose project name and ports, so a running development stack is not
touched, and is removed with its volumes afterwards. Before `up`, a throwaway CA is created with
the real CA tool and the cloud certificate is installed with scripts/install-emqx-certs.sh, so the
gateway listener runs as in production. Needs Docker with Compose v2 (override the command with
MM_COMPOSE, e.g. MM_COMPOSE="podman compose").
"""
import json
import os
import shlex
import subprocess
from pathlib import Path

import httpx

CLOUD_DIR = Path(__file__).resolve().parents[3]
PROJECT = "mm-cloud-tc"
PORTS = {"PROXY_HTTP_PUBLISHED_PORT": "18080", "API_PUBLISHED_PORT": "18000", "EMQX_DASHBOARD_PUBLISHED_PORT": "28083",
         "EMQX_GATEWAY_PUBLISHED_PORT": "28883", "EMQX_INTERNAL_PUBLISHED_PORT": "21883"}


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


def env_value(env_file: Path, name: str) -> str:
    for line in env_file.read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    raise KeyError(name)


def read_volume_file(volume: str, path: str) -> str:
    engine = shlex.split(os.environ.get("MM_COMPOSE", "docker compose"))[0]
    return subprocess.run([engine, "run", "--rm", "-v", f"{PROJECT}_{volume}:/v:ro", "alpine:3.22.2", "cat", f"/v/{path}"],
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
