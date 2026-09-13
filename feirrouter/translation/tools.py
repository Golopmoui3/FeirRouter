"""Heuristic tool parser (FCC): models returning tool calls as text → structured tool_use."""
from __future__ import annotations
import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_TAG_RE = re.compile(r"<toolcall>(.*?)</toolcall>", re.S | re.I)


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
