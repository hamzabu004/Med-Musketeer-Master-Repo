"""Test helper: an RSA signing key and a ZITADEL-like JWKS, to issue tokens without ZITADEL."""
import time
import uuid

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.tokens import ROLES_CLAIM, ORG_CLAIM, ZitadelConfig

ISSUER = "http://localhost:8080"
PROJECT_ID = "300000000000000001"
DEFAULT_ORG_ID = "300000000000000002"
CONFIG = ZitadelConfig(issuer=ISSUER, project_id=PROJECT_ID, default_org_id=DEFAULT_ORG_ID)


class SigningKey:
    def __init__(self, kid: str | None = None):
        self.kid = kid or uuid.uuid4().hex
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def jwk(self) -> dict:
        public = jwt.algorithms.RSAAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        return {**public, "kid": self.kid, "use": "sig", "alg": "RS256"}

    def token(self, sub: str = "user-1", roles: dict | None = None, org: str = DEFAULT_ORG_ID,
              **overrides) -> str:
        now = int(time.time())
        claims = {
            "iss": ISSUER, "aud": [PROJECT_ID], "sub": sub, "iat": now, "nbf": now, "exp": now + 300,
            ROLES_CLAIM.format(project_id=PROJECT_ID): roles if roles is not None else {"system_admin": {org: "x"}},
            ORG_CLAIM: org,
        }
        claims.update(overrides)
        claims = {key: value for key, value in claims.items() if value is not None}
        return jwt.encode(claims, self.private, algorithm="RS256", headers={"kid": self.kid})


class FakeJwks:
    """Serves the given keys at /oauth/v2/keys and records the requests it receives."""

    def __init__(self, *keys: SigningKey):
        self.keys = list(keys)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.path == "/oauth/v2/keys"
        return httpx.Response(200, json={"keys": [key.jwk() for key in self.keys]})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
