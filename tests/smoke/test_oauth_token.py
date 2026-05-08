"""Per-resource OAuth client_credentials token endpoint."""


def test_token_happy_path(client, resource, api_key):
    resp = client.post(
        f"/{resource['resource_id']}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": api_key["key_id"],
            "client_secret": api_key["api_key"],
            "scope": "https://cognitiveservices.azure.com/.default",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]
    assert body["expires_in"] == 3600


def test_token_invalid_client_returns_aad_shaped_error(client, resource):
    resp = client.post(
        f"/{resource['resource_id']}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "wrong",
            "client_secret": "wrong",
        },
    )
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["error"] == "invalid_client"
    assert "error_description" in body
    assert "trace_id" in body


def test_token_unsupported_grant_type(client, resource):
    resp = client.post(
        f"/{resource['resource_id']}/oauth2/v2.0/token",
        data={"grant_type": "password"},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "unsupported_grant_type"


def test_token_unknown_resource_returns_404(client):
    resp = client.post(
        "/UNKNOWN/oauth2/v2.0/token",
        data={"grant_type": "client_credentials", "client_id": "x", "client_secret": "y"},
    )
    assert resp.status_code == 404
