"""Flask application factory for the Azure OpenAI twin.

A single Flask app serves the data plane (path-prefixed by resource),
the per-resource AAD discovery + token endpoints, the Twin Plane, and
the explainer page. Hosts inject a ``TwinStorage`` and a ``TenantStore``;
behavioural differences between local (SQLite) and cloud (Postgres) come
from those injected dependencies plus the ``is_cloud`` flag, never from
twin code branching on the host type.

The control plane (Azure ARM) is intentionally not emulated. Operators
provision resources, deployments, and api-keys via the Twin Plane.
"""

import logging

from flask import Flask, g

from twins_local.logs import install_correlation_id

from .explainer import explainer_bp
from .routes.oauth_token import oauth_token_bp
from .routes.openai_data import data_bp
from .routes.well_known import well_known_bp
from .storage import TwinStorage
from .twin_plane.routes import twin_plane_bp

logger = logging.getLogger(__name__)


def create_app(
    storage: TwinStorage,
    tenants=None,
    config: dict | None = None,
) -> Flask:
    """Create and configure the AOAI twin Flask app.

    Args:
        storage: A :class:`TwinStorage` implementation provided by the host.
        tenants: A ``TenantStore`` implementation. Required for Twin Plane
            tenant auth.
        config: Configuration dict. Supported keys:
            - ``base_url`` (str): public-facing URL of the twin.
            - ``admin_token`` (str): operator-admin Bearer token.
            - ``is_cloud`` (bool): when True, the cloud guard rejects
              ``tenant_id="default"``.
    """
    config = config or {}
    base_url = config.get("base_url", "http://localhost:8080")
    admin_token = config.get("admin_token", "")
    is_cloud = bool(config.get("is_cloud", False))

    app = Flask(__name__)
    app.config["TWIN_STORAGE"] = storage
    app.config["TWIN_TENANTS"] = tenants
    app.config["TWIN_BASE_URL"] = base_url
    app.config["TWIN_ADMIN_TOKEN"] = admin_token
    app.config["TWIN_IS_CLOUD"] = is_cloud

    install_correlation_id(app)

    @app.before_request
    def inject_context():
        g.storage = app.config["TWIN_STORAGE"]
        g.tenants = app.config["TWIN_TENANTS"]
        g.base_url = app.config["TWIN_BASE_URL"]
        g.admin_token = app.config["TWIN_ADMIN_TOKEN"]
        g.is_cloud = app.config["TWIN_IS_CLOUD"]

    # Per-resource keypairs are created lazily on first JWKS / token /
    # AAD-validate request (see crypto.ensure_keypair).
    app.register_blueprint(well_known_bp)
    app.register_blueprint(oauth_token_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(twin_plane_bp)
    app.register_blueprint(explainer_bp)

    logger.info(
        "AOAI twin created — base_url=%s cloud=%s", base_url, is_cloud
    )
    return app
