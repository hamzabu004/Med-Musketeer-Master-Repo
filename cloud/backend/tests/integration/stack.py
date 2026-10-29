"""The full compose stack for the A-stack tests (TC-C01, C12 to C26), shared by the test modules.

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

from tests.certs import Issued, TestCA
from tests.mqtt import Client, tls_context

CLOUD_DIR = Path(__file__).resolve().parents[3]
PROJECT = "mm-cloud-tc"
PORTS = {"PROXY_HTTP_PUBLISHED_PORT": "18080", "API_PUBLISHED_PORT": "18000", "EMQX_DASHBOARD_PUBLISHED_PORT": "28083",
         "EMQX_GATEWAY_PUBLISHED_PORT": "28883", "EMQX_INTERNAL_PUBLISHED_PORT": "21883"}
# No periodic full republish of the revocation list during a test session: TC-C29 checks that the
# retained list survives EMQX being recreated without being published again.
SETTINGS = {**PORTS, "REVOCATION_REPUBLISH_S": "86400"}


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
GATEWAY_PORT = int(PORTS["EMQX_GATEWAY_PUBLISHED_PORT"])
INTERNAL_PORT = int(PORTS["EMQX_INTERNAL_PUBLISHED_PORT"])


def register(admin, issued: Issued, device_type: str) -> str:
    """Register, add the certificate as its credential, activate; returns the credential id."""
    response = admin.post("/admin/devices", json={"device_id": issued.device_id, "type": device_type, "is_testbed": True})
    assert response.status_code in (201, 409), response.text  # 409: a second certificate for the same device
    credential = admin.post(f"/admin/devices/{issued.device_id}/credentials",
                            json={"auth_method": "x509_mtls", "key_type": "ec_p256", "credential_ref": issued.fingerprint})
    assert credential.status_code == 201, credential.text
    if response.status_code == 201:
        assert admin.post(f"/admin/devices/{issued.device_id}/activate").status_code == 200
    return credential.json()["credential_id"]


def gateway(stack_ca: TestCA, issued: Issued | None) -> Client:
    context = tls_context(stack_ca.ca_cert, issued.cert if issued else None, issued.key if issued else None)
    return Client(GATEWAY_PORT, context)

