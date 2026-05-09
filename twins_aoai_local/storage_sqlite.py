"""SQLite implementation of the AOAI twin's TwinStorage.

Persistent across restarts; configurable via ``TWIN_DB_PATH``.

Every resource-scoped table carries the owning ``resource_id`` (and, for
tables that need fast tenant scoping like ``api_keys``, a denormalised
``tenant_id``). Twin Plane operations scope by ``tenant_id``; data-plane
operations scope by ``resource_id`` after the auth decorator has matched
either an api-key row or a JWT to the URL-named resource.
"""

import json
import sqlite3
import threading
from typing import Optional

from twins_aoai.storage import TwinStorage

_VALID_FEEDBACK_COLUMNS = frozenset({"status", "date_updated"})


class SQLiteStorage(TwinStorage):
    """SQLite-backed storage for the AOAI twin."""

    def __init__(self, db_path: str = "data/aoai_twin.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS resources (
                        resource_id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        friendly_name TEXT NOT NULL DEFAULT '',
                        date_created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_resources_tenant ON resources(tenant_id);

                    CREATE TABLE IF NOT EXISTS api_keys (
                        key_id TEXT PRIMARY KEY,
                        resource_id TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        key_hash TEXT NOT NULL UNIQUE,
                        friendly_name TEXT NOT NULL DEFAULT '',
                        date_created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_api_keys_resource ON api_keys(resource_id);
                    CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);

                    CREATE TABLE IF NOT EXISTS deployments (
                        resource_id TEXT NOT NULL,
                        deployment_id TEXT NOT NULL,
                        model TEXT NOT NULL,
                        friendly_name TEXT NOT NULL DEFAULT '',
                        date_created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (resource_id, deployment_id)
                    );

                    CREATE TABLE IF NOT EXISTS signing_keys (
                        resource_id TEXT PRIMARY KEY,
                        kid TEXT NOT NULL,
                        private_pem TEXT NOT NULL,
                        public_pem TEXT NOT NULL,
                        date_created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS requests (
                        id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        resource_id TEXT NOT NULL,
                        deployment_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        request_json TEXT NOT NULL,
                        response_json TEXT NOT NULL,
                        date_created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_requests_tenant ON requests(tenant_id);
                    CREATE INDEX IF NOT EXISTS idx_requests_resource ON requests(resource_id);

                    CREATE TABLE IF NOT EXISTS feedback (
                        id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        body TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT '',
                        context_json TEXT NOT NULL DEFAULT '{}',
                        status TEXT NOT NULL DEFAULT 'pending',
                        date_created TEXT NOT NULL,
                        date_updated TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_feedback_tenant ON feedback(tenant_id);

                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tenant_id TEXT NOT NULL,
                        record_json TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_logs_tenant ON logs(tenant_id);
                    """
                )
                conn.commit()
            finally:
                conn.close()

    # -- resources --

    def create_resource(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        friendly_name: str,
    ) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO resources (resource_id, tenant_id, friendly_name) VALUES (?, ?, ?)",
                    (resource_id, tenant_id, friendly_name),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_resource(resource_id) or {
            "resource_id": resource_id,
            "tenant_id": tenant_id,
            "friendly_name": friendly_name,
        }

    def get_resource(self, resource_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM resources WHERE resource_id = ?", (resource_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_resources(self, *, tenant_id: Optional[str] = None) -> list[dict]:
        conn = self._get_conn()
        try:
            if tenant_id is None:
                rows = conn.execute(
                    "SELECT * FROM resources ORDER BY resource_id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM resources WHERE tenant_id = ? ORDER BY resource_id",
                    (tenant_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_resource(self, resource_id: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM api_keys WHERE resource_id = ?", (resource_id,)
                )
                conn.execute(
                    "DELETE FROM deployments WHERE resource_id = ?", (resource_id,)
                )
                conn.execute(
                    "DELETE FROM signing_keys WHERE resource_id = ?", (resource_id,)
                )
                conn.execute(
                    "DELETE FROM resources WHERE resource_id = ?", (resource_id,)
                )
                conn.commit()
            finally:
                conn.close()

    # -- api keys --

    def create_api_key(
        self,
        *,
        resource_id: str,
        key_id: str,
        key_hash: str,
        friendly_name: str,
    ) -> dict:
        # Look up the owning tenant so the api-key row carries it
        # denormalised for fast auth scoping.
        resource = self.get_resource(resource_id)
        tenant_id = resource["tenant_id"] if resource else ""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO api_keys (key_id, resource_id, tenant_id, key_hash, friendly_name) VALUES (?, ?, ?, ?, ?)",
                    (key_id, resource_id, tenant_id, key_hash, friendly_name),
                )
                conn.commit()
            finally:
                conn.close()
        return {
            "key_id": key_id,
            "resource_id": resource_id,
            "tenant_id": tenant_id,
            "key_hash": key_hash,
            "friendly_name": friendly_name,
        }

    def get_api_key_by_hash(self, key_hash: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_api_keys(self, *, resource_id: Optional[str] = None) -> list[dict]:
        conn = self._get_conn()
        try:
            if resource_id is None:
                rows = conn.execute(
                    "SELECT * FROM api_keys ORDER BY key_id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM api_keys WHERE resource_id = ? ORDER BY key_id",
                    (resource_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_api_key(self, key_id: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM api_keys WHERE key_id = ?", (key_id,))
                conn.commit()
            finally:
                conn.close()

    # -- deployments --

    def create_deployment(
        self,
        *,
        resource_id: str,
        deployment_id: str,
        model: str,
        friendly_name: str,
    ) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO deployments (resource_id, deployment_id, model, friendly_name) VALUES (?, ?, ?, ?)",
                    (resource_id, deployment_id, model, friendly_name),
                )
                conn.commit()
            finally:
                conn.close()
        return {
            "resource_id": resource_id,
            "deployment_id": deployment_id,
            "model": model,
            "friendly_name": friendly_name,
        }

    def get_deployment(
        self, *, resource_id: str, deployment_id: str
    ) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM deployments WHERE resource_id = ? AND deployment_id = ?",
                (resource_id, deployment_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_deployments(self, *, resource_id: str) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM deployments WHERE resource_id = ? ORDER BY deployment_id",
                (resource_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_deployment(
        self, *, resource_id: str, deployment_id: str
    ) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM deployments WHERE resource_id = ? AND deployment_id = ?",
                    (resource_id, deployment_id),
                )
                conn.commit()
            finally:
                conn.close()

    # -- signing keys --

    def get_signing_key(self, resource_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT resource_id, kid, private_pem, public_pem FROM signing_keys WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def put_signing_key(
        self,
        *,
        resource_id: str,
        kid: str,
        private_pem: str,
        public_pem: str,
    ) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO signing_keys (resource_id, kid, private_pem, public_pem) VALUES (?, ?, ?, ?)",
                    (resource_id, kid, private_pem, public_pem),
                )
                conn.commit()
            finally:
                conn.close()
        return {
            "resource_id": resource_id,
            "kid": kid,
            "private_pem": private_pem,
            "public_pem": public_pem,
        }

    def get_or_create_signing_key(self, resource_id: str, generator) -> dict:
        # `self._lock` is held across the entire SELECT-then-INSERT, so two
        # concurrent threads cannot both observe "no key" and both generate.
        # See twins-la/aoai#2 for the race that motivated this primitive.
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT resource_id, kid, private_pem, public_pem "
                    "FROM signing_keys WHERE resource_id = ?",
                    (resource_id,),
                ).fetchone()
                if row:
                    return dict(row)
                kid, private_pem, public_pem = generator()
                conn.execute(
                    "INSERT INTO signing_keys (resource_id, kid, private_pem, public_pem) VALUES (?, ?, ?, ?)",
                    (resource_id, kid, private_pem, public_pem),
                )
                conn.commit()
            finally:
                conn.close()
        return {
            "resource_id": resource_id,
            "kid": kid,
            "private_pem": private_pem,
            "public_pem": public_pem,
        }

    # -- requests --

    def create_request(self, data: dict) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO requests
                        (id, tenant_id, resource_id, deployment_id, kind, request_json, response_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["id"],
                        data["tenant_id"],
                        data["resource_id"],
                        data["deployment_id"],
                        data["kind"],
                        data.get("request_json", "{}"),
                        data.get("response_json", "{}"),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return data

    def list_requests(
        self,
        *,
        tenant_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        conn = self._get_conn()
        try:
            sql = "SELECT * FROM requests WHERE 1=1"
            params: list = []
            if tenant_id is not None:
                sql += " AND tenant_id = ?"
                params.append(tenant_id)
            if resource_id is not None:
                sql += " AND resource_id = ?"
                params.append(resource_id)
            sql += " ORDER BY date_created DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["request"] = json.loads(d.pop("request_json") or "{}")
                d["response"] = json.loads(d.pop("response_json") or "{}")
                out.append(d)
            return out
        finally:
            conn.close()

    # -- feedback --

    def create_feedback(self, data: dict) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO feedback
                        (id, tenant_id, body, category, context_json, status, date_created, date_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["id"],
                        data["tenant_id"],
                        data["body"],
                        data.get("category", ""),
                        json.dumps(data.get("context", {}) or {}),
                        data.get("status", "pending"),
                        data["date_created"],
                        data["date_updated"],
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_feedback(data["id"])

    def get_feedback(self, feedback_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM feedback WHERE id = ?", (feedback_id,)
            ).fetchone()
            return self._row_to_feedback(row) if row else None
        finally:
            conn.close()

    def list_feedback(
        self,
        *,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dict]:
        conn = self._get_conn()
        try:
            sql = "SELECT * FROM feedback WHERE 1=1"
            params: list = []
            if status:
                sql += " AND status = ?"
                params.append(status)
            if tenant_id is not None:
                sql += " AND tenant_id = ?"
                params.append(tenant_id)
            sql += " ORDER BY date_created DESC"
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_feedback(r) for r in rows]
        finally:
            conn.close()

    def update_feedback(self, feedback_id: str, updates: dict) -> Optional[dict]:
        cols = [k for k in updates.keys() if k in _VALID_FEEDBACK_COLUMNS]
        if not cols:
            return self.get_feedback(feedback_id)
        sql = f"UPDATE feedback SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?"
        params = [updates[c] for c in cols] + [feedback_id]
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
        return self.get_feedback(feedback_id)

    @staticmethod
    def _row_to_feedback(row) -> dict:
        return {
            "id": row["id"],
            "tenant_id": row["tenant_id"],
            "body": row["body"],
            "category": row["category"],
            "context": json.loads(row["context_json"] or "{}"),
            "status": row["status"],
            "date_created": row["date_created"],
            "date_updated": row["date_updated"],
        }

    # -- logs --

    def append_log(self, entry: dict) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO logs (tenant_id, record_json, timestamp) VALUES (?, ?, ?)",
                    (
                        entry.get("tenant_id", ""),
                        json.dumps(entry),
                        entry.get("timestamp", ""),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def list_logs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        tenant_id: Optional[str] = None,
    ) -> list[dict]:
        conn = self._get_conn()
        try:
            sql = "SELECT id, record_json FROM logs"
            params: list = []
            if tenant_id is not None:
                sql += " WHERE tenant_id = ?"
                params.append(tenant_id)
            sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(sql, params).fetchall()
            out = []
            for r in rows:
                rec = json.loads(r["record_json"])
                rec["id"] = r["id"]
                out.append(rec)
            return out
        finally:
            conn.close()
