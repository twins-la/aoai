"""CRUD on resources, api_keys, deployments + cross-tenant isolation."""

import base64

from twins_local.tenants import (
    generate_tenant_id,
    generate_tenant_secret,
    hash_secret,
)


def _another_tenant(twin_app):
    tid = generate_tenant_id()
    secret = generate_tenant_secret()
    twin_app._tenant_store.create_tenant(
        tenant_id=tid,
        secret_hash=hash_secret(secret),
        friendly_name="Other Tenant",
    )
    creds = base64.b64encode(f"{tid}:{secret}".encode()).decode()
    return tid, {"Authorization": f"Basic {creds}"}


def test_create_resource_returns_base_url(client, tenant_headers):
    resp = client.post(
        "/_twin/resources",
        json={"friendly_name": "r1"},
        headers=tenant_headers,
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["resource_id"]
    assert body["base_url"].endswith(f"/{body['resource_id']}")


def test_explicit_resource_id_honoured(client, tenant_headers):
    resp = client.post(
        "/_twin/resources",
        json={"resource_id": "my-resource", "friendly_name": "r"},
        headers=tenant_headers,
    )
    assert resp.status_code == 201
    assert resp.get_json()["resource_id"] == "my-resource"


def test_resource_id_collision_returns_409(client, tenant_headers):
    client.post(
        "/_twin/resources",
        json={"resource_id": "dup"},
        headers=tenant_headers,
    )
    resp = client.post(
        "/_twin/resources",
        json={"resource_id": "dup"},
        headers=tenant_headers,
    )
    assert resp.status_code == 409


def test_list_resources_scoped_to_tenant(client, tenant_headers, resource):
    resp = client.get("/_twin/resources", headers=tenant_headers)
    assert resp.status_code == 200
    rids = [r["resource_id"] for r in resp.get_json()["resources"]]
    assert resource["resource_id"] in rids


def test_delete_resource(client, tenant_headers, resource):
    resp = client.delete(
        f"/_twin/resources/{resource['resource_id']}", headers=tenant_headers
    )
    assert resp.status_code == 200
    follow = client.get(
        "/_twin/resources", headers=tenant_headers
    )
    assert resource["resource_id"] not in [
        r["resource_id"] for r in follow.get_json()["resources"]
    ]


def test_create_api_key_returns_raw_key_once(
    client, tenant_headers, resource
):
    resp = client.post(
        f"/_twin/resources/{resource['resource_id']}/api_keys",
        json={"friendly_name": "k1"},
        headers=tenant_headers,
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["key_id"]
    assert body["api_key"]

    listing = client.get(
        f"/_twin/resources/{resource['resource_id']}/api_keys",
        headers=tenant_headers,
    ).get_json()["api_keys"]
    assert listing
    assert "api_key" not in listing[0]
    assert "key_hash" not in listing[0]


def test_create_deployment(client, tenant_headers, resource):
    resp = client.post(
        f"/_twin/resources/{resource['resource_id']}/deployments",
        json={"deployment_id": "d1", "model": "gpt-4o-mini"},
        headers=tenant_headers,
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["deployment_id"] == "d1"
    assert body["model"] == "gpt-4o-mini"


def test_deployment_requires_model(client, tenant_headers, resource):
    resp = client.post(
        f"/_twin/resources/{resource['resource_id']}/deployments",
        json={"deployment_id": "d2"},
        headers=tenant_headers,
    )
    assert resp.status_code == 400


def test_deployment_collision_409(client, tenant_headers, resource):
    client.post(
        f"/_twin/resources/{resource['resource_id']}/deployments",
        json={"deployment_id": "d3", "model": "gpt-4o"},
        headers=tenant_headers,
    )
    resp = client.post(
        f"/_twin/resources/{resource['resource_id']}/deployments",
        json={"deployment_id": "d3", "model": "gpt-4o"},
        headers=tenant_headers,
    )
    assert resp.status_code == 409


def test_cross_tenant_resource_isolation(client, twin_app, resource, tenant_headers):
    """Tenant B must not see or mutate Tenant A's resource."""
    _, b_headers = _another_tenant(twin_app)

    # B cannot see A's resource in its list.
    listing = client.get("/_twin/resources", headers=b_headers).get_json()
    assert resource["resource_id"] not in [
        r["resource_id"] for r in listing["resources"]
    ]

    # B cannot fetch A's api_keys (404 cloak).
    resp = client.get(
        f"/_twin/resources/{resource['resource_id']}/api_keys",
        headers=b_headers,
    )
    assert resp.status_code == 404

    # B cannot create a deployment in A's resource.
    resp = client.post(
        f"/_twin/resources/{resource['resource_id']}/deployments",
        json={"deployment_id": "evil", "model": "gpt-4o-mini"},
        headers=b_headers,
    )
    assert resp.status_code == 404

    # B cannot delete A's resource.
    resp = client.delete(
        f"/_twin/resources/{resource['resource_id']}", headers=b_headers
    )
    assert resp.status_code == 404
