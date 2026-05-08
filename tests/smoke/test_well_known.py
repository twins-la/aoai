"""Per-resource OpenID discovery + JWKS publication."""


def test_openid_configuration(client, resource):
    resp = client.get(f"/{resource['resource_id']}/.well-known/openid-configuration")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["issuer"].endswith(f"/{resource['resource_id']}/v2.0")
    assert body["jwks_uri"].endswith(
        f"/{resource['resource_id']}/.well-known/jwks.json"
    )
    assert body["token_endpoint"].endswith(
        f"/{resource['resource_id']}/oauth2/v2.0/token"
    )
    assert "RS256" in body["id_token_signing_alg_values_supported"]


def test_openid_configuration_unknown_resource_404(client):
    resp = client.get("/UNKNOWN/.well-known/openid-configuration")
    assert resp.status_code == 404


def test_jwks_shape(client, resource):
    resp = client.get(f"/{resource['resource_id']}/.well-known/jwks.json")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "keys" in body and len(body["keys"]) >= 1
    key = body["keys"][0]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["alg"] == "RS256"
    assert key["kid"]
    assert key["n"]
    assert key["e"]


def test_kid_stable_across_requests(client, resource):
    a = client.get(
        f"/{resource['resource_id']}/.well-known/jwks.json"
    ).get_json()["keys"][0]["kid"]
    b = client.get(
        f"/{resource['resource_id']}/.well-known/jwks.json"
    ).get_json()["keys"][0]["kid"]
    assert a == b


def test_jwks_per_resource_isolation(client, tenant_headers):
    """Two resources must publish distinct kids."""
    r1 = client.post(
        "/_twin/resources",
        json={"friendly_name": "r1"},
        headers=tenant_headers,
    ).get_json()
    r2 = client.post(
        "/_twin/resources",
        json={"friendly_name": "r2"},
        headers=tenant_headers,
    ).get_json()
    k1 = client.get(
        f"/{r1['resource_id']}/.well-known/jwks.json"
    ).get_json()["keys"][0]["kid"]
    k2 = client.get(
        f"/{r2['resource_id']}/.well-known/jwks.json"
    ).get_json()["keys"][0]["kid"]
    assert k1 != k2
