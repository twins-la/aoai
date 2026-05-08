# twins-aoai

A digital twin of the **Azure OpenAI Service** for [twins.la](https://twins.la).

## What this is

A high-fidelity emulation of the Azure OpenAI **data plane** with
path-prefixed resource routing:

```
https://aoai.twins.la/<resource>/openai/deployments/<deployment>/chat/completions
https://aoai.twins.la/<resource>/openai/deployments/<deployment>/embeddings
https://aoai.twins.la/<resource>/openai/deployments/<deployment>/completions
```

* **Channel:** Azure OpenAI Service data plane.
* **Synthetic responses:** the twin never calls a real model. Chat replies
  are deterministic echoes; embeddings are deterministic vectors so identical
  inputs produce identical outputs across runs.
* **Control plane skipped:** Azure ARM is not emulated — operators provision
  resources, deployments, and api-keys through the Twin Plane at `/_twin/`.
* **Dual auth:** every data-plane endpoint accepts EITHER an `api-key`
  header OR an `Authorization: Bearer <jwt>`. Either is sufficient. AAD
  tokens are issued and signed by a per-resource RSA keypair.

## Supported scenarios

* `chat-completions` — non-streaming and streaming SSE.
* `embeddings` — single and batch input, deterministic synthetic vectors.
* `dual-auth` — api-key + AAD-bearer with per-resource JWKS and OAuth
  client-credentials token endpoint.

See [SCENARIOS.md](./SCENARIOS.md) for full details.

## Cloud usage

```bash
# 1) Bootstrap a tenant (returned secret is shown ONCE).
curl -X POST https://aoai.twins.la/_twin/tenants \
  -H "Content-Type: application/json" \
  -d '{"friendly_name": "Dev"}'
# -> { tenant_id, tenant_secret }

# 2) Create a resource (the <resource> URL segment).
curl -X POST https://aoai.twins.la/_twin/resources \
  -u "TENANT_ID:TENANT_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"friendly_name": "my-aoai"}'
# -> { resource_id, base_url: "https://aoai.twins.la/<resource_id>" }

# 3) Mint an api-key for the resource.
curl -X POST https://aoai.twins.la/_twin/resources/<resource_id>/api_keys \
  -u "TENANT_ID:TENANT_SECRET" -d '{}'
# -> { key_id, api_key }   (api_key shown ONCE)

# 4) Create a deployment that maps a deployment-name to a model.
curl -X POST https://aoai.twins.la/_twin/resources/<resource_id>/deployments \
  -u "TENANT_ID:TENANT_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"deployment_id": "chat", "model": "gpt-4o-mini"}'
```

Then call the data plane with the Azure OpenAI SDK:

```python
from openai import AzureOpenAI

client = AzureOpenAI(
    api_key="RAW_API_KEY",
    api_version="2024-10-21",
    azure_endpoint="https://aoai.twins.la/<resource_id>",
)
resp = client.chat.completions.create(
    model="chat",  # the deployment name
    messages=[{"role": "user", "content": "hello"}],
)
```

## Local usage

```bash
pip install twins-aoai twins-aoai-local
python -m twins_aoai_local
# -> http://localhost:8080
```

The local host uses SQLite at `~/.twins/aoai.sqlite3`. Override with
`TWIN_DB_PATH`, `TWIN_HOST`, `TWIN_PORT`, `TWIN_BASE_URL`, or
`TWIN_ADMIN_TOKEN`.

## Project structure

* `twins_aoai/` — the twin (Flask app, blueprints, storage ABC).
* `twins_aoai_local/` — local SQLite host.
* `tests/smoke/` — in-process Flask test-client suite.
