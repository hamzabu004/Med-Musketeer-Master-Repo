"""EMQX's authentication and authorisation hooks (D4, D5). Called only by EMQX, with a shared secret.

Gateway authentication: EMQX has already verified the TLS chain to the MedMusketeer CA and set the
username to the certificate CN. The API then requires that the presented certificate (its SHA-256
fingerprint) is an active, unexpired x509_mtls credential of an active fixed_gateway whose
device_id is that CN. So a revoked certificate is refused on its next connect even if the gateway
has another, and a wearable certificate is refused because it is not a gateway.

Topic access (D5): a gateway may publish to mm/fixed/{wearable}/{alert,result,status,command_ack,
telemetry} and mm/gateway/{own id}/..., and subscribe to mm/fixed/+/command (or one wearable's
command topic) and to the wearable revocation list (D16), which only the API publishes, through
EMQX's REST API. The adapter may only subscribe to ingest/#. Everything else is denied.

Every answer is HTTP 200 with {"result": "allow" | "deny"}; anything else (wrong secret, API
error) makes EMQX treat the hook as "ignore", which ends in a refusal. Each authentication
decision is logged with its check time, a benchmark checkpoint later.
"""
import base64
import binascii
import hmac
import logging
import time
import uuid
from typing import Annotated

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.db import Conn, one
from app.revocation import TOPIC as REVOCATION_TOPIC

log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/emqx", include_in_schema=False)

GATEWAY_LISTENER = "ssl:gateway"
SERVICE_LISTENER = "tcp:internal"
ADAPTER_USERNAME = "mm-adapter"
WEARABLE_TOPICS = {"alert", "result", "status", "command_ack", "telemetry"}  # D5

Decision = dict[str, str]
ALLOW: Decision = {"result": "allow"}
DENY: Decision = {"result": "deny"}


def hook_caller(request: Request) -> None:
    secret = request.app.state.settings.emqx_hook_secret
    if secret is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "broker hooks are not configured")
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), secret.get_secret_value().encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not the broker")


Broker = Annotated[None, Depends(hook_caller)]


# --- authentication ----------------------------------------------------------------------------

class GatewayAuthn(BaseModel):
    username: str = ""
    clientid: str = ""
    listener: str = ""
    cert_pem: str = ""  # the client certificate as Base64 DER, as EMQX renders ${cert_pem}


class ServiceAuthn(BaseModel):
    username: str = ""
    password: str = ""
    listener: str = ""


def certificate_fingerprint(cert_pem: str) -> tuple[str, str]:
    """(SHA-256 fingerprint as upper-case hex, CN) of the certificate EMQX passed on."""
    body = "".join(line for line in cert_pem.strip().splitlines() if not line.startswith("-----"))
    der = base64.b64decode(body, validate=True)
    cert = x509.load_der_x509_certificate(der)
    names = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    return cert.fingerprint(hashes.SHA256()).hex().upper(), names[0].value if names else ""


async def gateway_refusal(conn, body: GatewayAuthn) -> str | None:
    """None if the gateway may connect, otherwise the reason (logged, never sent to the client)."""
    if body.listener != GATEWAY_LISTENER:
        return "wrong listener"
    try:
        device_id = uuid.UUID(body.username)
        fingerprint, common_name = certificate_fingerprint(body.cert_pem)
    except (ValueError, binascii.Error):
        return "malformed username or certificate"
    if common_name != body.username:
        return "certificate CN differs from the username"
    row = await one(conn, """
        SELECT d.type, d.status, c.status AS credential_status,
               c.expires_at IS NOT NULL AND c.expires_at <= now() AS credential_expired
        FROM devices d
        LEFT JOIN device_credentials c
               ON c.device_id = d.device_id AND c.auth_method = 'x509_mtls' AND c.credential_ref = :fp
        WHERE d.device_id = :d
    """, d=device_id, fp=fingerprint)
    if row is None:
        return "unknown device"
    if row["type"] != "fixed_gateway":
        return f"device is a {row['type']}"
    if row["status"] != "active":
        return f"device is {row['status']}"
    if row["credential_status"] is None:
        return "certificate is not a registered credential of this device"
    if row["credential_status"] != "active":
        return f"credential is {row['credential_status']}"
    if row["credential_expired"]:
        return "credential has expired"
    return None


@router.post("/authn/gateway")
async def authenticate_gateway(body: GatewayAuthn, _: Broker, conn: Conn) -> Decision:
    started = time.perf_counter()
    reason = await gateway_refusal(conn, body)
    log.info("emqx authn gateway=%s clientid=%s result=%s reason=%s check_ms=%.1f",
             body.username, body.clientid, "deny" if reason else "allow", reason or "-",
             (time.perf_counter() - started) * 1000)
    return DENY if reason else ALLOW


@router.post("/authn/service")
async def authenticate_service(body: ServiceAuthn, _: Broker, request: Request) -> Decision:
    password = request.app.state.settings.emqx_adapter_password
    allowed = (password is not None and body.listener == SERVICE_LISTENER and body.username == ADAPTER_USERNAME
               and hmac.compare_digest(body.password.encode(), password.get_secret_value().encode()))
    log.info("emqx authn service=%s result=%s", body.username, "allow" if allowed else "deny")
    return ALLOW if allowed else DENY


# --- authorisation -----------------------------------------------------------------------------

class Authz(BaseModel):
    username: str = ""
    clientid: str = ""
    listener: str = ""
    topic: str = ""
    action: str = ""  # publish or subscribe


def is_device_id(level: str) -> bool:
    try:
        return str(uuid.UUID(level)) == level
    except ValueError:
        return False


def gateway_may(username: str, action: str, topic: str) -> bool:
    """The D5 topic rules for the gateway whose device id is `username`."""
    levels = topic.split("/")
    if action == "publish":
        if len(levels) == 4 and levels[:2] == ["mm", "fixed"]:
            return is_device_id(levels[2]) and levels[3] in WEARABLE_TOPICS
        if len(levels) >= 4 and levels[:3] == ["mm", "gateway", username]:
            return all(levels[3:]) and not any(level in ("+", "#") for level in levels[3:])
        return False
    if action == "subscribe":
        if topic == REVOCATION_TOPIC:
            return True
        return len(levels) == 4 and levels[:2] == ["mm", "fixed"] and levels[3] == "command" and (
            levels[2] == "+" or is_device_id(levels[2]))
    return False


def adapter_may(action: str, topic: str) -> bool:
    return action == "subscribe" and topic == "ingest/#"


@router.post("/authz")
async def authorise(body: Authz, _: Broker, conn: Conn) -> Decision:
    if body.listener == SERVICE_LISTENER and body.username == ADAPTER_USERNAME:
        allowed = adapter_may(body.action, body.topic)
    elif body.listener == GATEWAY_LISTENER and is_device_id(body.username) and gateway_may(
            body.username, body.action, body.topic):
        # Still an active gateway: a suspended or revoked one loses access when EMQX's
        # authorisation cache expires, without waiting for a reconnect.
        allowed = await one(conn, """
            SELECT 1 FROM devices WHERE device_id = :d AND type = 'fixed_gateway' AND status = 'active'
        """, d=uuid.UUID(body.username)) is not None
    else:
        allowed = False
    if not allowed:
        log.info("emqx authz denied %s %s %s", body.username, body.action, body.topic)
    return ALLOW if allowed else DENY
