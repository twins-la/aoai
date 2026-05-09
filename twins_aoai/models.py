"""Response builders for the Azure OpenAI data-plane shapes.

References (retrieved 2026-05-08):
  - https://learn.microsoft.com/en-us/azure/ai-services/openai/reference
  - https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/migration

The twin returns the OpenAI-compatible response shape Azure documents on
its data-plane endpoints. Token counts are approximated (4 chars/token);
embeddings are deterministic synthetic vectors so identical inputs give
identical outputs across runs.
"""

import hashlib
import math
import struct
from datetime import datetime, timezone
from typing import Sequence


def now_iso_z() -> str:
    """ISO-8601 UTC timestamp with millisecond precision and ``Z`` suffix."""
    n = datetime.now(tz=timezone.utc)
    return f"{n.strftime('%Y-%m-%dT%H:%M:%S')}.{n.microsecond // 1000:03d}Z"


def now_unix() -> int:
    """Unix epoch seconds — the ``created`` field on completion responses."""
    return int(datetime.now(tz=timezone.utc).timestamp())


def count_tokens_text(text: str) -> int:
    """Cheap synthetic token count — 4 chars per token, ceil-rounded."""
    if not text:
        return 0
    return (len(text) + 3) // 4


def build_synthetic_chat_text(messages: Sequence[dict], model: str) -> str:
    """Deterministic synthetic assistant reply.

    Mirrors the Anthropic twin's behaviour: returns a short
    "Twin echoing back: ..." style message that quotes the most recent
    user input. Operators driving fixtures get stable, inspectable
    responses without ever calling a real model.
    """
    last_user = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                last_user = content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        last_user = part.get("text", "")
                        break
            break
    if not last_user:
        return f"[aoai-twin:{model}] hello — no user message provided."
    return f"[aoai-twin:{model}] echoing: {last_user}"


def build_chat_completion(
    *,
    completion_id: str,
    model: str,
    content_text: str,
    prompt_tokens: int,
    completion_tokens: int,
    finish_reason: str = "stop",
) -> dict:
    """OpenAI-compatible ``chat.completion`` response object."""
    return {
        "id": f"chatcmpl-{completion_id}",
        "object": "chat.completion",
        "created": now_unix(),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content_text},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _extract_response_input_text(input_value) -> str:
    """Pull a plain-text echo out of the Responses API ``input`` field.

    ``input`` accepts either a string or a list of input items per
    https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#responses.
    Items can be ``{"type": "input_text", "text": "..."}`` or shorthand
    role-content pairs; mirror enough of the shape that consumer code
    using either form sees a non-empty ``output_text`` back.
    """
    if isinstance(input_value, str):
        return input_value
    if isinstance(input_value, list):
        for item in reversed(input_value):
            if isinstance(item, dict):
                if item.get("type") == "input_text" and isinstance(item.get("text"), str):
                    return item["text"]
                content = item.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") in ("input_text", "text"):
                            text = part.get("text", "")
                            if isinstance(text, str) and text:
                                return text
    return ""


def build_synthetic_response_text(input_value, model: str) -> str:
    """Deterministic synthetic Responses-API output text."""
    last = _extract_response_input_text(input_value)
    if not last:
        return f"[aoai-twin:{model}] hello — no input provided."
    return f"[aoai-twin:{model}] echoing: {last}"


def build_response(
    *,
    response_id: str,
    model: str,
    output_text: str,
    input_tokens: int,
    output_tokens: int,
    status: str = "completed",
) -> dict:
    """Azure OpenAI Responses-API ``response`` object.

    Mirrors the documented shape (https://learn.microsoft.com/en-us/azure/
    ai-services/openai/reference#responses, retrieved 2026-05-09): a
    flat envelope with an ``output`` array of message-shaped items. The
    twin emits a single message item whose content is one ``output_text``
    block — sufficient for SDK round-tripping without committing to a
    full tool-call / multi-turn shape.
    """
    return {
        "id": f"resp_{response_id}",
        "object": "response",
        "created_at": now_unix(),
        "status": status,
        "model": model,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": output_text},
                ],
            }
        ],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }


def build_completion(
    *,
    completion_id: str,
    model: str,
    text: str,
    prompt_tokens: int,
    completion_tokens: int,
    finish_reason: str = "stop",
) -> dict:
    """Legacy ``completion`` response object (Azure still ships this surface)."""
    return {
        "id": f"cmpl-{completion_id}",
        "object": "text_completion",
        "created": now_unix(),
        "model": model,
        "choices": [
            {
                "index": 0,
                "text": text,
                "finish_reason": finish_reason,
                "logprobs": None,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def synthetic_embedding(text: str, *, dims: int = 1536) -> list[float]:
    """Deterministic synthetic embedding vector.

    Uses SHA-256 of the input text as a seed to fill ``dims`` floats in
    [-1, 1]. L2-normalised so callers comparing cosine similarity get
    sensible values for identical inputs.
    """
    if dims <= 0:
        return []
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    raw: list[float] = []
    counter = 0
    while len(raw) < dims:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        # Each block yields 8 floats from 8-byte chunks.
        for i in range(0, 32, 4):
            word = struct.unpack(">I", block[i : i + 4])[0]
            # Map [0, 2^32) → [-1, 1).
            raw.append((word / 2_147_483_648.0) - 1.0)
            if len(raw) >= dims:
                break
        counter += 1
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]


def build_embedding_response(
    *,
    model: str,
    vectors: list[list[float]],
    prompt_tokens: int,
) -> dict:
    """OpenAI-compatible embeddings response shape."""
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": vec}
            for i, vec in enumerate(vectors)
        ],
        "model": model,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "total_tokens": prompt_tokens,
        },
    }
