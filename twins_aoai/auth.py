"""Data-plane authentication decorators.

Two layers, applied in order on every ``/<resource>/openai/...`` route:

* :func:`require_resource` — resolves the URL's ``<resource>`` segment
  and stashes the row on ``g.resource`` (or 404s with the AOAI envelope).

* :func:`require_aoai_data_auth` — accepts EITHER an ``api-key`` header
  OR an ``Authorization: Bearer <jwt>`` header. Either is sufficient.
  On success, sets ``g.tenant_id`` to the resource's owning tenant.

Tenant isolation is enforced on both paths:

* api-key path: the looked-up key must belong to ``g.resource``.
* AAD path: the JWT's ``tid`` claim must match the resource's tenant.

Twin-Plane (``/_twin/...``) auth is unrelated and lives in
``twin_plane/auth.py``.
"""

import functools

from flask import g, request

from .crypto import ensure_keypair
from .errors import aoai_not_found, aoai_unauthorized
from .logs import emit
from .sids import hash_api_key
from .tokens import (
    DEFAULT_AUDIENCE,
    ValidationFailure,
    validate_inbound_aad_token,
)


def require_resource(view):
    """Resolve the ``<resource_id>`` path segment to a storage row."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        resource_id = kwargs.get("resource_id", "")
        if not resource_id:
            return aoai_not_found("Resource not specified")
        resource = g.storage.get_resource(resource_id)
        if not resource:
            return aoai_not_found(f"Resource {resource_id!r} not found")
        g.resource = resource
        return view(*args, **kwargs)

    return wrapper


def _api_key_path() -> tuple[bool, str | None]:
    """Try the api-key header. Returns (ok, reason).

    On success, sets ``g.tenant_id`` and returns ``(True, None)``.
    """
    raw_key = request.headers.get("api-key", "")
    if not raw_key:
        return (False, "missing-api-key")
    row = g.storage.get_api_key_by_hash(hash_api_key(raw_key))
    if not row:
        return (False, "unknown-api-key")
    if row.get("resource_id") != g.resource["resource_id"]:
        return (False, "api-key-resource-mismatch")
    g.tenant_id = g.resource["tenant_id"]
    return (True, None)


def _aad_path() -> tuple[bool, str | None]:
    """Try the AAD bearer path. Returns (ok, reason)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return (False, "missing-bearer")
    token = auth[7:]

    base = g.base_url.rstrip("/")
    expected_issuer = f"{base}/{g.resource['resource_id']}/v2.0"

    try:
        claims = validate_inbound_aad_token(
            token=token,
            expected_audience=DEFAULT_AUDIENCE,
            expected_issuer=expected_issuer,
            jwks_resolver=lambda: g.storage.get_signing_key(g.resource["resource_id"]),
        )
    except ValidationFailure as exc:
        return (False, exc.reason)

    if claims.get("tid") != g.resource["tenant_id"]:
        return (False, "tid-mismatch")
    g.tenant_id = g.resource["tenant_id"]
    return (True, None)


def require_aoai_data_auth(view):
    """Either ``api-key`` or AAD ``Authorization: Bearer`` is sufficient."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        # Lazily ensure the per-resource keypair exists so the AAD path
        # can validate even on a cold resource (the issuer URL is stable
        # whether or not anyone has hit the JWKS endpoint yet).
        ensure_keypair(g.storage, g.resource["resource_id"])

        api_key_present = bool(request.headers.get("api-key"))
        bearer_present = request.headers.get("Authorization", "").startswith("Bearer ")

        if api_key_present:
            ok, reason = _api_key_path()
            if ok:
                emit(
                    g.storage,
                    tenant_id=g.tenant_id,
                    plane="data",
                    operation="auth.api_key.validate",
                    resource={"type": "resource", "id": g.resource["resource_id"]},
                )
                return view(*args, **kwargs)
            # Fall through to AAD only if the api-key was absent; a bad
            # api-key is a hard reject (caller chose that path).
            emit(
                g.storage,
                tenant_id=g.resource["tenant_id"],
                plane="data",
                operation="auth.api_key.validate",
                resource={"type": "resource", "id": g.resource["resource_id"]},
                outcome="failure",
                reason=reason,
            )
            return aoai_unauthorized()

        if bearer_present:
            ok, reason = _aad_path()
            if ok:
                emit(
                    g.storage,
                    tenant_id=g.tenant_id,
                    plane="data",
                    operation="auth.aad.token.validate",
                    resource={"type": "resource", "id": g.resource["resource_id"]},
                )
                return view(*args, **kwargs)
            emit(
                g.storage,
                tenant_id=g.resource["tenant_id"],
                plane="data",
                operation="auth.aad.token.validate",
                resource={"type": "resource", "id": g.resource["resource_id"]},
                outcome="failure",
                reason=reason,
            )
            return aoai_unauthorized()

        emit(
            g.storage,
            tenant_id=g.resource["tenant_id"],
            plane="data",
            operation="auth.api_key.validate",
            resource={"type": "resource", "id": g.resource["resource_id"]},
            outcome="failure",
            reason="missing-credentials",
        )
        return aoai_unauthorized()

    return wrapper
