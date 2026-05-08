"""Per-resource RSA keypair management + JWK serialization.

Each AOAI resource owns its own RSA-2048 keypair. The twin signs the
AAD-shaped JWTs it issues at ``/<resource>/oauth2/v2.0/token`` with the
resource's private key, and publishes the matching public key as a JWK
at ``/<resource>/.well-known/jwks.json`` so the data plane can validate
those tokens without a network round-trip outside the twin.

Pure module — no Flask, no storage. Hosts pass the storage in.

References (retrieved 2026-05-08):
  - RFC 7517 (JWK)
  - RFC 7638 (JWK thumbprint, used as the stable ``kid``)
  - https://learn.microsoft.com/en-us/azure/active-directory/develop/active-directory-v2-protocols
"""

import base64
import hashlib
import json
from typing import Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey


def _b64url_uint(value: int) -> str:
    """Big-endian base64url encoding of an unsigned integer (RFC 7518 §6.3.1)."""
    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode("ascii")


def _public_jwk_components(public_key: RSAPublicKey) -> Tuple[str, str]:
    """Return base64url-encoded (n, e) for an RSA public key."""
    numbers = public_key.public_numbers()
    return _b64url_uint(numbers.n), _b64url_uint(numbers.e)


def compute_kid(public_key: RSAPublicKey) -> str:
    """RFC 7638 thumbprint — stable, deterministic key id."""
    n, e = _public_jwk_components(public_key)
    canonical = json.dumps(
        {"e": e, "kty": "RSA", "n": n},
        separators=(",", ":"),
        sort_keys=False,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(canonical).digest()).rstrip(b"=").decode("ascii")


def generate_keypair_pem() -> Tuple[str, str, str]:
    """Generate an RSA-2048 keypair. Returns (kid, private_pem, public_pem).

    PEM format keeps the storage layer driver-agnostic — the host serialises
    text without needing to know about cryptography internals.
    """
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public = private.public_key()
    public_pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    kid = compute_kid(public)
    return kid, private_pem, public_pem


def load_private_key(private_pem: str) -> RSAPrivateKey:
    return serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)


def load_public_key(public_pem: str) -> RSAPublicKey:
    return serialization.load_pem_public_key(public_pem.encode("ascii"))


def jwk_for_public_key(public_key: RSAPublicKey, *, kid: str) -> dict:
    """Render an RSA public key as a JWK (RFC 7517)."""
    n, e = _public_jwk_components(public_key)
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": n,
        "e": e,
    }


def ensure_keypair(storage, resource_id: str) -> dict:
    """Load the resource's signing key from ``storage``, generating one
    if none exists. Returns ``{kid, private_pem, public_pem}``.

    Idempotent — safe to call from any route handler that needs the key
    (data-plane AAD validation, JWKS publication, OAuth token issue).
    """
    existing = storage.get_signing_key(resource_id)
    if existing:
        return existing
    kid, private_pem, public_pem = generate_keypair_pem()
    return storage.put_signing_key(
        resource_id=resource_id,
        kid=kid,
        private_pem=private_pem,
        public_pem=public_pem,
    )
