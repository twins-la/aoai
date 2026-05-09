"""Sweep test: unknown ``/<resource>/openai/...`` paths return Azure-shaped JSON 404.

Real Azure OpenAI returns ``Content-Type: application/json`` on every
unknown path under ``/openai/``. Without this, Flask falls through to its
default HTML 404, which Azure SDKs cannot parse — the next missing
endpoint is invisible (cf. twins-la/aoai#1, where the absent Responses API
shipped silently for the same reason).

These assertions are deliberately path-agnostic: they sweep the rendered
output for the canonical envelope rather than enumerating specific
expected misses, so adding a new bogus probe doesn't drift from the test.
"""

import pytest


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "openai/foo"),
        ("POST", "openai/deployments/nope/wrong-thing"),
        ("GET", "openai/Foo"),  # mixed case
        ("POST", "openai/responses-misspell"),
        ("DELETE", "openai/random/nested/path"),
        ("PUT", "openai/files/abc"),
    ],
)
def test_unknown_openai_path_returns_json_404(client, resource, method, path):
    full = f"/{resource['resource_id']}/{path}"
    resp = client.open(
        full,
        method=method,
        json={"foo": "bar"} if method in ("POST", "PUT", "PATCH") else None,
    )
    assert resp.status_code == 404, f"{method} {full} got {resp.status_code}"
    assert resp.headers["Content-Type"].startswith("application/json"), (
        f"{method} {full} returned {resp.headers.get('Content-Type')!r} "
        f"body={resp.get_data(as_text=True)[:200]!r}"
    )
    body = resp.get_json()
    assert body is not None and "error" in body
    assert body["error"]["code"] == "NotFound"
    assert body["error"]["type"] == "invalid_request_error"


def test_unknown_openai_path_no_html_leak(client, resource):
    """Belt-and-braces: HTML 404 must never appear on any /openai/* miss."""
    resp = client.get(f"/{resource['resource_id']}/openai/literally-anything")
    body = resp.get_data(as_text=True)
    assert "<!doctype" not in body.lower()
    assert "<html" not in body.lower()


def test_unknown_openai_path_with_valid_auth_still_404(
    client, resource, api_key
):
    """Auth doesn't change behavior — endpoint absence is the gating factor."""
    resp = client.get(
        f"/{resource['resource_id']}/openai/files/list",
        headers=api_key["headers"],
    )
    assert resp.status_code == 404
    assert resp.headers["Content-Type"].startswith("application/json")
    body = resp.get_json()
    assert body["error"]["code"] == "NotFound"


def test_known_openai_paths_still_match(client, resource, api_key, deployment):
    """Verify the catch-all doesn't shadow the real data-plane routes."""
    chat = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=api_key["headers"],
    )
    assert chat.status_code == 200, chat.get_data(as_text=True)

    responses = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={"model": deployment["deployment_id"], "input": "hi"},
        headers=api_key["headers"],
    )
    assert responses.status_code == 200, responses.get_data(as_text=True)
