"""AAD-shaped JWT issuance + validation, per-resource.

The twin emulates the AAD ``v2.0`` token endpoint at
``/<resource>/oauth2/v2.0/token`` and signs the resulting access token
with the resource's RSA keypair. Data-plane requests carrying
``Authorization: Bearer <jwt>`` are validated against the same key.

Token shape mirrors a real AAD ``v1.0`` access token (Azure OpenAI's
documented audience is ``https://cognitiveservices.azure.com``):

    iss = "<base_url>/<resource>/v2.0"
    aud = "https://cognitiveservices.azure.com"
    tid = <tenant_id>          # the twin's tenant, NOT an AAD tenant
    appid = <api_key_id>       # the api-key id used as client_id
    sub = <api_key_id>
    iat / nbf / exp = standard
    ver = "1.0"

References (retrieved 2026-05-08):
  - RFC 7519 — JSON Web Token
  - https://learn.microsoft.com/en-us/azure/active-directory/develop/access-tokens
"""

import time
from dataclasses import dataclass

import jwt

from .crypto import load_private_key, load_public_key

DEFAULT_AUDIENCE = "https://cognitiveservices.azure.com"
"""Documented Azure OpenAI AAD audience (Cognitive Services data plane)."""

DEFAULT_TOKEN_TTL_SECONDS = 3600
"""1 hour — matches AAD's default access-token TTL."""

CLOCK_SKEW_SECONDS = 5 * 60
"""Industry-standard 5-minute skew."""


@dataclass
class ValidationFailure(Exception):
    reason: str
    """Specific machine-readable rejection reason. Tests assert on these
    literals: ``missing-bearer``, ``bad-iss``, ``bad-aud``, ``expired``,
    ``unknown-kid``, ``sig-invalid``, ``unsupported-alg``,
    ``missing-claim``."""


def issue_aad_token(
    *,
    private_pem: str,
    kid: str,
    issuer: str,
    audience: str,
    tenant_id_claim: str,
    app_id_claim: str,
    ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
) -> str:
    """Sign an AAD-shaped access token the data plane will accept.

    ``issuer`` is the resource-scoped issuer URL
    (``<base_url>/<resource>/v2.0``); ``tenant_id_claim`` is the twin's
    tenant id (placed in ``tid`` so a real AAD-validating consumer sees a
    plausibly-shaped tenant claim).
    """
    now = int(time.time())
    payload = {
        "iss": issuer,
        "aud": audience,
        "tid": tenant_id_claim,
        "appid": app_id_claim,
        "sub": app_id_claim,
        "iat": now,
        "nbf": now - 5,
        "exp": now + ttl_seconds,
        "ver": "1.0",
    }
    return jwt.encode(
        payload,
        load_private_key(private_pem),
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )


def validate_inbound_aad_token(
    *,
    token: str,
    expected_audience: str,
    expected_issuer: str,
    jwks_resolver,
) -> dict:
    """Validate a bearer token presented on the AOAI data plane.

    ``jwks_resolver`` is a zero-arg callable returning the resource's
    storage signing-key dict (``{kid, private_pem, public_pem}``) or
    ``None``. Resolution is deferred so route handlers can scope the
    lookup to the resource the URL identifies.

    Returns the decoded claims on success; raises
    :class:`ValidationFailure` with a specific ``reason`` on rejection.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise ValidationFailure("sig-invalid") from exc
    if header.get("alg") != "RS256":
        raise ValidationFailure("unsupported-alg")
    kid = header.get("kid")
    if not kid:
        raise ValidationFailure("missing-claim")

    keypair = jwks_resolver()
    if not keypair or keypair.get("kid") != kid:
        raise ValidationFailure("unknown-kid")

    try:
        claims = jwt.decode(
            token,
            load_public_key(keypair["public_pem"]),
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=expected_issuer,
            leeway=CLOCK_SKEW_SECONDS,
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValidationFailure("expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise ValidationFailure("bad-aud") from exc
    except jwt.InvalidIssuerError as exc:
        raise ValidationFailure("bad-iss") from exc
    except jwt.InvalidTokenError as exc:
        raise ValidationFailure("sig-invalid") from exc

    if "tid" not in claims:
        raise ValidationFailure("missing-claim")
    return claims


def jwks_doc_for_storage_keypair(storage_keypair: dict) -> dict:
    """Render a stored keypair as a JWKS document for publication."""
    public_key = load_public_key(storage_keypair["public_pem"])
    return {"keys": [jwk_for_public_key(public_key, kid=storage_keypair["kid"])]}


# Re-export to avoid duplicate imports at call sites.
from .crypto import jwk_for_public_key  # noqa: E402
