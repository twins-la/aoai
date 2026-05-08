"""Twin Plane authentication — re-exports from ``twins_local.tenants.auth``.

The Twin Plane authenticates callers as tenants (HTTP Basic
``tenant_id:tenant_secret``) or operator admins (Bearer or
``X-Twin-Admin-Token``). Data-plane auth (``api-key`` or AAD bearer) is
separate — see ``../auth.py``.
"""

from twins_local.tenants.auth import (
    require_admin,
    require_tenant,
    require_tenant_or_admin,
)

__all__ = ["require_tenant", "require_tenant_or_admin", "require_admin"]
