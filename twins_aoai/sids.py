"""Identifier generators for the AOAI twin.

Real Azure OpenAI uses opaque strings for resource names, deployment
names, and api-keys (32-char hex). Synthetic identifiers below match the
shape so consumer code that parses or compares these does not need to
special-case the twin.
"""

import hashlib
import secrets


def hash_api_key(raw_key: str) -> str:
    """Deterministic hash of an api-key for storage lookup.

    Plain SHA-256 — not a password hash. AOAI api-keys are 32 bytes of
    secure entropy from :func:`generate_api_key`, so a fast deterministic
    digest is appropriate (and necessary, since rows are looked up by
    hash on the auth hot path).
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_resource_id() -> str:
    """Synthetic resource alias. Operators may override at create time."""
    return f"r-{secrets.token_urlsafe(8)}"


def generate_deployment_id() -> str:
    """Synthetic deployment name. Operators may override at create time."""
    return f"dep-{secrets.token_urlsafe(8)}"


def generate_api_key() -> str:
    """AOAI-shaped api key — 32 bytes hex (matches Azure's display format)."""
    return secrets.token_hex(32)


def generate_api_key_id() -> str:
    """Twin-side identifier for an api-key row."""
    return f"apikey_{secrets.token_urlsafe(12)}"


def generate_completion_id() -> str:
    """Tail of an OpenAI completion id (the ``chatcmpl-<id>`` form)."""
    return secrets.token_urlsafe(20)


def generate_request_id() -> str:
    """History-row id; not surfaced on the wire."""
    return secrets.token_urlsafe(16)


def generate_feedback_id() -> str:
    return f"fb_{secrets.token_urlsafe(12)}"
