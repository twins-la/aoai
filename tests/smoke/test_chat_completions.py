"""Chat completions: happy path + auth failures + unknown deployment."""


def test_chat_completion_happy_path(client, resource, api_key, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
        query_string={"api-version": "2024-10-21"},
        headers=api_key["headers"],
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert body["model"] == deployment["model"]
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert "echoing" in body["choices"][0]["message"]["content"]
    assert body["choices"][0]["finish_reason"] == "stop"
    usage = body["usage"]
    assert usage["prompt_tokens"] >= 0
    assert usage["completion_tokens"] >= 0
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_chat_completion_no_api_key_returns_401(client, resource, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["error"]["type"] == "AuthenticationError"


def test_chat_completion_wrong_api_key_returns_401(client, resource, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"api-key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_chat_completion_cross_resource_api_key_rejected(
    client, tenant_headers, resource, api_key
):
    """An api-key for resource A must not work on resource B even though
    they belong to the same tenant."""
    other = client.post(
        "/_twin/resources",
        json={"friendly_name": "other"},
        headers=tenant_headers,
    ).get_json()
    client.post(
        f"/_twin/resources/{other['resource_id']}/deployments",
        json={"deployment_id": "chat", "model": "gpt-4o-mini"},
        headers=tenant_headers,
    )

    resp = client.post(
        f"/{other['resource_id']}/openai/deployments/chat/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=api_key["headers"],
    )
    assert resp.status_code == 401


def test_chat_completion_unknown_deployment_returns_404(
    client, resource, api_key
):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/nope/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=api_key["headers"],
    )
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"]["code"] == "DeploymentNotFound"


def test_chat_completion_missing_messages_returns_400(
    client, resource, api_key, deployment
):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={},
        headers=api_key["headers"],
    )
    assert resp.status_code == 400


def test_unknown_resource_returns_404(client, api_key, deployment):
    resp = client.post(
        "/UNKNOWN/openai/deployments/chat/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=api_key["headers"],
    )
    assert resp.status_code == 404
