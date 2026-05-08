"""Explainer landing page + agent instructions for the AOAI twin.

Serves:
  GET /                          — HTML explainer page for humans and agents
  GET /_twin/agent-instructions  — Plain-text agent instructions
"""

from flask import Blueprint

explainer_bp = Blueprint("explainer", __name__)

AGENT_INSTRUCTIONS = """\
# Azure OpenAI Twin — aoai.twins.la

A high-fidelity digital twin of the Azure OpenAI Service data plane. The
twin emulates chat completions, legacy completions, and embeddings, all
backed by deterministic synthetic responses (no real model is ever
called).

## URL shape

Path-prefixed, single host:

    https://aoai.twins.la/<resource>/openai/deployments/<deployment>/chat/completions
    https://aoai.twins.la/<resource>/openai/deployments/<deployment>/embeddings
    https://aoai.twins.la/<resource>/openai/deployments/<deployment>/completions

There is no subdomain-per-resource. The Azure ARM control plane is NOT
emulated — operators provision resources, deployments, and api-keys
through the Twin Plane (`/_twin/`).

## Authentication (data plane)

Both auth paths are accepted on every data-plane endpoint and either is
sufficient:

  * `api-key: <key>` — primary AOAI auth header.
  * `Authorization: Bearer <jwt>` — AAD-shaped JWT, RS256-signed by the
    twin's per-resource keypair, obtained from
    `POST /<resource>/oauth2/v2.0/token` with grant_type=client_credentials.

Tenant isolation is enforced on both paths.

## Twin Plane authentication

Twin Plane (`/_twin/`) uses the standard tenant Basic + admin Bearer scheme:

  * Bootstrap a tenant: `POST /_twin/tenants` -> {tenant_id, tenant_secret}
  * Tenant calls: HTTP Basic `tenant_id:tenant_secret`
  * Admin calls: `Authorization: Bearer <admin_token>` (or `X-Twin-Admin-Token`)

## Key endpoints

Twin Plane (no auth):
  GET  /_twin/health
  GET  /_twin/scenarios
  GET  /_twin/settings
  GET  /_twin/references
  POST /_twin/tenants

Twin Plane (Basic tenant_id:tenant_secret):
  POST /_twin/resources                              -> {resource_id, base_url}
  GET  /_twin/resources
  DELETE /_twin/resources/<resource>
  POST /_twin/resources/<resource>/api_keys           -> {key_id, api_key (shown ONCE)}
  GET  /_twin/resources/<resource>/api_keys
  POST /_twin/resources/<resource>/deployments        body: {model, deployment_id?}
  GET  /_twin/resources/<resource>/deployments
  DELETE /_twin/resources/<resource>/deployments/<d>
  GET  /_twin/logs                  (or admin Bearer for cross-tenant)
  POST /_twin/feedback

Per-resource AAD endpoints (no auth):
  GET  /<resource>/.well-known/openid-configuration
  GET  /<resource>/.well-known/jwks.json
  POST /<resource>/oauth2/v2.0/token   form: grant_type=client_credentials,
                                              client_id=<key_id>,
                                              client_secret=<api_key>

Data plane (api-key OR AAD bearer):
  POST /<resource>/openai/deployments/<deployment>/chat/completions
  POST /<resource>/openai/deployments/<deployment>/completions
  POST /<resource>/openai/deployments/<deployment>/embeddings

## Quick start (cloud)

  curl -X POST https://aoai.twins.la/_twin/tenants \\
    -H "Content-Type: application/json" \\
    -d '{"friendly_name":"Dev"}'
  # -> { tenant_id, tenant_secret }

  curl -X POST https://aoai.twins.la/_twin/resources \\
    -u "TENANT_ID:TENANT_SECRET" \\
    -H "Content-Type: application/json" \\
    -d '{"friendly_name":"my-aoai"}'
  # -> { resource_id, base_url }

  curl -X POST https://aoai.twins.la/_twin/resources/RID/api_keys \\
    -u "TENANT_ID:TENANT_SECRET" -d '{}'
  # -> { key_id, api_key }

  curl -X POST https://aoai.twins.la/_twin/resources/RID/deployments \\
    -u "TENANT_ID:TENANT_SECRET" \\
    -H "Content-Type: application/json" \\
    -d '{"model":"gpt-4o-mini","deployment_id":"chat"}'

  curl -X POST 'https://aoai.twins.la/RID/openai/deployments/chat/chat/completions?api-version=2024-10-21' \\
    -H 'api-key: RAW_API_KEY' \\
    -H 'Content-Type: application/json' \\
    -d '{"messages":[{"role":"user","content":"hello"}]}'

## SDK example

    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_key="RAW_API_KEY",
        api_version="2024-10-21",
        azure_endpoint="https://aoai.twins.la/RID",
    )
    resp = client.chat.completions.create(
        model="chat",  # the deployment name
        messages=[{"role": "user", "content": "hello"}],
    )

## Local

  pip install twins-aoai twins-aoai-local
  python -m twins_aoai_local

## Reference

GitHub:           https://github.com/twins-la/aoai
Project overview: https://twins.la
All twins:        https://github.com/twins-la/twins-la
"""


EXPLAINER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>aoai.twins.la &mdash; Azure OpenAI Twin</title>
    <link rel="icon" type="image/png" href="https://twins.la/twins.png">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            min-height: 100vh;
            background: #f8f8f8;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: #374151;
            padding: 4rem 2rem;
            line-height: 1.7;
        }
        main { max-width: 700px; margin: 0 auto; }
        h1 {
            font-size: clamp(2rem, 5vw, 3rem);
            font-weight: 600;
            letter-spacing: -0.03em;
            color: #1a2e4a;
            margin-bottom: 0.5rem;
        }
        h1 .aoai { color: #0078d4; }
        .tagline { font-size: 1.1rem; color: #6b7280; margin-bottom: 2.5rem; font-weight: 300; }
        h2 {
            font-size: 1.25rem;
            font-weight: 600;
            color: #1a2e4a;
            margin: 2rem 0 0.75rem;
            letter-spacing: -0.01em;
        }
        p { margin-bottom: 1rem; color: #6b7280; }
        p strong { color: #1a2e4a; }
        a { color: #0078d4; text-decoration: none; }
        a:hover { color: #005a9e; text-decoration: underline; }
        ul { list-style: none; padding: 0; margin-bottom: 1rem; }
        ul li { padding: 0.3rem 0; color: #6b7280; }
        ul li::before { content: "\\2192  "; color: #0078d4; }
        code {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85em;
            background: #f3f4f6;
            padding: 0.15em 0.4em;
            border-radius: 4px;
            color: #1a2e4a;
            border: 1px solid #e5e7eb;
        }
        .snippet-box {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 1.5rem;
            margin: 1rem 0;
            position: relative;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .snippet-box pre {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: #6b7280;
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.5;
            max-height: 400px;
            overflow-y: auto;
        }
        .copy-btn {
            position: absolute;
            top: 0.75rem;
            right: 0.75rem;
            background: #f3f4f6;
            color: #6b7280;
            border: 1px solid #e5e7eb;
            padding: 0.3rem 0.7rem;
            border-radius: 6px;
            font-size: 0.75rem;
            cursor: pointer;
            font-family: 'Inter', sans-serif;
            transition: background 0.15s, color 0.15s;
        }
        .copy-btn:hover { background: #1a2e4a; color: #ffffff; }
        .links { margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px solid #e5e7eb; }
        .links a { margin-right: 1.5rem; font-size: 0.9rem; }
        footer { margin-top: 3rem; color: #6b7280; font-size: 0.8rem; }
        footer .dot { color: #0078d4; }
        .breadcrumb { margin-bottom: 0.5rem; font-size: 0.85rem; }
        .breadcrumb a { color: #0e7490; }
        .breadcrumb a:hover { color: #1a2e4a; }
        .callout {
            background: #eef6fc;
            border: 1px solid #b7dbf2;
            border-radius: 10px;
            padding: 1rem 1.25rem;
            margin: 1.25rem 0;
            color: #0c3a59;
        }
    </style>
</head>
<body>
    <main>
        <p class="breadcrumb"><a href="https://twins.la">twins.la</a></p>
        <h1><span class="aoai">aoai</span>.twins.la</h1>
        <p class="tagline">A digital twin of the Azure OpenAI Service.</p>

        <h2>What is this?</h2>
        <p>
            A high-fidelity digital twin of the Azure OpenAI Service
            <strong>data plane</strong>: chat completions, legacy completions,
            and embeddings. Responses are deterministic synthetic stand-ins,
            so identical inputs always produce identical outputs and no real
            model is ever called.
        </p>
        <ul>
            <li><strong>Resources</strong> &mdash; tenant-scoped namespaces, the <code>&lt;resource&gt;</code> URL segment.</li>
            <li><strong>Deployments</strong> &mdash; per-resource <code>&lt;deployment&gt;</code> mapping to a model name.</li>
            <li><strong>Dual auth</strong> &mdash; <code>api-key</code> header OR AAD <code>Authorization: Bearer</code>; either is sufficient.</li>
        </ul>

        <div class="callout">
            <strong>No control plane.</strong> Azure's ARM management API is
            intentionally not emulated. Provision resources, deployments, and
            api-keys through the Twin Plane at <code>/_twin/</code>.
        </div>

        <h2>Supported scenarios</h2>
        <ul>
            <li><code>chat-completions</code> &mdash; non-streaming and streaming SSE</li>
            <li><code>embeddings</code> &mdash; deterministic synthetic vectors</li>
            <li><code>dual-auth</code> &mdash; api-key + AAD-bearer with per-resource JWKS and OAuth token endpoint</li>
        </ul>

        <h2>How to use it</h2>
        <p>
            <strong>Cloud:</strong> bootstrap a tenant, create a resource and
            deployment via <code>/_twin/</code>, then point your Azure OpenAI
            SDK at <code>https://aoai.twins.la/&lt;resource&gt;</code> with
            either an api-key or a token from the per-resource AAD endpoint.
        </p>
        <p>
            <strong>Local:</strong> install with
            <code>pip install twins-aoai-local</code> and run a local instance
            on any port. Same API, same behavior, your machine.
        </p>

        <h2>For agents</h2>
        <p>
            Copy this into your agent's system prompt, tool configuration, or
            CLAUDE.md. Also available as plain text at
            <a href="/_twin/agent-instructions"><code>/_twin/agent-instructions</code></a>.
        </p>
        <div class="snippet-box">
            <button class="copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('agent-snippet').textContent).then(()=>{this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)})">Copy</button>
            <pre id="agent-snippet">""" + AGENT_INSTRUCTIONS.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + """</pre>
        </div>

        <div class="links">
            <a href="https://github.com/twins-la/aoai">GitHub</a>
            <a href="https://twins.la">twins.la</a>
            <a href="/_twin/health">Health</a>
            <a href="/_twin/scenarios">Scenarios</a>
        </div>

        <footer>twins.la <span class="dot">&middot;</span> Where agents meet their environment.</footer>
    </main>
</body>
</html>
"""


@explainer_bp.route("/", methods=["GET"])
def explainer_page():
    return EXPLAINER_HTML
