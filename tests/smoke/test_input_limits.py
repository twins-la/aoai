"""Resource-bound + response-header hardening (security).

Covers TWAO-002 (limit clamp), TWAO-003 (MAX_CONTENT_LENGTH + embeddings
item cap), and TWAO-005 (security headers). Each test goes red if the
corresponding guard is removed from production.
"""


def test_list_logs_limit_is_clamped(client, tenant_headers):
    resp = client.get("/_twin/logs?limit=10000000", headers=tenant_headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["limit"] == 1000


def test_list_logs_negative_limit_floored(client, tenant_headers):
    resp = client.get("/_twin/logs?limit=-1", headers=tenant_headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["limit"] == 1


def test_security_headers_present(client, tenant_headers):
    resp = client.get("/_twin/logs", headers=tenant_headers)
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_embeddings_input_item_cap(client, resource, api_key, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/embeddings",
        json={"input": ["x"] * 2049},
        headers=api_key["headers"],
    )
    assert resp.status_code == 400, resp.get_data(as_text=True)


def test_oversize_request_body_rejected(client, resource, api_key, deployment):
    big = "x" * (4 * 1024 * 1024 + 1)
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/embeddings",
        data='{"input": "' + big + '"}',
        content_type="application/json",
        headers=api_key["headers"],
    )
    assert resp.status_code == 413, resp.get_data(as_text=True)
