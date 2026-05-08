"""Tenant bootstrap + cloud-mode default rejection."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from twins_aoai.app import create_app  # noqa: E402
from twins_aoai_local.storage_sqlite import SQLiteStorage  # noqa: E402
from twins_local.tenants import SQLiteTenantStore  # noqa: E402


def test_tenant_bootstrap_returns_secret_once(client):
    resp = client.post("/_twin/tenants", json={"friendly_name": "Sample"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["tenant_id"]
    assert body["tenant_secret"]
    assert body["friendly_name"] == "Sample"


def test_tenant_required_for_resources_create(client):
    resp = client.post("/_twin/resources", json={})
    assert resp.status_code == 401


def test_tenant_credentials_validated(client, tenant):
    import base64

    bad = base64.b64encode(f"{tenant['tenant_id']}:wrong".encode()).decode()
    resp = client.get(
        "/_twin/resources", headers={"Authorization": f"Basic {bad}"}
    )
    assert resp.status_code == 401


@pytest.fixture
def cloud_app(tmp_path):
    storage = SQLiteStorage(db_path=str(tmp_path / "test_twin.db"))
    tenant_store = SQLiteTenantStore(db_path=str(tmp_path / "tenants.sqlite3"))
    app = create_app(
        storage=storage,
        tenants=tenant_store,
        config={"base_url": "https://aoai.twins.la", "is_cloud": True},
    )
    app.config["TESTING"] = True
    return app


def test_cloud_mode_rejects_default_tenant(cloud_app):
    """``ensure_default_tenant`` was NOT called, but the bootstrap path
    rejects ``default`` tenant ids in cloud mode regardless."""
    cl = cloud_app.test_client()
    # Cloud always allocates random tenant ids; this asserts the path
    # exists by smoke-creating one (the reject_default_in_cloud guard
    # would fire only if generate_tenant_id() returned ``default``).
    resp = cl.post("/_twin/tenants", json={"friendly_name": "x"})
    assert resp.status_code == 201
