# Scenarios — twins-aoai

Per the twins.la HOSTING_CONTRACT, every twin enumerates the scenarios it
supports and the surfaces those scenarios cover. Status values are
`Supported`, `Partial`, or `Out-of-scope`.

## Version 0.1.0

### `chat-completions` — Supported

Azure OpenAI chat-completions data plane.

In-scope:

* `POST /<resource>/openai/deployments/<deployment>/chat/completions`
  (non-streaming)
* `POST /<resource>/openai/deployments/<deployment>/chat/completions` with
  `stream: true` — text/event-stream response with role + content delta
  chunks and a terminal `data: [DONE]` line.
* `?api-version=...` query parameter accepted (recorded, not validated
  against an allowlist).
* OpenAI-compatible response envelope:
  `{id, object: "chat.completion", created, model, choices, usage}`.

Out-of-scope: function/tool calling beyond the static request envelope,
JSON-mode strict output, log-probs, real model inference.

### `embeddings` — Supported

Azure OpenAI embeddings data plane.

In-scope:

* `POST /<resource>/openai/deployments/<deployment>/embeddings`
* `input` accepted as a string or list of strings.
* Deterministic 1536-dim synthetic vectors (SHA-256-seeded, L2-normalised);
  identical inputs produce identical vectors across runs.
* OpenAI-compatible envelope: `{object:"list", data:[{embedding,...}],
  model, usage}`.

Out-of-scope: dimensions parameter, base64 encoding, real embedding
inference.

### `dual-auth` — Supported

Both authentication paths accepted on every data-plane endpoint; either
is sufficient.

In-scope:

* `api-key: <key>` header path. Hashes are looked up; the key must belong
  to the URL-named resource (cross-resource keys are rejected).
* `Authorization: Bearer <jwt>` path. JWTs are RS256-signed by the twin's
  per-resource keypair and obtained from
  `POST /<resource>/oauth2/v2.0/token` with grant_type=client_credentials.
  Validation rejects: `alg=none`, `alg=HS*`, expired, bad-aud, bad-iss,
  unknown-kid, missing-claim, sig-invalid, tid-mismatch.
* Per-resource AAD discovery at
  `GET /<resource>/.well-known/openid-configuration` and JWKS at
  `GET /<resource>/.well-known/jwks.json`.

Out-of-scope:

* Real Azure ARM control plane (resource creation via management API).
* Managed-identity / federated-credentials AAD flows (only
  client_credentials is honoured).

### Out-of-scope (entire twin)

* ARM control plane.
* Real model inference.
* Fine-tuning, assistants, threads, vector stores, file uploads.
* Image generation (DALL-E) and audio (Whisper, TTS).
* Content-filter / safety annotations.

## References (retrieved 2026-05-08)

* Azure OpenAI Service REST API:
  <https://learn.microsoft.com/en-us/azure/ai-services/openai/reference>
* Azure OpenAI: Migration guide for OpenAI Python v1.x:
  <https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/migration>
* Microsoft identity platform — v2.0 protocols:
  <https://learn.microsoft.com/en-us/azure/active-directory/develop/active-directory-v2-protocols>
* RFC 7517 — JSON Web Key (JWK):
  <https://datatracker.ietf.org/doc/html/rfc7517>
* RFC 7519 — JSON Web Token (JWT):
  <https://datatracker.ietf.org/doc/html/rfc7519>
* RFC 7638 — JWK Thumbprint:
  <https://datatracker.ietf.org/doc/html/rfc7638>
