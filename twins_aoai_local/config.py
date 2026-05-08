"""Local-host configuration. Values come from the environment so the
container deployment can override them without code changes."""

import os

HOST = os.environ.get("TWIN_HOST", "0.0.0.0")
PORT = int(os.environ.get("TWIN_PORT", "8080"))
BASE_URL = os.environ.get("TWIN_BASE_URL", f"http://localhost:{PORT}")
ADMIN_TOKEN = os.environ.get("TWIN_ADMIN_TOKEN", "")
DB_PATH = os.environ.get(
    "TWIN_DB_PATH", os.path.expanduser("~/.twins/aoai.sqlite3")
)
