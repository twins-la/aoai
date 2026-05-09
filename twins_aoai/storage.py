"""Abstract storage interface for the AOAI twin.

Hosts (local SQLite, cloud Postgres) implement this contract. The twin
package never imports a specific database driver.

Resource hierarchy:
  * ``resources``   — tenant-owned namespace (``<resource>`` URL segment).
  * ``api_keys``    — per-resource keys for the ``api-key`` header. Multiple
                      keys per resource so they can be rotated without an
                      outage window.
  * ``deployments`` — per-resource deployment name → model mapping.
  * ``signing_keys`` — per-resource RSA keypair (PEM) used to sign and
                       verify the AAD-shaped JWTs the twin issues at
                       ``/<resource>/oauth2/v2.0/token``. Persistent so
                       the JWKS is stable across restarts.
  * ``requests``    — request/response history for inspection.
"""

from abc import ABC, abstractmethod
from typing import Optional


class TwinStorage(ABC):
    """Storage backend contract that hosts must implement."""

    # -- Resources --

    @abstractmethod
    def create_resource(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        friendly_name: str,
    ) -> dict:
        """Persist a resource row. Returns the stored row."""

    @abstractmethod
    def get_resource(self, resource_id: str) -> Optional[dict]:
        """Fetch a resource by id; returns the row including ``tenant_id``."""

    @abstractmethod
    def list_resources(self, *, tenant_id: Optional[str] = None) -> list[dict]:
        """List resources; ``tenant_id=None`` returns all (admin only)."""

    @abstractmethod
    def delete_resource(self, resource_id: str) -> None:
        """Delete a resource and any of its child rows that belong with it."""

    # -- API keys (per resource) --

    @abstractmethod
    def create_api_key(
        self,
        *,
        resource_id: str,
        key_id: str,
        key_hash: str,
        friendly_name: str,
    ) -> dict:
        """Persist an api-key row. Returns the stored row (no raw secret)."""

    @abstractmethod
    def get_api_key_by_hash(self, key_hash: str) -> Optional[dict]:
        """Lookup an api-key by its hash; row carries ``resource_id`` and
        (denormalised) ``tenant_id`` for fast auth scoping."""

    @abstractmethod
    def list_api_keys(self, *, resource_id: Optional[str] = None) -> list[dict]:
        """List api-keys (no raw secrets); admin-only when ``resource_id`` is None."""

    @abstractmethod
    def delete_api_key(self, key_id: str) -> None:
        """Delete an api-key row by id."""

    # -- Deployments (per resource) --

    @abstractmethod
    def create_deployment(
        self,
        *,
        resource_id: str,
        deployment_id: str,
        model: str,
        friendly_name: str,
    ) -> dict:
        """Persist a deployment row. Returns the stored row."""

    @abstractmethod
    def get_deployment(
        self, *, resource_id: str, deployment_id: str
    ) -> Optional[dict]:
        """Fetch a deployment scoped to a resource."""

    @abstractmethod
    def list_deployments(self, *, resource_id: str) -> list[dict]:
        """List deployments for a resource."""

    @abstractmethod
    def delete_deployment(self, *, resource_id: str, deployment_id: str) -> None:
        """Delete a deployment by ``(resource_id, deployment_id)``."""

    # -- Per-resource signing keys --

    @abstractmethod
    def get_signing_key(self, resource_id: str) -> Optional[dict]:
        """Fetch the resource's signing keypair. Returns dict with
        ``kid``, ``private_pem``, ``public_pem`` or ``None``."""

    @abstractmethod
    def put_signing_key(
        self,
        *,
        resource_id: str,
        kid: str,
        private_pem: str,
        public_pem: str,
    ) -> dict:
        """Persist the resource's signing keypair."""

    @abstractmethod
    def get_or_create_signing_key(self, resource_id: str, generator) -> dict:
        """Atomically load the resource's signing keypair, generating one if none
        exists. The check-and-create MUST be serialized so concurrent first-time
        callers against the same ``resource_id`` produce exactly one keypair.

        ``generator`` is called only when no key is present and must return a
        ``(kid, private_pem, public_pem)`` tuple. Returns the dict shape of
        ``get_signing_key``.

        Closes twins-la/aoai#2 (cold-start race on per-resource keypair)."""

    # -- Requests history --

    @abstractmethod
    def create_request(self, data: dict) -> dict:
        """Persist a request/response history row.

        ``data`` carries ``id, tenant_id, resource_id, deployment_id, kind,
        request_json, response_json, date_created``.
        """

    @abstractmethod
    def list_requests(
        self,
        *,
        tenant_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """List request rows, optionally filtered by tenant and/or resource."""

    # -- Feedback --

    @abstractmethod
    def create_feedback(self, data: dict) -> dict:
        """Persist a feedback record."""

    @abstractmethod
    def get_feedback(self, feedback_id: str) -> Optional[dict]:
        """Fetch a feedback record by id."""

    @abstractmethod
    def list_feedback(
        self,
        *,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dict]:
        """List feedback, optionally filtered."""

    @abstractmethod
    def update_feedback(self, feedback_id: str, updates: dict) -> Optional[dict]:
        """Mutate a feedback record. Returns the updated dict or None."""

    # -- Logs --

    @abstractmethod
    def append_log(self, entry: dict) -> None:
        """Append an operation log entry. ``entry`` carries ``tenant_id``."""

    @abstractmethod
    def list_logs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        tenant_id: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve operation logs, optionally scoped to a tenant."""
