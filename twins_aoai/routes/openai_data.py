"""Azure OpenAI data plane — chat / completions / embeddings.

URL shape (path-prefixed resource):

    POST /<resource>/openai/deployments/<deployment>/chat/completions
    POST /<resource>/openai/deployments/<deployment>/completions
    POST /<resource>/openai/deployments/<deployment>/embeddings

All routes apply :func:`require_resource` then :func:`require_aoai_data_auth`,
so reaching the body handler implies (a) the resource exists, (b) auth
succeeded by either api-key or AAD bearer, and (c) ``g.tenant_id`` is the
authenticated tenant.

Inference is **synthetic**: the twin never calls a real model. Token
counts are approximated; embeddings are deterministic vectors.
"""

import json
from typing import Iterator

from flask import Blueprint, Response, g, request

from ..auth import require_aoai_data_auth, require_resource
from ..errors import aoai_bad_request, aoai_not_found, aoai_path_not_found
from ..logs import emit
from ..models import (
    build_chat_completion,
    build_completion,
    build_embedding_response,
    build_response,
    build_synthetic_chat_text,
    build_synthetic_response_text,
    count_tokens_text,
    now_unix,
    synthetic_embedding,
)
from ..sids import generate_completion_id, generate_request_id, generate_response_id

data_bp = Blueprint("openai_data", __name__)


def _persist_request(*, deployment_id: str, kind: str, request_body: dict, response_body: dict) -> str:
    """Record a request/response history row. Returns the row id."""
    rid = generate_request_id()
    g.storage.create_request(
        {
            "id": rid,
            "tenant_id": g.tenant_id,
            "resource_id": g.resource["resource_id"],
            "deployment_id": deployment_id,
            "kind": kind,
            "request_json": json.dumps(request_body, default=str),
            "response_json": json.dumps(response_body, default=str),
            "date_created": "",
        }
    )
    return rid


def _resolve_deployment(deployment_id: str):
    """Return the deployment row or send the AOAI 404 envelope."""
    deployment = g.storage.get_deployment(
        resource_id=g.resource["resource_id"], deployment_id=deployment_id
    )
    if not deployment:
        return None, aoai_not_found(
            f"The API deployment for this resource does not exist: {deployment_id!r}"
        )
    return deployment, None


def _stream_chat_completion(
    *, completion_id: str, model: str, content_text: str
) -> Iterator[bytes]:
    """Yield SSE chunks split into roughly word-sized deltas."""
    tokens = content_text.split(" ") if content_text else [""]
    base = {
        "id": f"chatcmpl-{completion_id}",
        "object": "chat.completion.chunk",
        "created": now_unix(),
        "model": model,
    }

    # Initial role chunk — matches Azure OpenAI's documented stream order.
    first = dict(base)
    first["choices"] = [
        {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
    ]
    yield f"data: {json.dumps(first)}\n\n".encode("utf-8")

    for i, tok in enumerate(tokens):
        delta_text = tok if i == 0 else f" {tok}"
        chunk = dict(base)
        chunk["choices"] = [
            {"index": 0, "delta": {"content": delta_text}, "finish_reason": None}
        ]
        yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")

    final = dict(base)
    final["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    yield f"data: {json.dumps(final)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"


@data_bp.route(
    "/<resource_id>/openai/deployments/<deployment_id>/chat/completions",
    methods=["POST"],
)
@require_resource
@require_aoai_data_auth
def chat_completions(resource_id: str, deployment_id: str):
    deployment, err = _resolve_deployment(deployment_id)
    if err is not None:
        return err

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return aoai_bad_request("Request body must be a JSON object")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return aoai_bad_request("'messages' is required and must be a non-empty list")

    model = deployment["model"]
    content_text = build_synthetic_chat_text(messages, model)
    completion_id = generate_completion_id()

    api_version = request.args.get("api-version", "")

    if body.get("stream"):
        # Persist a synthetic non-streaming snapshot for inspection so
        # log-driven dashboards have one row per request, even on stream.
        snapshot = build_chat_completion(
            completion_id=completion_id,
            model=model,
            content_text=content_text,
            prompt_tokens=sum(
                count_tokens_text(json.dumps(m, default=str)) for m in messages
            ),
            completion_tokens=count_tokens_text(content_text),
        )
        _persist_request(
            deployment_id=deployment_id,
            kind="chat.completion.stream",
            request_body=body,
            response_body=snapshot,
        )
        emit(
            g.storage,
            tenant_id=g.tenant_id,
            plane="data",
            operation="data.chat.completion",
            resource={"type": "deployment", "id": deployment_id},
            details={
                "model": model,
                "stream": True,
                "api_version": api_version,
            },
        )
        return Response(
            _stream_chat_completion(
                completion_id=completion_id, model=model, content_text=content_text
            ),
            mimetype="text/event-stream",
        )

    response = build_chat_completion(
        completion_id=completion_id,
        model=model,
        content_text=content_text,
        prompt_tokens=sum(
            count_tokens_text(json.dumps(m, default=str)) for m in messages
        ),
        completion_tokens=count_tokens_text(content_text),
    )
    _persist_request(
        deployment_id=deployment_id,
        kind="chat.completion",
        request_body=body,
        response_body=response,
    )
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="data",
        operation="data.chat.completion",
        resource={"type": "deployment", "id": deployment_id},
        details={"model": model, "stream": False, "api_version": api_version},
    )
    return response


@data_bp.route(
    "/<resource_id>/openai/deployments/<deployment_id>/completions",
    methods=["POST"],
)
@require_resource
@require_aoai_data_auth
def completions(resource_id: str, deployment_id: str):
    """Legacy completions surface — Azure still ships it."""
    deployment, err = _resolve_deployment(deployment_id)
    if err is not None:
        return err

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return aoai_bad_request("Request body must be a JSON object")
    prompt = body.get("prompt", "")
    if isinstance(prompt, list):
        prompt_text = " ".join(str(p) for p in prompt)
    else:
        prompt_text = str(prompt)

    model = deployment["model"]
    text = f"[aoai-twin:{model}] echoing legacy: {prompt_text[:200]}"
    completion_id = generate_completion_id()
    response = build_completion(
        completion_id=completion_id,
        model=model,
        text=text,
        prompt_tokens=count_tokens_text(prompt_text),
        completion_tokens=count_tokens_text(text),
    )
    _persist_request(
        deployment_id=deployment_id,
        kind="completion",
        request_body=body,
        response_body=response,
    )
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="data",
        operation="data.completions.create",
        resource={"type": "deployment", "id": deployment_id},
        details={"model": model},
    )
    return response


@data_bp.route(
    "/<resource_id>/openai/responses",
    methods=["POST"],
)
@require_resource
@require_aoai_data_auth
def responses(resource_id: str):
    """Azure OpenAI Responses API.

    Reference: https://learn.microsoft.com/en-us/azure/ai-services/openai/
    reference#responses (retrieved 2026-05-09). Unlike chat/completions,
    the deployment is named in the body's ``model`` field rather than the
    URL path; the twin treats that field as the deployment identifier.
    """
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return aoai_bad_request("Request body must be a JSON object")

    model = body.get("model")
    if not isinstance(model, str) or not model:
        return aoai_bad_request("'model' is required")

    raw_input = body.get("input")
    if raw_input is None:
        return aoai_bad_request("'input' is required")
    if not isinstance(raw_input, (str, list)):
        return aoai_bad_request("'input' must be a string or list of input items")

    deployment, err = _resolve_deployment(model)
    if err is not None:
        return err

    api_version = request.args.get("api-version", "")
    output_text = build_synthetic_response_text(raw_input, deployment["model"])
    response_id = generate_response_id()

    response = build_response(
        response_id=response_id,
        model=deployment["model"],
        output_text=output_text,
        input_tokens=count_tokens_text(json.dumps(raw_input, default=str)),
        output_tokens=count_tokens_text(output_text),
    )
    _persist_request(
        deployment_id=deployment["deployment_id"],
        kind="response",
        request_body=body,
        response_body=response,
    )
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="data",
        operation="data.responses.create",
        resource={"type": "deployment", "id": deployment["deployment_id"]},
        details={"model": deployment["model"], "api_version": api_version},
    )
    return response


@data_bp.route(
    "/<resource_id>/openai/deployments/<deployment_id>/embeddings",
    methods=["POST"],
)
@require_resource
@require_aoai_data_auth
def embeddings(resource_id: str, deployment_id: str):
    deployment, err = _resolve_deployment(deployment_id)
    if err is not None:
        return err

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return aoai_bad_request("Request body must be a JSON object")
    raw_input = body.get("input")
    if raw_input is None:
        return aoai_bad_request("'input' is required")
    if isinstance(raw_input, str):
        items = [raw_input]
    elif isinstance(raw_input, list):
        items = [str(x) for x in raw_input]
        if not items:
            return aoai_bad_request("'input' must not be an empty list")
    else:
        return aoai_bad_request("'input' must be a string or list of strings")

    model = deployment["model"]
    vectors = [synthetic_embedding(text) for text in items]
    prompt_tokens = sum(count_tokens_text(t) for t in items)
    response = build_embedding_response(
        model=model, vectors=vectors, prompt_tokens=prompt_tokens
    )
    _persist_request(
        deployment_id=deployment_id,
        kind="embeddings",
        request_body=body,
        response_body=response,
    )
    emit(
        g.storage,
        tenant_id=g.tenant_id,
        plane="data",
        operation="data.embeddings.create",
        resource={"type": "deployment", "id": deployment_id},
        details={"model": model, "n_inputs": len(items)},
    )
    return response


# ---- Catch-all for unknown /<resource>/openai/* paths ------------------
#
# Without this, Flask falls through to its default HTML 404. Real Azure
# OpenAI returns a JSON envelope on every unknown path under /openai/...
# so consumer SDKs can parse the error. Registered last so the more
# specific data-plane routes above always win in URL matching.
#
# Intentionally NO auth decorators: real Azure returns the same 404
# envelope whether the caller is authenticated or not (in fact it
# doesn't get far enough to authenticate against an absent endpoint).


@data_bp.route(
    "/<resource_id>/openai/<path:rest>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
def unknown_openai_path(resource_id: str, rest: str):
    storage = getattr(g, "storage", None)
    if storage is not None:
        emit(
            storage,
            tenant_id=getattr(g, "tenant_id", "__anonymous__"),
            plane="data",
            operation="data.unknown.path",
            resource={"type": "openai_path", "id": rest},
            outcome="failure",
            reason="path-not-implemented",
            details={"method": request.method, "path": f"/{resource_id}/openai/{rest}"},
        )
    return aoai_path_not_found(
        f"The API endpoint /{resource_id}/openai/{rest} does not exist"
    )
