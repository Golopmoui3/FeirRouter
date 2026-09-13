"""Format translation: OpenAI ↔ Anthropic ↔ Gemini ↔ Responses (OmniRoute idea)."""
from __future__ import annotations


def openai_to_anthropic(messages: list[dict], system: str | None = None) -> tuple[str, list[dict]]:
    sys = system or ""
    out = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            sys += ("\n" if sys else "") + (content if isinstance(content, str) else str(content))
            continue
        if role == "developer":  # OmniRoute role normalization
            role = "system"
            sys += ("\n" if sys else "") + str(content)
            continue
        text = content if isinstance(content, str) else " ".join(
            b.get("text", "") for b in content if isinstance(b, dict))
        out.append({"role": "assistant" if role == "assistant" else "user",
                    "content": [{"type": "text", "text": text}]})
    return sys, out


def anthropic_to_openai(system: str, messages: list[dict]) -> list[dict]:
    out = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        blocks = m.get("content", [])
        if isinstance(blocks, str):
            text = blocks
        else:
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        out.append({"role": m.get("role", "user"), "content": text})
    return out


def openai_to_gemini(messages: list[dict]) -> dict:
    contents = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else "user"
        text = m.get("content", "")
        if isinstance(text, list):
            text = " ".join(str(x) for x in text)
        if m.get("role") == "system":
            continue  # systemInstruction отдельно
        contents.append({"role": role, "parts": [{"text": str(text)}]})
    sys = " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
    body: dict = {"contents": contents}
    if sys:
        body["systemInstruction"] = {"parts": [{"text": sys}]}
    return body


def openai_to_responses(model: str, messages: list[dict], extra: dict | None = None) -> dict:
    """Codex Responses API input."""
    inp = []
    for m in messages:
        inp.append({"role": m.get("role", "user"),
                    "content": [{"type": "input_text", "text": str(m.get("content", ""))}]})
    body = {"model": model, "input": inp, "stream": bool((extra or {}).get("stream", False))}
    return body


def sanitize_openai_response(data: dict) -> dict:
    """OmniRoute response sanitization: strip non-standard fields breaking SDKs."""
    for choice in data.get("choices", []):
        msg = choice.get("message", {})
        for k in ("x_groq", "usage_breakdown", "service_tier", "reasoning_content", "think"):
            msg.pop(k, None)
    data.pop("usage_breakdown", None)
    return data
