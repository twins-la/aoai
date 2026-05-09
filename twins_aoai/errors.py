"""HTTP error helpers — match the Azure OpenAI JSON error envelope.

Azure OpenAI returns ``{"error": {"code": <str>, "message": <str>,
"param": <nullable>, "type": <str>}}`` (retrieved 2026-05-08,
https://learn.microsoft.com/en-us/azure/ai-services/openai/reference).

The Twin Plane uses the platform-standard ``{"error": <str>}`` shape per
TWIN_PLANE.md.
"""

from typing import Optional

from flask import jsonify


def aoai_error(
    code: str,
    message: str,
    status: int,
    type_: str = "invalid_request_error",
    param: Optional[str] = None,
):
    """Azure OpenAI error envelope, as documented on /openai/* endpoints."""
    resp = jsonify({"error": {"code": code, "message": message, "param": param, "type": type_}})
    resp.status_code = status
    return resp


def aoai_unauthorized(message: str = "Access denied due to invalid subscription key or wrong API endpoint"):
    return aoai_error("401", message, 401, type_="AuthenticationError")


def aoai_not_found(message: str = "Resource not found"):
    return aoai_error("DeploymentNotFound", message, 404)


def aoai_path_not_found(message: str = "Resource not found"):
    """Generic 404 for unknown ``/openai/...`` paths.

    Distinct from :func:`aoai_not_found` (which uses ``DeploymentNotFound``)
    because the consumer's mental model differs: a missing deployment is a
    state error against a known endpoint, whereas a missing path means the
    endpoint itself is absent. Real Azure returns the generic ``NotFound``
    code in the latter case.
    """
    return aoai_error("NotFound", message, 404)


def aoai_bad_request(message: str):
    return aoai_error("BadRequest", message, 400)


def plane_error(message: str, status: int = 400):
    """Twin Plane error shape — ``{"error": "<msg>"}`` per TWIN_PLANE.md."""
    resp = jsonify({"error": message})
    resp.status_code = status
    return resp
