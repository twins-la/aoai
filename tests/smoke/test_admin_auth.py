"""Admin (Bearer token) auth — cross-tenant log visibility."""

import base64
import os
import sys

import pytest

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
def admin_token():
    return "operator-admin-secret"


@pytest.fixture
def admin_app(tmp_path, admin_token):
    storage = SQLiteStorage(db_path=str(tmp_path / "test_twin.db"))
    tenant_store = SQLiteTenantStore(db_path=str(tmp_path / "tenants.sqlite3"))
    ensure_default_tenant(tenant_store)
    app = create_app(
        storage=storage,
        tenants=tenant_store,
        config={"base_url": "http://localhost:8080", "admin_token": admin_token},
    )
    app.config["TESTING"] = True
    app._tenant_store = tenant_store  # type: ignore[attr-defined]
    return app


@pytest.fixture
def admin_client(admin_app):
    return admin_app.test_client()


def _make_tenant(app):
    tenant_id = generate_tenant_id()
    tenant_secret = generate_tenant_secret()
    app._tenant_store.create_tenant(  # type: ignore[attr-defined]
        tenant_id=tenant_id,
        secret_hash=hash_secret(tenant_secret),
        friendly_name="t",
    )
    creds = base64.b64encode(f"{tenant_id}:{tenant_secret}".encode()).decode()
    return tenant_id, {"Authorization": f"Basic {creds}"}


def test_admin_lists_logs_across_tenants(admin_app, admin_client, admin_token):
    a_id, a_headers = _make_tenant(admin_app)
    b_id, b_headers = _make_tenant(admin_app)

    admin_client.post("/_twin/resources", json={}, headers=a_headers)
    admin_client.post("/_twin/resources", json={}, headers=b_headers)

    resp = admin_client.get(
        "/_twin/logs", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    log_tenants = {r["tenant_id"] for r in resp.get_json()["logs"]}
    assert a_id in log_tenants
    assert b_id in log_tenants


def test_tenant_only_sees_its_own_logs(admin_app, admin_client):
    a_id, a_headers = _make_tenant(admin_app)
    b_id, b_headers = _make_tenant(admin_app)

    admin_client.post("/_twin/resources", json={}, headers=a_headers)
    admin_client.post("/_twin/resources", json={}, headers=b_headers)

    a_logs = admin_client.get(
        "/_twin/logs", headers=a_headers
    ).get_json()["logs"]
    assert a_logs
    assert all(r["tenant_id"] == a_id for r in a_logs)


def test_wrong_admin_token_rejected(admin_client):
    resp = admin_client.get(
        "/_twin/logs", headers={"Authorization": "Bearer not-the-admin"}
    )
    assert resp.status_code == 401
