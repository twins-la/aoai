"""OpenID Connect Discovery + JWKS — per-resource public surface.

Real Azure OpenAI relies on AAD's tenant-scoped discovery at
``https://login.microsoftonline.com/<tid>/v2.0/.well-known/openid-configuration``.
The twin substitutes a per-resource discovery doc whose endpoints all
live under the resource's path prefix, so consumers wanting AAD-style
auth can point their token-acquisition flow at the twin.

References (retrieved 2026-05-08):
  - https://learn.microsoft.com/en-us/azure/active-directory/develop/active-directory-v2-protocols
  - RFC 7517 (JSON Web Key)
"""

from flask import Blueprint, g, jsonify

from twins_local.logs import ANONYMOUS_TENANT_ID

from ..crypto import ensure_keypair
from ..errors import aoai_not_found
from ..logs import emit
from ..tokens import jwks_doc_for_storage_keypair

well_known_bp = Blueprint("well_known", __name__)


@well_known_bp.route(
    "/<resource_id>/.well-known/openid-configuration", methods=["GET"]
)
def openid_configuration(resource_id: str):
    """OpenID Connect Discovery doc, scoped to one resource."""
    resource = g.storage.get_resource(resource_id)
    if not resource:
        return aoai_not_found(f"Resource {resource_id!r} not found")

    base = g.base_url.rstrip("/")
    body = {
        "issuer": f"{base}/{resource_id}/v2.0",
        "token_endpoint": f"{base}/{resource_id}/oauth2/v2.0/token",
        "jwks_uri": f"{base}/{resource_id}/.well-known/jwks.json",
        "id_token_signing_alg_values_supported": ["RS256"],
        "response_types_supported": ["token"],
        "subject_types_supported": ["public"],
    }
    emit(
        g.storage,
        tenant_id=ANONYMOUS_TENANT_ID,
        plane="data",
        operation="data.openid.fetch",
        resource={"type": "resource", "id": resource_id},
    )
    return jsonify(body)


@well_known_bp.route("/<resource_id>/.well-known/jwks.json", methods=["GET"])
def jwks(resource_id: str):
    """JWKS — RFC 7517. Lazy-creates the resource keypair on first call."""
    resource = g.storage.get_resource(resource_id)
    if not resource:
        return aoai_not_found(f"Resource {resource_id!r} not found")

    keypair = ensure_keypair(g.storage, resource_id)
    body = jwks_doc_for_storage_keypair(keypair)
    emit(
        g.storage,
        tenant_id=ANONYMOUS_TENANT_ID,
        plane="data",
        operation="data.jwks.fetch",
        resource={"type": "resource", "id": resource_id},
        details={"keys": len(body["keys"])},
    )
    return jsonify(body)
