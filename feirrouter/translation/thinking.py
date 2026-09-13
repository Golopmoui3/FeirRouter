"""Thinking blocks: <think> + reasoning_content → native Claude thinking (FCC idea)."""
from __future__ import annotations
import re

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.S | re.I)


def extract_thinking(text: str) -> tuple[str, str]:
    """Returns (thinking, cleaned_text)."""
    m = _THINK_RE.findall(text or "")
    thinking = "\n".join(m).strip()
    cleaned = _THINK_RE.sub("", text or "").strip()
    return thinking, cleaned


def to_anthropic_blocks(text: str, reasoning_content: str | None = None) -> list[dict]:
    thinking, cleaned = extract_thinking(text or "")
    if reasoning_content and not thinking:
        thinking = reasoning_content
    blocks: list[dict] = []
    if thinking:
        blocks.append({"type": "thinking", "thinking": thinking})
    if cleaned:
        blocks.append({"type": "text", "text": cleaned})
    return blocks or [{"type": "text", "text": ""}]
