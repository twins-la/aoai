"""Azure OpenAI digital twin for twins.la.

The twin emulates the Azure OpenAI Service **data plane** with
path-prefixed resource routing:

    https://aoai.twins.la/<resource>/openai/deployments/<deployment>/...

Each tenant owns one or more *resources* (a tenant-scoped namespace that
mirrors Azure's account/resource concept). Each resource owns one or more
*deployments* (the Azure deployment-name layer that maps to a model). API
keys, signing keys, and request history are scoped to the resource.

The control plane (ARM) is intentionally skipped: operators create
resources, deployments, and api-keys via the Twin Plane at ``/_twin/``
rather than through ARM emulation.

Two authentication paths are accepted on every data-plane endpoint and
either is sufficient:

* ``api-key: <key>`` — primary AOAI auth header.
* ``Authorization: Bearer <jwt>`` — AAD-shaped JWT, RS256-signed by the
  twin's per-resource keypair and obtained from the per-resource OAuth
  token endpoint at ``/<resource>/oauth2/v2.0/token``.
"""

__version__ = "0.1.0"
