"""Streaming for ``POST /<resource>/openai/responses`` (`stream=true`).

Closes twins-la/aoai#3. Documented event sequence per Microsoft AOAI
reference (https://learn.microsoft.com/en-us/azure/ai-services/openai/
reference#responses, retrieved 2026-05-09):

    response.created
    response.output_item.added
    response.output_text.delta  (1+)
    response.output_item.done
    response.completed
"""

import json


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    """Parse an SSE response body into a list of (event, data) tuples.

    Each SSE block is separated by a blank line; each block carries
    ``event: <name>`` and ``data: <json>`` lines. Real-Azure streams
    can also include ``: ping`` keep-alive comments — strip those.
    """
    out: list[tuple[str, dict]] = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith(": "):
                continue
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if not event_name or not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            payload = {"_raw": "\n".join(data_lines)}
        out.append((event_name, payload))
    return out


def test_responses_stream_emits_documented_event_sequence(
    client, resource, api_key, deployment
):
    """The stream MUST emit, in order: response.created →
    response.output_item.added → 1+ response.output_text.delta →
    response.output_item.done → response.completed.
    """
    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={
            "model": deployment["deployment_id"],
            "input": "Streaming sweep test",
            "stream": True,
        },
        headers=api_key["headers"],
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.headers["Content-Type"].startswith("text/event-stream"), (
        f"Content-Type was {resp.headers.get('Content-Type')!r}"
    )

    events = _parse_sse(resp.get_data(as_text=True))
    names = [name for name, _ in events]

    assert names[0] == "response.created", names
    assert names[1] == "response.output_item.added", names
    delta_indices = [i for i, n in enumerate(names) if n == "response.output_text.delta"]
    assert len(delta_indices) >= 1, names
    last_delta = delta_indices[-1]
    assert names[last_delta + 1] == "response.output_item.done", names
    assert names[-1] == "response.completed", names


def test_responses_stream_delta_concatenation_equals_non_stream(
    client, resource, api_key, deployment
):
    """Concatenating the ``delta`` strings from
    ``response.output_text.delta`` events MUST equal the
    ``output_text`` field that the non-streaming path returns for the
    same input.
    """
    body = {
        "model": deployment["deployment_id"],
        "input": "Concatenation test — please echo this back deterministically.",
    }

    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json=body,
        headers=api_key["headers"],
    )
    assert resp.status_code == 200
    expected = resp.get_json()["output"][0]["content"][0]["text"]

    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={**body, "stream": True},
        headers=api_key["headers"],
    )
    events = _parse_sse(resp.get_data(as_text=True))
    deltas = [
        payload["delta"]
        for name, payload in events
        if name == "response.output_text.delta"
    ]
    assert "".join(deltas) == expected


def test_responses_stream_completed_event_carries_full_response(
    client, resource, api_key, deployment
):
    """The ``response.completed`` event MUST carry the full final
    response object (id, model, output, usage, status='completed')
    matching the non-streaming shape."""
    resp = client.post(
        f"/{resource['resource_id']}/openai/responses",
        json={
            "model": deployment["deployment_id"],
            "input": "completed-event shape",
            "stream": True,
        },
        headers=api_key["headers"],
    )
    events = _parse_sse(resp.get_data(as_text=True))
    completed = [payload for name, payload in events if name == "response.completed"]
    assert len(completed) == 1, [n for n, _ in events]
    full = completed[0]["response"]
    assert full["status"] == "completed"
    assert full["model"] == deployment["model"]
    assert full["object"] == "response"
    assert full["output"][0]["content"][0]["type"] == "output_text"
    assert "usage" in full
    assert full["id"].startswith("resp_")
