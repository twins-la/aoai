"""Local host entry point for the AOAI twin.

Wires up SQLite storage + the shared tenants store and serves the app.
"""

import logging
import os

from twins_aoai.app import create_app
from twins_local.tenants import SQLiteTenantStore, ensure_default_tenant

from .config import ADMIN_TOKEN, BASE_URL, DB_PATH
from .storage_sqlite import SQLiteStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def create_local_app():
    """Create the locally-hosted twin application.

    WSGI entry point::

        gunicorn 'twins_aoai_local.host:create_local_app()'
    """
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    storage = SQLiteStorage(db_path=DB_PATH)
    tenants = SQLiteTenantStore()
    ensure_default_tenant(tenants)

    app = create_app(
        storage=storage,
        tenants=tenants,
        config={
            "base_url": BASE_URL,
            "admin_token": ADMIN_TOKEN,
            "is_cloud": False,
        },
    )
    logger.info(
        "Local AOAI twin ready — db=%s base_url=%s", DB_PATH, BASE_URL
    )
    return app


def main():
    from .config import HOST, PORT

    app = create_local_app()
    logger.info("Starting local AOAI twin on %s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
