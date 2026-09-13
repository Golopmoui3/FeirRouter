"""Request optimization: 5 trivial Claude Code probes answered locally (FCC idea).

1. quota/network probe mock
2. title generation skip
3. prefix detection (fast local)
4. suggestion mode skip
5. filepath extraction mock
Saves quota + latency.
"""
from __future__ import annotations


def try_probe_mock(body: dict) -> dict | None:
    msgs = body.get("messages", []) or []
    text = " ".join(str(m.get("content", "")) for m in msgs[-2:] if isinstance(m, dict)).lower()
    if not text:
        return None
    if "network probe" in text or "connectivity check" in text or "quota probe" in text:
        return {"role": "probe", "mock": True, "content": "ok"}
    if "generate title" in text or "summarize title" in text:
        first = text[:40]
        return {"role": "title", "mock": True, "content": first}
    if text.strip().startswith("prefix:") or "prefix detection" in text:
        return {"role": "prefix", "mock": True, "content": "code"}
    if "suggestion" in text and len(text) < 200:
        return {"role": "suggestion", "mock": True, "content": ""}
    if "extract filepath" in text or "filepath extraction" in text:
        return {"role": "filepath", "mock": True, "content": ""}
    return None


def mock_anthropic_response(mock: dict) -> dict:
    return {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "model": "mock",
        "content": [{"type": "text", "text": mock.get("content", "ok")}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 0, "output_tokens": 1},
        "_mock": mock.get("role", "probe"),
    }


def mock_openai_response(mock: dict, model: str = "mock") -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": mock.get("content", "ok")},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 1, "total_tokens": 1},
        "_mock": mock.get("role", "probe"),
    }
