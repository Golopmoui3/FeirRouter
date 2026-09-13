"""Тесты пайплайна: probes, compression, guardrails, tools, thinking, translation."""
from feirrouter.optimization.probes import try_probe_mock, mock_openai_response
from feirrouter.optimization.compression import compress_messages
from feirrouter.translation import formats as F
from feirrouter.translation.thinking import to_anthropic_blocks, extract_thinking
from feirrouter.translation.tools import parse_text_tool_calls
from feirrouter.server import apply_guardrails


def test_probe_detected_and_normal_passes():
    assert try_probe_mock({"messages": [{"content": "network probe connectivity check"}]}) is not None
    assert try_probe_mock({"messages": [{"content": "write a quicksort in python"}]}) is None
    assert mock_openai_response({"content": "ok", "role": "probe"})["choices"][0]["message"]["content"] == "ok"


def test_compression_shrinks_tool_output():
    big = "\n".join(["trace line abcdef " * 20] * 300)
    msgs = [{"role": "user", "content": big}]
    out, stat = compress_messages(msgs, level=2)
    assert stat["saved_pct"] > 30
    assert "compressed" in out[0]["content"]


def test_compression_keeps_small_intact():
    msgs = [{"role": "user", "content": "hello"}]
    out, stat = compress_messages(msgs, level=2)
    assert out[0]["content"] == "hello" and stat["saved_chars"] == 0


def test_guardrails_redact_pii(monkeypatch):
    monkeypatch.setenv("FEIR_GUARDRAILS", "true")
    msgs = [{"role": "user", "content": "mail me at ivan@example.com, key sk-abcdef123456"}]
    out, red = apply_guardrails(msgs)
    assert red and "ivan@example.com" not in out[0]["content"] and "[REDACTED]" in out[0]["content"]


def test_guardrails_off_by_default(monkeypatch):
    monkeypatch.delenv("FEIR_GUARDRAILS", raising=False)
    msgs = [{"role": "user", "content": "ivan@example.com"}]
    out, red = apply_guardrails(msgs)
    assert not red and out[0]["content"] == "ivan@example.com"


def test_tool_parser():
    cleaned, calls = parse_text_tool_calls('do it <toolcall>{"name": "read", "arguments": {"f": "a"}}</toolcall> done')
    assert len(calls) == 1 and calls[0]["name"] == "read"
    assert "toolcall" not in cleaned
    _, none = parse_text_tool_calls("just plain text")
    assert none == []


def test_thinking_blocks():
    t, clean = extract_thinking("<think>plan</think>answer")
    assert t == "plan" and clean == "answer"
    blocks = to_anthropic_blocks("<think>plan</think>answer")
    assert blocks[0]["type"] == "thinking" and blocks[1] == {"type": "text", "text": "answer"}
    blocks2 = to_anthropic_blocks("plain", reasoning_content="rc")
    assert blocks2[0] == {"type": "thinking", "thinking": "rc"}


def test_translation_roundtrip():
    oai = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}]
    sys, amsgs = F.openai_to_anthropic(oai)
    assert sys == "sys" and amsgs[0]["content"][0]["text"] == "hello"
    back = F.anthropic_to_openai(sys, amsgs)
    assert back[0] == {"role": "system", "content": "sys"}
    assert F.openai_to_gemini(oai)["contents"][0]["role"] == "user"
    assert F.sanitize_openai_response({"choices": [{"message": {"x_groq": 1, "content": "ok"}}]})["choices"][0]["message"] == {"content": "ok"}
