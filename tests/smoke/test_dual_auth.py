"""Dual auth: api-key path AND AAD-bearer path on the same endpoint."""

import time

import jwt

from twins_aoai.crypto import ensure_keypair


def test_chat_completion_via_api_key(client, resource, api_key, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "via api-key"}]},
        headers=api_key["headers"],
    )
    assert resp.status_code == 200


def test_chat_completion_via_aad_bearer(
    client, resource, deployment, aad_token
):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "via aad"}]},
        headers=aad_token["headers"],
    )
    assert resp.status_code == 200


def test_aad_token_with_bad_audience_rejected(
    client, twin_app, resource, deployment
):
    """Forge a token with the right kid but wrong aud — must be rejected."""
    storage = twin_app.config["TWIN_STORAGE"]
    keypair = ensure_keypair(storage, resource["resource_id"])
    now = int(time.time())
    payload = {
        "iss": f"http://localhost:8080/{resource['resource_id']}/v2.0",
        "aud": "https://wrong.example.com",
        "tid": resource["tenant_id"],
        "appid": "spoof",
        "sub": "spoof",
        "iat": now,
        "nbf": now - 5,
        "exp": now + 600,
        "ver": "1.0",
    }
    from twins_aoai.crypto import load_private_key

    bad = jwt.encode(
        payload,
        load_private_key(keypair["private_pem"]),
        algorithm="RS256",
        headers={"kid": keypair["kid"], "typ": "JWT"},
    )
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "bad-aud"}]},
        headers={"Authorization": f"Bearer {bad}"},
    )
    assert resp.status_code == 401


def test_aad_token_expired_rejected(
    client, twin_app, resource, deployment
):
    storage = twin_app.config["TWIN_STORAGE"]
    keypair = ensure_keypair(storage, resource["resource_id"])
    # Fully expired beyond the 5-minute leeway.
    now = int(time.time())
    payload = {
        "iss": f"http://localhost:8080/{resource['resource_id']}/v2.0",
        "aud": "https://cognitiveservices.azure.com",
        "tid": resource["tenant_id"],
        "appid": "spoof",
        "sub": "spoof",
        "iat": now - 7200,
        "nbf": now - 7200,
        "exp": now - 3600,
        "ver": "1.0",
    }
    from twins_aoai.crypto import load_private_key

    expired = jwt.encode(
        payload,
        load_private_key(keypair["private_pem"]),
        algorithm="RS256",
        headers={"kid": keypair["kid"], "typ": "JWT"},
    )
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "expired"}]},
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401


def test_aad_token_unknown_kid_rejected(
    client, resource, deployment
):
    """Build a token with a bogus kid — twin's validator must reject."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rogue_pem = rogue.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    now = int(time.time())
    payload = {
        "iss": f"http://localhost:8080/{resource['resource_id']}/v2.0",
        "aud": "https://cognitiveservices.azure.com",
        "tid": resource["tenant_id"],
        "appid": "spoof",
        "sub": "spoof",
        "iat": now,
        "nbf": now - 5,
        "exp": now + 600,
        "ver": "1.0",
    }
    from twins_aoai.crypto import load_private_key

    bad = jwt.encode(
        payload,
        load_private_key(rogue_pem),
        algorithm="RS256",
        headers={"kid": "totally-bogus", "typ": "JWT"},
    )
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "rogue-kid"}]},
        headers={"Authorization": f"Bearer {bad}"},
    )
    assert resp.status_code == 401
