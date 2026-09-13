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


# Singleton default used when provider has no quirks
default_provider = OpenAICompatibleProvider()
