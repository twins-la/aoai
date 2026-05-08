"""Shared fixtures for the AOAI twin smoke tests.

Spins the twin up in-process via Flask's test client, with SQLite storage
and an in-process SQLiteTenantStore. No external services needed.
"""

import base64
import os
import sys

import pytest

# Sibling host package may not be pip-installed during dev.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from twins_aoai.app import create_app  # noqa: E402
from twins_aoai_local.storage_sqlite import SQLiteStorage  # noqa: E402
from twins_local.tenants import (  # noqa: E402
    SQLiteTenantStore,
    ensure_default_tenant,
    generate_tenant_id,
    generate_tenant_secret,
    hash_secret,
)


@pytest.fixture
def tenant_store(tmp_path):
    store = SQLiteTenantStore(db_path=str(tmp_path / "tenants.sqlite3"))
    ensure_default_tenant(store)
    return store


@pytest.fixture
def twin_app(tmp_path, tenant_store):
    storage = SQLiteStorage(db_path=str(tmp_path / "test_twin.db"))
    app = create_app(
        storage=storage,
        tenants=tenant_store,
        config={"base_url": "http://localhost:8080"},
    )
    app.config["TESTING"] = True
    app._tenant_store = tenant_store  # type: ignore[attr-defined]
    return app


@pytest.fixture
def client(twin_app):
    return twin_app.test_client()


def _make_tenant_in(store):
    tenant_id = generate_tenant_id()
    tenant_secret = generate_tenant_secret()
    store.create_tenant(
        tenant_id=tenant_id,
        secret_hash=hash_secret(tenant_secret),
        friendly_name="Test Tenant",
    )
    return tenant_id, tenant_secret


def _basic_headers(tenant_id: str, tenant_secret: str) -> dict:
    creds = base64.b64encode(f"{tenant_id}:{tenant_secret}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def tenant(tenant_store):
    tenant_id, tenant_secret = _make_tenant_in(tenant_store)
    return {"tenant_id": tenant_id, "tenant_secret": tenant_secret}


@pytest.fixture
def tenant_headers(tenant):
    return _basic_headers(tenant["tenant_id"], tenant["tenant_secret"])


@pytest.fixture
def resource(client, tenant_headers):
    resp = client.post(
        "/_twin/resources",
        json={"friendly_name": "fixture-resource"},
        headers=tenant_headers,
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


@pytest.fixture
def api_key(client, tenant_headers, resource):
    resp = client.post(
        f"/_twin/resources/{resource['resource_id']}/api_keys",
        json={"friendly_name": "fixture-key"},
        headers=tenant_headers,
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    return {
        "key_id": body["key_id"],
        "api_key": body["api_key"],
        "headers": {"api-key": body["api_key"]},
    }


@pytest.fixture
def deployment(client, tenant_headers, resource):
    resp = client.post(
        f"/_twin/resources/{resource['resource_id']}/deployments",
        json={
            "deployment_id": "chat",
            "model": "gpt-4o-mini",
            "friendly_name": "fixture-deployment",
        },
        headers=tenant_headers,
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


@pytest.fixture
def aad_token(client, resource, api_key):
    """Acquire an AAD-shaped bearer via the per-resource token endpoint."""
    resp = client.post(
        f"/{resource['resource_id']}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": api_key["key_id"],
            "client_secret": api_key["api_key"],
            "scope": "https://cognitiveservices.azure.com/.default",
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    return {
        "access_token": body["access_token"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }
