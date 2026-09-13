"""Provider abstractions. FCC: BaseProvider + OpenAICompatibleProvider extensibility."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
import httpx


@dataclass
class ChatRequest:
    model: str
    messages: list
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    tools: list | None = None
    extra: dict | None = None


class BaseProvider(ABC):
    """Extend this for fully custom wire formats. For OpenAI-compatible — extend OpenAICompatibleProvider."""

    name: str = "base"
    api_format: str = "openai"  # openai | anthropic | gemini | responses

    @abstractmethod
    async def chat(self, req: ChatRequest, api_key: str, base_url: str, timeout: float) -> dict:
        ...

    async def stream_chat(self, req: ChatRequest, api_key: str, base_url: str, timeout: float):
        # default: non-streaming fallback as single chunk
        data = await self.chat(req, api_key, base_url, timeout)
        yield data


class OpenAICompatibleProvider(BaseProvider):
    """Default executor (OmniRoute DefaultExecutor). Covers Groq/Together/NVIDIA/OpenRouter/..."""

    api_format = "openai"

    async def chat(self, req: ChatRequest, api_key: str, base_url: str, timeout: float) -> dict:
        payload: dict = {"model": req.model, "messages": req.messages, "stream": False}
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.tools:
            payload["tools"] = req.tools
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(base_url.rstrip("/") + "/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            return r.json()

    async def stream_chat(self, req: ChatRequest, api_key: str, base_url: str, timeout: float):
        payload: dict = {"model": req.model, "messages": req.messages, "stream": True}
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.tools:
            payload["tools"] = req.tools
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "text/event-stream"}
        async with httpx.AsyncClient(timeout=timeout) as c:
            async with c.stream("POST", base_url.rstrip("/") + "/chat/completions", json=payload, headers=headers) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    yield data


class AnthropicLikeProvider(OpenAICompatibleProvider):
    """Providers speaking Anthropic Messages natively (Kimi/Wafer/Z.ai quirks handled in translation)."""
    api_format = "anthropic"


class GeminiLikeProvider(OpenAICompatibleProvider):
    """Gemini GenerateContent / v1beta surface."""
    api_format = "gemini"


class AnthropicMessagesProvider(BaseProvider):
    """Native Anthropic /v1/messages call (real Anthropic API + Claude subscription OAuth).

    In: ChatRequest (OpenAI-shape messages). Out: OpenAI-shape response
    (thinking → reasoning_content, usage mapped), so the shared chain works unchanged.
    """

    api_format = "anthropic"

    def build_request(self, req: ChatRequest) -> tuple[str, dict, dict]:
        from ..translation import formats as F
        system, amsgs = F.openai_to_anthropic(req.messages)
        body: dict = {"model": req.model, "max_tokens": req.max_tokens or 1024, "messages": amsgs}
        if system:
            body["system"] = system
        if req.tools:
            body["tools"] = req.tools
        is_oauth = (req.extra or {}).get("auth") == "oauth" or req.model.startswith("oauth")
        headers = {"anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        return ("oauth" if is_oauth else "key", body, headers)

    @staticmethod
    def normalize(data: dict, model: str) -> dict:
        text_parts, thinking_parts = [], []
        for b in data.get("content", []) or []:
            if b.get("type") == "text":
                text_parts.append(b.get("text", ""))
            elif b.get("type") == "thinking":
                thinking_parts.append(b.get("thinking", ""))
        msg: dict = {"role": "assistant", "content": "".join(text_parts)}
        if thinking_parts:
            msg["reasoning_content"] = "\n".join(thinking_parts)
        usage = data.get("usage", {}) or {}
        return {"id": data.get("id", "msg_feir"), "object": "chat.completion",
                "model": model,
                "choices": [{"index": 0, "message": msg,
                             "finish_reason": "stop" if data.get("stop_reason") in (None, "end_turn") else "tool_calls"}],
                "usage": {"prompt_tokens": usage.get("input_tokens", 0),
                          "completion_tokens": usage.get("output_tokens", 0),
                          "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)}}

    async def chat(self, req: ChatRequest, api_key: str, base_url: str, timeout: float) -> dict:
        mode, body, headers = self.build_request(req)
        if mode == "oauth":
            headers["Authorization"] = f"Bearer {api_key}"
            headers["anthropic-beta"] = "oauth-2025-04-20"
        else:
            headers["x-api-key"] = api_key
        url = base_url.rstrip("/") + ("" if base_url.rstrip("/").endswith("/messages") else "/messages")
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, json=body, headers=headers)
            r.raise_for_status()
            return self.normalize(r.json(), req.model)


# Singleton default used when provider has no quirks
default_provider = OpenAICompatibleProvider()
anthropic_provider = AnthropicMessagesProvider()
