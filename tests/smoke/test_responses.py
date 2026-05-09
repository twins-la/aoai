"""Responses API: happy path + auth failures + unknown deployment + missing input.

Mirrors the test footprint of `test_chat_completions.py`. The Responses
API names the deployment in the body's ``model`` field rather than the
URL path, so the route shape is `/openai/responses` — not under
`/openai/deployments/<id>/`.

Reference: https://learn.microsoft.com/en-us/azure/ai-services/openai/
reference#responses (retrieved 2026-05-09).
"""


def test_responses_happy_path(client, resource, api_key, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={"model": deployment["deployment_id"], "input": "hello"},
        query_string={"api-version": "2025-04-01-preview"},
        headers=api_key["headers"],
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["object"] == "response"
    assert body["id"].startswith("resp_")
    assert body["status"] == "completed"
    assert body["model"] == deployment["model"]
    output = body["output"]
    assert isinstance(output, list) and len(output) == 1
    item = output[0]
    assert item["type"] == "message"
    assert item["role"] == "assistant"
    assert item["content"][0]["type"] == "output_text"
    assert "echoing" in item["content"][0]["text"]
    usage = body["usage"]
    assert usage["input_tokens"] >= 0
    assert usage["output_tokens"] >= 0
    assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]


def test_responses_accepts_input_array(client, resource, api_key, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={
            "model": deployment["deployment_id"],
            "input": [
                {"type": "input_text", "text": "what is 2+2?"},
            ],
        },
        headers=api_key["headers"],
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "echoing: what is 2+2?" in body["output"][0]["content"][0]["text"]


def test_responses_no_api_key_returns_401(client, resource, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={"model": deployment["deployment_id"], "input": "hi"},
    )
    assert resp.status_code == 401


def test_responses_unknown_deployment_returns_json_404(
    client, resource, api_key
):
    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={"model": "nope", "input": "hi"},
        headers=api_key["headers"],
    )
    assert resp.status_code == 404
    assert resp.headers["Content-Type"].startswith("application/json")
    body = resp.get_json()
    assert body["error"]["code"] == "DeploymentNotFound"


def test_responses_missing_input_returns_400(
    client, resource, api_key, deployment
):
    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={"model": deployment["deployment_id"]},
        headers=api_key["headers"],
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"]["type"] == "invalid_request_error"


def test_responses_missing_model_returns_400(client, resource, api_key):
    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={"input": "hi"},
        headers=api_key["headers"],
    )
    assert resp.status_code == 400
