"""Embeddings: shape + dimensions + determinism."""


def test_single_input_embedding(client, resource, api_key, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/embeddings",
        json={"input": "hello world"},
        headers=api_key["headers"],
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["object"] == "list"
    assert len(body["data"]) == 1
    assert body["data"][0]["object"] == "embedding"
    assert len(body["data"][0]["embedding"]) == 1536
    assert body["model"] == deployment["model"]
    assert body["usage"]["prompt_tokens"] >= 0


def test_batch_input_embedding(client, resource, api_key, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/embeddings",
        json={"input": ["a", "b", "c"]},
        headers=api_key["headers"],
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["data"]) == 3
    assert all(len(d["embedding"]) == 1536 for d in body["data"])
    assert [d["index"] for d in body["data"]] == [0, 1, 2]


def test_embedding_deterministic(client, resource, api_key, deployment):
    """Same input → same vector across calls."""
    body_a = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/embeddings",
        json={"input": "stable"},
        headers=api_key["headers"],
    ).get_json()
    body_b = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/embeddings",
        json={"input": "stable"},
        headers=api_key["headers"],
    ).get_json()
    assert body_a["data"][0]["embedding"] == body_b["data"][0]["embedding"]


def test_embedding_missing_input_returns_400(client, resource, api_key, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/embeddings",
        json={},
        headers=api_key["headers"],
    )
    assert resp.status_code == 400
