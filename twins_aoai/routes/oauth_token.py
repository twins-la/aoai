"""Per-resource OAuth 2.0 token endpoint.

Emulates the AAD ``v2.0`` token endpoint at
``/<resource>/oauth2/v2.0/token``. A consumer presents
``client_id`` + ``client_secret`` (an api-key id and api-key secret
provisioned via the Twin Plane) and receives an AAD-shaped access token
the data plane will accept on subsequent ``Authorization: Bearer``
calls.

The error envelope on failure matches AAD's documented shape
(``invalid_client`` etc.) so SDKs that surface AAD errors verbatim get
familiar text.
"""

import time
import uuid

from flask import Blueprint, g, jsonify, request

from ..crypto import ensure_keypair
from ..errors import aoai_not_found
from ..logs import emit
from ..sids import hash_api_key
from ..tokens import (
    DEFAULT_AUDIENCE,
    DEFAULT_TOKEN_TTL_SECONDS,
    issue_aad_token,
)

oauth_token_bp = Blueprint("oauth_token", __name__)


def _aad_token_error(error: str, description: str, status: int):
    """AAD-shaped token-endpoint error body."""
    body = {
        "error": error,
        "error_description": description,
        "error_codes": [70002] if error == "invalid_client" else [50000],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "trace_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
    }
    resp = jsonify(body)
    resp.status_code = status
    return resp


@oauth_token_bp.route("/<resource_id>/oauth2/v2.0/token", methods=["POST"])
def token(resource_id: str):
    """``application/x-www-form-urlencoded`` body.

    Body fields:
        grant_type      — must be ``client_credentials``.
        client_id       — an api-key id provisioned for this resource.
        client_secret   — the matching api-key secret.
        scope           — defaults to ``<aud>/.default`` per AAD convention.
    """
    resource = g.storage.get_resource(resource_id)
    if not resource:
        return aoai_not_found(f"Resource {resource_id!r} not found")

    grant_type = request.form.get("grant_type", "")
    if grant_type != "client_credentials":
        emit(
            g.storage,
            tenant_id=resource["tenant_id"],
            plane="control",
            operation="control.token.issue",
            resource={"type": "resource", "id": resource_id},
            outcome="failure",
            reason=f"unsupported grant_type {grant_type!r}",
        )
        return _aad_token_error(
            "unsupported_grant_type",
            f"grant_type {grant_type!r} not supported",
            400,
        )

    client_id = request.form.get("client_id", "")
    client_secret = request.form.get("client_secret", "")

    row = g.storage.get_api_key_by_hash(hash_api_key(client_secret))
    if (
        not row
        or row.get("resource_id") != resource_id
        or row.get("key_id") != client_id
    ):
        emit(
            g.storage,
            tenant_id=resource["tenant_id"],
            plane="control",
            operation="control.token.issue",
            resource={"type": "resource", "id": resource_id},
            outcome="failure",
            reason="invalid client_id or client_secret",
            details={"client_id": client_id},
        )
        return _aad_token_error(
            "invalid_client",
            "Client credentials are invalid for this resource",
            401,
        )

    base = g.base_url.rstrip("/")
    issuer = f"{base}/{resource_id}/v2.0"
    keypair = ensure_keypair(g.storage, resource_id)
    access_token = issue_aad_token(
        private_pem=keypair["private_pem"],
        kid=keypair["kid"],
        issuer=issuer,
        audience=DEFAULT_AUDIENCE,
        tenant_id_claim=resource["tenant_id"],
        app_id_claim=client_id,
    )

    emit(
        g.storage,
        tenant_id=resource["tenant_id"],
        plane="control",
        operation="control.token.issue",
        resource={"type": "resource", "id": resource_id},
        details={"client_id": client_id, "expires_in": DEFAULT_TOKEN_TTL_SECONDS},
    )

    return jsonify(
        {
            "token_type": "Bearer",
            "expires_in": DEFAULT_TOKEN_TTL_SECONDS,
            "ext_expires_in": DEFAULT_TOKEN_TTL_SECONDS,
            "access_token": access_token,
        }
    )
