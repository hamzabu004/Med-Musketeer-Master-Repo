"""Validation of ZITADEL-issued JWT access tokens (D2/D3).

A token is accepted only if it is signed (RS256) by a key from ZITADEL's JWKS, was issued by the
configured issuer for the MedMusketeer project (audience), and is within its validity window.
The claims the API relies on are then extracted; mapping them to a MedMusketeer user is done in
app.auth, against the database.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import jwt

log = logging.getLogger(__name__)

ROLES_CLAIM = "urn:zitadel:iam:org:project:{project_id}:roles"
ORG_CLAIM = "urn:zitadel:iam:user:resourceowner:id"
LEEWAY_S = 30
JWKS_MIN_REFRESH_S = 60  # an unknown key id triggers a refetch at most this often


class InvalidToken(Exception):
    """The token is not acceptable. The message is safe to log; it never contains the token."""


@dataclass(frozen=True)
class ZitadelConfig:
    """Written by the zitadel-bootstrap job (app.zitadel_bootstrap); nothing in it is secret."""
    issuer: str
    project_id: str
    default_org_id: str

    @classmethod
    def load(cls, path: Path) -> "ZitadelConfig":
        data = json.loads(path.read_text())
        return cls(issuer=data["issuer"], project_id=data["project_id"], default_org_id=data["default_org_id"])


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    roles: dict[str, set[str]]  # MedMusketeer role -> ZITADEL org ids that granted it
    zitadel_org_id: str


class TokenVerifier:
    def __init__(self, config: ZitadelConfig, zitadel_url: str, http: httpx.AsyncClient):
        self.config = config
        self._jwks_url = f"{zitadel_url.rstrip('/')}/oauth/v2/keys"
        # ZITADEL picks the instance by Host, so internal calls carry the public host name.
        self._host = urlsplit(config.issuer).netloc
        self._http = http
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _refresh_keys(self, force: bool) -> None:
        async with self._lock:
            if not force and self._keys:
                return
            if force and time.monotonic() - self._fetched_at < JWKS_MIN_REFRESH_S:
                return
            response = await self._http.get(self._jwks_url, headers={"Host": self._host})
            response.raise_for_status()
            keys = {}
            for entry in response.json().get("keys", []):
                if entry.get("kid") and entry.get("kty") == "RSA":
                    keys[entry["kid"]] = jwt.PyJWK(entry, algorithm="RS256")
            self._keys = keys
            self._fetched_at = time.monotonic()

    async def _key_for(self, kid: str) -> jwt.PyJWK:
        await self._refresh_keys(force=False)
        if kid not in self._keys:
            await self._refresh_keys(force=True)  # ZITADEL rotates its signing keys
        if kid not in self._keys:
            raise InvalidToken("unknown signing key")
        return self._keys[kid]

    async def verify(self, token: str) -> TokenClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as error:
            raise InvalidToken("malformed token") from error
        if header.get("alg") != "RS256":
            raise InvalidToken("unexpected signing algorithm")
        key = await self._key_for(str(header.get("kid", "")))
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                issuer=self.config.issuer,
                audience=self.config.project_id,
                leeway=LEEWAY_S,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as error:
            raise InvalidToken(type(error).__name__) from error

        raw_roles = claims.get(ROLES_CLAIM.format(project_id=self.config.project_id)) or {}
        org_id = claims.get(ORG_CLAIM)
        if not isinstance(raw_roles, dict) or not isinstance(org_id, str):
            raise InvalidToken("missing role or organisation claims")
        roles = {role: set(grants) for role, grants in raw_roles.items() if isinstance(grants, dict)}
        return TokenClaims(subject=claims["sub"], roles=roles, zitadel_org_id=org_id)
