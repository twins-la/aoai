"""Streaming SSE chat completions."""

import json


def test_streaming_chat_completion(client, resource, api_key, deployment):
    resp = client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={
            "messages": [{"role": "user", "content": "stream please"}],
            "stream": True,
        },
        headers=api_key["headers"],
    )
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"

    raw = resp.get_data(as_text=True)
    lines = [ln for ln in raw.split("\n") if ln.startswith("data: ")]
    assert lines, raw
    assert lines[-1].strip() == "data: [DONE]"

    # Parse each non-DONE line as JSON, sanity-check the chunk shape.
    chunks = []
    for ln in lines[:-1]:
        body = ln[len("data: "):]
        chunks.append(json.loads(body))
    assert chunks
    assert all(c["object"] == "chat.completion.chunk" for c in chunks)
    # First chunk carries the role; some intermediate carry content; final
    # carries finish_reason="stop".
    assert chunks[0]["choices"][0]["delta"].get("role") == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    contents = "".join(
        c["choices"][0]["delta"].get("content", "") for c in chunks
    )
    assert "echoing" in contents
