"""Тесты параллельного fusion: fan-out + judge + фолбэки."""
import asyncio

import pytest
from fastapi import HTTPException

import feirrouter.server as S
from feirrouter.routing.engine import QuotaLedger, CircuitBreaker


def _seeds():
    return [
        {"provider": "groq", "model": "x", "priority": 9, "intelligence": 7, "price": 0.0,
         "penalty": 0, "open": True, "load": 0, "latency_ms": 100, "errors": 0,
         "rpm_left": 99, "tpd_left": 9999, "quota_reset_s": 60, "cache_affinity": 0,
         "context": 128000, "enabled": True},
        {"provider": "deepseek", "model": "y", "priority": 8, "intelligence": 7, "price": 0.0,
         "penalty": 0, "open": True, "load": 0, "latency_ms": 100, "errors": 0,
         "rpm_left": 99, "tpd_left": 9999, "quota_reset_s": 60, "cache_affinity": 0,
         "context": 128000, "enabled": True},
        {"provider": "cerebras", "model": "j", "priority": 7, "intelligence": 9, "price": 0.0,
         "penalty": 0, "open": True, "load": 0, "latency_ms": 100, "errors": 0,
         "rpm_left": 99, "tpd_left": 9999, "quota_reset_s": 60, "cache_affinity": 0,
         "context": 128000, "enabled": True},
    ]


def _setup(monkeypatch, texts: dict, fail_models: set | None = None, judge_fail: bool = False):
    # панель/judge отбираются по НАЛИЧИЮ ключей — эмулируем вбитые ключи пользователя
    monkeypatch.setenv("GROQ_API_KEY", "t")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "t")
    monkeypatch.setenv("CEREBRAS_API_KEY", "t")
    async def fake_chat(req, api_key, base_url, timeout):
        if judge_fail and any(m.get("role") == "system" and "strict judge" in str(m.get("content", ""))
                              for m in req.messages):
            raise Exception("500 judge down")
        if req.model in (fail_models or set()):
            raise Exception("500 panel member down")
        return {"choices": [{"message": {"role": "assistant", "content": texts.get(req.model, "empty")},
                             "finish_reason": "stop"}]}
    monkeypatch.setattr(S, "ledger", QuotaLedger())
    monkeypatch.setattr(S, "breaker", CircuitBreaker())
    monkeypatch.setattr(S, "seed_candidates", _seeds)
    monkeypatch.setattr(S, "provider_creds", lambda p: ("k", "http://127.0.0.1:9"))
    monkeypatch.setattr(S.default_provider, "chat", fake_chat)


def test_fusion_explicit_panel_judge_synthesizes(monkeypatch):
    _setup(monkeypatch, {"x": "ans-x", "y": "ans-y", "j": "JUDGED-VERDICT"})
    prov, model, data = asyncio.run(S.run_fusion(
        [{"role": "user", "content": "q"}], explicit=["groq/x", "deepseek/y"]))
    txt = data["choices"][0]["message"]["content"]
    assert txt == "JUDGED-VERDICT"
    assert data["_fusion_via"].startswith("fusion:groq/x,deepseek/y+judge:cerebras/j")
    assert prov == "fusion"


def test_fusion_single_ok_returns_it(monkeypatch):
    _setup(monkeypatch, {"y": "only-survivor"}, fail_models={"x"})
    prov, model, data = asyncio.run(S.run_fusion(
        [{"role": "user", "content": "q"}], explicit=["groq/x", "deepseek/y"]))
    assert data["choices"][0]["message"]["content"] == "only-survivor"
    assert "single-ok" in data["_fusion_via"]


def test_fusion_all_fail_502(monkeypatch):
    _setup(monkeypatch, {}, fail_models={"x", "y"})
    with pytest.raises(HTTPException):
        asyncio.run(S.run_fusion([{"role": "user", "content": "q"}], explicit=["groq/x", "deepseek/y"]))


def test_fusion_judge_down_falls_back_to_longest(monkeypatch):
    _setup(monkeypatch, {"x": "short", "y": "much-longer-panel-answer"}, fail_models={"j"})
    prov, model, data = asyncio.run(S.run_fusion(
        [{"role": "user", "content": "q"}], explicit=["groq/x", "deepseek/y"]))
    assert data["choices"][0]["message"]["content"] == "much-longer-panel-answer"
    assert "fallback-longest" in data["_fusion_via"]


def test_fusion_endpoint_header(monkeypatch):
    from fastapi.testclient import TestClient
    _setup(monkeypatch, {"x": "ans-x", "y": "ans-y", "j": "J"})
    c = TestClient(S.app)
    r = c.post("/v1/chat/completions", json={
        "model": "fusion:groq/x+deepseek/y",
        "messages": [{"role": "user", "content": "q"}]})
    assert r.status_code == 200
    assert r.headers["X-Routed-Via"].startswith("fusion:")


def test_fusion_auto_panel(monkeypatch):
    """Без explicit-панели топ-N собирается из auto-цепочки сам."""
    _setup(monkeypatch, {"x": "ans-x", "y": "ans-y", "j": "JUDGED-AUTO"})
    prov, model, data = asyncio.run(S.run_fusion([{"role": "user", "content": "q"}]))
    assert data["choices"][0]["message"]["content"] == "JUDGED-AUTO"
    via = data["_fusion_via"]
    assert via.startswith("fusion:") and "+judge:cerebras/j" in via
    assert "groq/x" in via and "deepseek/y" in via


def test_fusion_partial_panel_judge_down(monkeypatch):
    """2 из 3 выжили, judge упал → самый длинный из выживших."""
    _setup(monkeypatch, {"y": "medium-answer", "j": "tiny"}, fail_models={"x"}, judge_fail=True)
    prov, model, data = asyncio.run(S.run_fusion(
        [{"role": "user", "content": "q"}], explicit=["groq/x", "deepseek/y", "cerebras/j"]))
    assert data["choices"][0]["message"]["content"] == "medium-answer"
    assert "fallback-longest" in data["_fusion_via"]
    assert "deepseek/y" in data["_fusion_via"] and "cerebras/j" in data["_fusion_via"]


def test_fusion_empty_answer_excluded(monkeypatch):
    """Пустой ответ члена панели не участвует в синтезе."""
    _setup(monkeypatch, {"x": "", "y": "real-answer", "j": "J"})
    prov, model, data = asyncio.run(S.run_fusion(
        [{"role": "user", "content": "q"}], explicit=["groq/x", "deepseek/y"]))
    assert data["choices"][0]["message"]["content"] in ("J", "real-answer")
    assert "groq/x" not in data["_fusion_via"]


def test_fusion_member_in_cooldown_skipped(monkeypatch):
    """Член панели в shared-cooldown не дёргается (quota-каскад)."""
    from feirrouter.routing.engine import ledger_key
    L = QuotaLedger()
    L.fail(ledger_key("groq", "x"), 429)  # groq/x на cooldown
    monkeypatch.setattr(S, "ledger", L)
    monkeypatch.setattr(S, "breaker", CircuitBreaker())
    monkeypatch.setattr(S, "seed_candidates", _seeds)
    monkeypatch.setattr(S, "provider_creds", lambda p: ("k", "http://127.0.0.1:9"))
    calls = []

    async def fake_chat(req, api_key, base_url, timeout):
        calls.append(req.model)
        return {"choices": [{"message": {"role": "assistant", "content": f"t-{req.model}"},
                             "finish_reason": "stop"}]}

    monkeypatch.setattr(S.default_provider, "chat", fake_chat)
    prov, model, data = asyncio.run(S.run_fusion(
        [{"role": "user", "content": "q"}], explicit=["groq/x", "deepseek/y"]))
    assert "x" not in calls  # groq/x пропущен молча
    assert data["choices"][0]["message"]["content"] in ("t-y",)
