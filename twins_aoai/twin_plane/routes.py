"""Twin Plane management API for the AOAI twin.

Served at ``/_twin/`` per TWIN_PLANE.md. The control plane (Azure ARM)
is intentionally not emulated; instead this surface exposes:

  * Resources — tenant-scoped namespace, ``<resource>`` URL segment.
  * Api keys — per-resource keys for the data plane's ``api-key`` header.
  * Deployments — per-resource ``<deployment>`` mapping to a model.

Resource-scoped routes verify the resource belongs to the authenticated
tenant; cross-tenant references return 404 (no leakage).
"""

import logging

from flask import Blueprint, Response, g, jsonify, request

from twins_local.tenants import (
    OPERATOR_ADMIN_TENANT_ID,
    generate_tenant_id,
    generate_tenant_secret,
    hash_secret,
    reject_default_in_cloud,
)

from .. import __version__
from ..errors import plane_error
from ..logs import emit
from ..models import now_iso_z
from ..sids import (
    generate_api_key,
    generate_api_key_id,
    generate_deployment_id,
    generate_feedback_id,
    generate_resource_id,
    hash_api_key,
)
from .auth import require_admin, require_tenant, require_tenant_or_admin

logger = logging.getLogger(__name__)

twin_plane_bp = Blueprint("twin_plane", __name__, url_prefix="/_twin")


def _scope_tenant_id() -> str:
    return OPERATOR_ADMIN_TENANT_ID if g.get("is_admin") else g.tenant_id


def _resource_base_url(resource_id: str) -> str:
    return f"{g.base_url.rstrip('/')}/{resource_id}"


def _ensure_tenant_owns_resource(resource_id: str):
    """Resolve a resource and verify ownership; returns row or error response."""
    resource = g.storage.get_resource(resource_id)
    if not resource:
        return None, plane_error("Resource not found", 404)
    if not g.get("is_admin") and resource["tenant_id"] != g.tenant_id:
        # Cross-tenant access — return 404 to avoid leaking existence.
        return None, plane_error("Resource not found", 404)
    return resource, None


# ---- Public info endpoints ----


@twin_plane_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "twin": "aoai", "version": __version__})


@twin_plane_bp.route("/scenarios", methods=["GET"])
def scenarios():
    return jsonify(
        {
            "scenarios": [
                {
                    "name": "chat-completions",
                    "status": "supported",
                    "description": (
                        "Azure OpenAI chat-completions data plane. Accepts "
                        "POST /<resource>/openai/deployments/<deployment>/"
                        "chat/completions with synthetic responses; "
                        "streaming SSE supported via stream=true."
                    ),
                    "capabilities": [
                        "non_streaming_chat",
                        "streaming_chat_sse",
                        "synthetic_deterministic_text",
                    ],
                },
                {
                    "name": "embeddings",
                    "status": "supported",
                    "description": (
                        "Azure OpenAI embeddings data plane. Returns "
                        "deterministic synthetic vectors so identical "
                        "inputs produce identical outputs across runs."
                    ),
                    "capabilities": [
                        "single_input_embedding",
                        "batch_input_embedding",
                        "deterministic_vectors",
                    ],
                },
                {
                    "name": "dual-auth",
                    "status": "supported",
                    "description": (
                        "Both api-key and AAD-bearer auth paths are "
                        "accepted on every data-plane endpoint. The twin "
                        "issues AAD-shaped tokens at "
                        "/<resource>/oauth2/v2.0/token signed by a "
                        "per-resource keypair."
                    ),
                    "capabilities": [
                        "api_key_header_auth",
                        "aad_bearer_auth",
                        "per_resource_jwks",
                        "oauth_client_credentials_token_issue",
                    ],
                },
            ]
        }
    )


@twin_plane_bp.route("/references", methods=["GET"])
def references():
    return jsonify(
        {
            "references": [
                {
                    "title": "Azure OpenAI Service REST API reference",
                    "url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/reference",
                    "retrieved": "2026-05-08",
                },
                {
                    "title": "Azure OpenAI: Migration to OpenAI Python v1.x",
                    "url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/migration",
                    "retrieved": "2026-05-08",
                },
                {
                    "title": "Microsoft identity platform: v2.0 protocols",
                    "url": "https://learn.microsoft.com/en-us/azure/active-directory/develop/active-directory-v2-protocols",
                    "retrieved": "2026-05-08",
                },
                {
                    "title": "RFC 7517 — JSON Web Key (JWK)",
                    "url": "https://datatracker.ietf.org/doc/html/rfc7517",
                    "retrieved": "2026-05-08",
                },
                {
                    "title": "RFC 7519 — JSON Web Token (JWT)",
                    "url": "https://datatracker.ietf.org/doc/html/rfc7519",
                    "retrieved": "2026-05-08",
                },
                {
                    "title": "RFC 7638 — JSON Web Key (JWK) Thumbprint",
                    "url": "https://datatracker.ietf.org/doc/html/rfc7638",
                    "retrieved": "2026-05-08",
                },
            ]
        }
    )


@twin_plane_bp.route("/settings", methods=["GET"])
def get_settings():
    return jsonify(
        {"twin": "aoai", "version": __version__, "base_url": g.base_url}
    )


@twin_plane_bp.route("/agent-instructions", methods=["GET"])
def agent_instructions_endpoint():
    """Plain-text agent instructions; same body the explainer page embeds."""
    from ..explainer import AGENT_INSTRUCTIONS

    return Response(AGENT_INSTRUCTIONS, mimetype="text/plain")


# ---- Tenants (bootstrap) ----


@twin_plane_bp.route("/tenants", methods=["POST"])
def create_tenant():
    payload = request.get_json(silent=True) or {}
    friendly_name = payload.get("friendly_name", "") if isinstance(payload, dict) else ""

    tenant_id = generate_tenant_id()
    if g.is_cloud:
        reject_default_in_cloud(tenant_id)

    tenant_secret = generate_tenant_secret()
    tenant = g.tenants.create_tenant(
        tenant_id=tenant_id,
        secret_hash=hash_secret(tenant_secret),
        friendly_name=friendly_name,
    )

    emit(
        g.storage,
        tenant_id=tenant_id,
        plane="twin",
        operation="twin.tenant.create",
        resource={"type": "tenant", "id": tenant_id},
    )

    resp = jsonify(
        {
            "tenant_id": tenant_id,
            "tenant_secret": tenant_secret,
            "friendly_name": tenant["friendly_name"],
            "created_at": tenant["created_at"],
        }
    )
    resp.status_code = 201
    return resp


# ---- Logs ----


@twin_plane_bp.route("/logs", methods=["GET"])
@require_tenant_or_admin
def list_logs():
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    tenant_id = None if g.is_admin else g.tenant_id
    entries = g.storage.list_logs(limit=limit, offset=offset, tenant_id=tenant_id)
    return jsonify({"logs": entries, "limit": limit, "offset": offset})


# ---- Resources ----


def _resource_public(row: dict) -> dict:
    return {
        "resource_id": row["resource_id"],
        "tenant_id": row["tenant_id"],
        "friendly_name": row.get("friendly_name", ""),
        "base_url": _resource_base_url(row["resource_id"]),
    }


@twin_plane_bp.route("/resources", methods=["POST"])
@require_tenant
def create_resource():
    payload = request.get_json(silent=True) or {}
    resource_id = payload.get("resource_id") or generate_resource_id()
    if g.storage.get_resource(resource_id):
        return plane_error(f"Resource {resource_id!r} already exists", 409)
    row = g.storage.create_resource(
        tenant_id=g.tenant_id,
        resource_id=resource_id,
        friendly_name=payload.get("friendly_name", ""),
    )
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="twin",
        operation="twin.resource.create",
        resource={"type": "resource", "id": resource_id},
    )
    resp = jsonify(_resource_public(row))
    resp.status_code = 201
    return resp


@twin_plane_bp.route("/resources", methods=["GET"])
@require_tenant_or_admin
def list_resources():
    tenant_id = None if g.is_admin else g.tenant_id
    rows = g.storage.list_resources(tenant_id=tenant_id)
    return jsonify({"resources": [_resource_public(r) for r in rows]})


@twin_plane_bp.route("/resources/<resource_id>", methods=["DELETE"])
@require_tenant
def delete_resource(resource_id: str):
    resource, err = _ensure_tenant_owns_resource(resource_id)
    if err is not None:
        return err
    g.storage.delete_resource(resource_id)
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="twin",
        operation="twin.resource.delete",
        resource={"type": "resource", "id": resource_id},
    )
    return jsonify({"deleted": True, "resource_id": resource_id})


# ---- Api keys ----


def _api_key_masked(row: dict) -> dict:
    return {
        "key_id": row["key_id"],
        "resource_id": row["resource_id"],
        "friendly_name": row.get("friendly_name", ""),
        "date_created": row.get("date_created", ""),
    }


@twin_plane_bp.route("/resources/<resource_id>/api_keys", methods=["POST"])
@require_tenant
def create_api_key(resource_id: str):
    resource, err = _ensure_tenant_owns_resource(resource_id)
    if err is not None:
        return err
    payload = request.get_json(silent=True) or {}
    key_id = generate_api_key_id()
    raw_key = generate_api_key()
    row = g.storage.create_api_key(
        resource_id=resource_id,
        key_id=key_id,
        key_hash=hash_api_key(raw_key),
        friendly_name=payload.get("friendly_name", ""),
    )
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="twin",
        operation="twin.api_key.create",
        resource={"type": "api_key", "id": key_id},
        details={"resource_id": resource_id},
    )
    resp = jsonify(
        {
            "key_id": key_id,
            "api_key": raw_key,
            "resource_id": resource_id,
            "friendly_name": row.get("friendly_name", ""),
        }
    )
    resp.status_code = 201
    return resp


@twin_plane_bp.route("/resources/<resource_id>/api_keys", methods=["GET"])
@require_tenant
def list_api_keys(resource_id: str):
    _, err = _ensure_tenant_owns_resource(resource_id)
    if err is not None:
        return err
    rows = g.storage.list_api_keys(resource_id=resource_id)
    return jsonify({"api_keys": [_api_key_masked(r) for r in rows]})


@twin_plane_bp.route(
    "/resources/<resource_id>/api_keys/<key_id>", methods=["DELETE"]
)
@require_tenant
def delete_api_key(resource_id: str, key_id: str):
    _, err = _ensure_tenant_owns_resource(resource_id)
    if err is not None:
        return err
    rows = g.storage.list_api_keys(resource_id=resource_id)
    if not any(r["key_id"] == key_id for r in rows):
        return plane_error("API key not found", 404)
    g.storage.delete_api_key(key_id)
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="twin",
        operation="twin.api_key.delete",
        resource={"type": "api_key", "id": key_id},
        details={"resource_id": resource_id},
    )
    return jsonify({"deleted": True, "key_id": key_id})


# ---- Deployments ----


def _deployment_public(row: dict) -> dict:
    return {
        "resource_id": row["resource_id"],
        "deployment_id": row["deployment_id"],
        "model": row["model"],
        "friendly_name": row.get("friendly_name", ""),
    }


@twin_plane_bp.route("/resources/<resource_id>/deployments", methods=["POST"])
@require_tenant
def create_deployment(resource_id: str):
    resource, err = _ensure_tenant_owns_resource(resource_id)
    if err is not None:
        return err
    payload = request.get_json(silent=True) or {}
    model = payload.get("model")
    if not model or not isinstance(model, str):
        return plane_error("'model' is required", 400)
    deployment_id = payload.get("deployment_id") or generate_deployment_id()
    existing = g.storage.get_deployment(
        resource_id=resource_id, deployment_id=deployment_id
    )
    if existing:
        return plane_error(
            f"Deployment {deployment_id!r} already exists in this resource", 409
        )
    row = g.storage.create_deployment(
        resource_id=resource_id,
        deployment_id=deployment_id,
        model=model,
        friendly_name=payload.get("friendly_name", ""),
    )
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="twin",
        operation="twin.deployment.create",
        resource={"type": "deployment", "id": deployment_id},
        details={"resource_id": resource_id, "model": model},
    )
    resp = jsonify(_deployment_public(row))
    resp.status_code = 201
    return resp


@twin_plane_bp.route("/resources/<resource_id>/deployments", methods=["GET"])
@require_tenant
def list_deployments(resource_id: str):
    _, err = _ensure_tenant_owns_resource(resource_id)
    if err is not None:
        return err
    rows = g.storage.list_deployments(resource_id=resource_id)
    return jsonify({"deployments": [_deployment_public(r) for r in rows]})


@twin_plane_bp.route(
    "/resources/<resource_id>/deployments/<deployment_id>", methods=["DELETE"]
)
@require_tenant
def delete_deployment(resource_id: str, deployment_id: str):
    _, err = _ensure_tenant_owns_resource(resource_id)
    if err is not None:
        return err
    existing = g.storage.get_deployment(
        resource_id=resource_id, deployment_id=deployment_id
    )
    if not existing:
        return plane_error("Deployment not found", 404)
    g.storage.delete_deployment(
        resource_id=resource_id, deployment_id=deployment_id
    )
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="twin",
        operation="twin.deployment.delete",
        resource={"type": "deployment", "id": deployment_id},
        details={"resource_id": resource_id},
    )
    return jsonify({"deleted": True, "deployment_id": deployment_id})


# ---- Feedback ----


@twin_plane_bp.route("/feedback", methods=["POST"])
@require_tenant
def submit_feedback():
    payload = request.get_json(silent=True) or {}
    body = payload.get("body")
    if not body or not isinstance(body, str) or not body.strip():
        return plane_error("'body' is required", 400)

    feedback_id = generate_feedback_id()
    now = now_iso_z()
    record = g.storage.create_feedback(
        {
            "id": feedback_id,
            "tenant_id": g.tenant_id,
            "body": body.strip(),
            "category": payload.get("category", ""),
            "context": payload.get("context", {}),
            "status": "pending",
            "date_created": now,
            "date_updated": now,
        }
    )
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="twin",
        operation="twin.feedback.submit",
        resource={"type": "feedback", "id": feedback_id},
        details={"category": record["category"]},
    )
    return jsonify(record), 201


@twin_plane_bp.route("/feedback", methods=["GET"])
@require_tenant_or_admin
def list_feedback():
    status = request.args.get("status")
    tenant_id = None if g.is_admin else g.tenant_id
    items = g.storage.list_feedback(status=status, tenant_id=tenant_id)
    return jsonify({"feedback": items})
