"""Heuristic tool parser (FCC): models returning tool calls as text → structured tool_use."""
from __future__ import annotations
import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_TAG_RE = re.compile(r"<toolcall>(.*?)</toolcall>", re.S | re.I)

# 200-with-error-text: апстрим вернул HTTP 200, но контент — жалоба биллинга/ключа,
# а не ответ (живой кейс: Pollinations "reached its budget"). Такое — в failover,
# а не пользователю. Паттерны узкие: content-policy отказы — легитимные ответы, их НЕ трогаем.
_SOFT_ERROR_RES = [
    re.compile(r"reached its budget", re.I),
    re.compile(r"raise the key budget", re.I),
    re.compile(r"incorrect api key|invalid api key|invalid_api_key", re.I),
    re.compile(r"account .{0,20}suspended", re.I),
    re.compile(r"quota exceeded.{0,40}(bill|upgrade|plan)", re.I),
]


def is_upstream_soft_error(text: str) -> bool:
    """True, если текст — жалоба апстрима на ключ/квоту, а не ответ модели."""
    t = text or ""
    if len(t) > 2000:  # проверяем голову — жалобы всегда в начале
        t = t[:2000]
    return any(p.search(t) for p in _SOFT_ERROR_RES)


def parse_text_tool_calls(text: str) -> tuple[str, list[dict]]:
    """Returns (cleaned_text, tool_calls[{id,name,arguments}])."""
    calls: list[dict] = []
    for pat in (_TAG_RE, _FENCE_RE):
        for m in pat.findall(text or ""):
            try:
                obj = json.loads(m)
                if isinstance(obj, dict) and ("name" in obj or "function" in obj):
                    name = obj.get("name") or obj.get("function", {}).get("name", "tool")
                    args = obj.get("arguments", obj.get("parameters", {}))
                    calls.append({"id": f"call_{len(calls)}", "name": name, "arguments": args})
            except Exception:
                continue
    cleaned = _TAG_RE.sub("", text or "").strip()
    return cleaned, calls
