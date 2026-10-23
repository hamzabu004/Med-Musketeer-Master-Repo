"""TC-C12 (token part): only properly signed, current tokens for the MedMusketeer project pass."""
import asyncio
import time

import jwt
import pytest

from app.tokens import InvalidToken, TokenVerifier
from tests.tokens import CONFIG, DEFAULT_ORG_ID, PROJECT_ID, FakeJwks, SigningKey


@pytest.fixture
def key():
    return SigningKey()


def verify(jwks: FakeJwks, token: str):
    async def run():
        async with jwks.client() as http:
            return await TokenVerifier(CONFIG, "http://zitadel-api:8080", http).verify(token)
    return asyncio.run(run())


def test_a_valid_token_yields_its_subject_roles_and_organisation(key):
    claims = verify(FakeJwks(key), key.token(sub="u-42", roles={"doctor": {"org-7": "d"}}, org="org-7"))
    assert claims.subject == "u-42"
    assert claims.roles == {"doctor": {"org-7"}}
    assert claims.zitadel_org_id == "org-7"


def test_keys_are_fetched_with_the_public_host_name(key):
    jwks = FakeJwks(key)
    verify(jwks, key.token())
    assert jwks.requests[0].url.host == "zitadel-api"
    assert jwks.requests[0].headers["Host"] == "localhost:8080"


@pytest.mark.parametrize("overrides, reason", [
    ({"iss": "http://evil.example"}, "InvalidIssuerError"),
    ({"aud": ["another-project"]}, "InvalidAudienceError"),
    ({"exp": -120}, "ExpiredSignatureError"),     # times are offsets from now, applied in the test
    ({"nbf": +120}, "ImmatureSignatureError"),
    ({"exp": None}, "MissingRequiredClaimError"),
    ({"sub": None}, "MissingRequiredClaimError"),
])
def test_tc_c12_wrong_issuer_audience_or_time_is_refused(key, overrides, reason):
    now = int(time.time())
    claims = {name: now + value if name in ("exp", "nbf") and value is not None else value
              for name, value in overrides.items()}
    with pytest.raises(InvalidToken, match=reason):
        verify(FakeJwks(key), key.token(**claims))


def test_tc_c12_a_token_signed_by_another_key_is_refused(key):
    impostor = SigningKey(kid=key.kid)  # same key id, different key
    with pytest.raises(InvalidToken, match="InvalidSignatureError"):
        verify(FakeJwks(key), impostor.token())


def test_tc_c12_a_token_with_an_unknown_key_id_is_refused(key):
    with pytest.raises(InvalidToken, match="unknown signing key"):
        verify(FakeJwks(key), SigningKey().token())


@pytest.mark.parametrize("algorithm", ["HS256", "none"])
def test_tc_c12_other_algorithms_are_refused(key, algorithm):
    payload = {"iss": CONFIG.issuer, "aud": [PROJECT_ID], "sub": "u", "exp": int(time.time()) + 60, "iat": int(time.time())}
    token = jwt.encode(payload, "s" * 32 if algorithm == "HS256" else None, algorithm=algorithm, headers={"kid": key.kid})
    with pytest.raises(InvalidToken, match="algorithm"):
        verify(FakeJwks(key), token)


def test_a_garbage_token_is_refused(key):
    with pytest.raises(InvalidToken, match="malformed"):
        verify(FakeJwks(key), "not-a-jwt")


def test_a_token_without_role_or_organisation_claims_is_refused(key):
    from app.tokens import ORG_CLAIM
    with pytest.raises(InvalidToken, match="missing role or organisation"):
        verify(FakeJwks(key), key.token(**{ORG_CLAIM: None}))


def test_rotated_keys_are_picked_up_without_a_restart(key):
    """ZITADEL rotates signing keys: an unseen key id triggers one refetch of the JWKS."""
    jwks = FakeJwks(key)
    new_key = SigningKey()

    async def run():
        async with jwks.client() as http:
            verifier = TokenVerifier(CONFIG, "http://zitadel-api:8080", http)
            await verifier.verify(key.token())
            jwks.keys.append(new_key)
            verifier._fetched_at -= 3600  # pretend the last fetch was long ago
            return await verifier.verify(new_key.token(org=DEFAULT_ORG_ID))

    assert asyncio.run(run()).zitadel_org_id == DEFAULT_ORG_ID
    assert len(jwks.requests) == 2
