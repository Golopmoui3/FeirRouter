"""Тесты роутинга: стратегии, ledger, breaker, tiers, alias-дедупликация, failover.

Ответ на критику: раньше тестировалось только 'API отвечает', теперь — сама маршрутизация.
"""
import asyncio
import time
from types import SimpleNamespace

import pytest

import feirrouter.server as S
from feirrouter.routing.strategies import order_candidates
from feirrouter.routing.engine import QuotaLedger, CircuitBreaker, resolve_tier_slug, ledger_key, UPSTREAM_GROUPS


def mk(name, **kw):
    d = {"provider": name, "model": f"{name}-m", "priority": 5, "intelligence": 7,
         "price": 1.0, "penalty": 0, "open": True, "load": 0, "latency_ms": 500,
         "errors": 0, "rpm_left": 30, "tpd_left": 9000, "quota_reset_s": 3600,
         "cache_affinity": 0, "context": 128000}
    d.update(kw)
    return d


def test_strategy_priority():
    cs = [mk("a", priority=1), mk("b", priority=9)]
    assert order_candidates("priority", cs)[0]["provider"] == "b"


def test_strategy_cost_optimized():
    cs = [mk("a", price=5.0, intelligence=9), mk("b", price=0.0, intelligence=7)]
    assert order_candidates("cost-optimized", cs)[0]["provider"] == "b"


def test_strategy_round_robin_rotates():
    cs = [mk("a"), mk("b"), mk("c")]
    first = [c["provider"] for c in order_candidates("round-robin", cs)]
    second = [c["provider"] for c in order_candidates("round-robin", cs)]
    assert first != second and sorted(first) == ["a", "b", "c"]


def test_strategy_least_used_and_headroom():
    cs = [mk("a", load=10, rpm_left=1, tpd_left=1), mk("b", load=1, rpm_left=99, tpd_left=99)]
    assert order_candidates("least-used", cs)[0]["provider"] == "b"
    assert order_candidates("headroom", cs)[0]["provider"] == "b"


def test_strategy_lkgp_pins_last_good():
    cs = [mk("a"), mk("b")]
    out = order_candidates("lkgp", cs, {"last_good": ("b", "b-m")})
    assert out[0]["provider"] == "b"


def test_strategy_reset_window():
    cs = [mk("a", quota_reset_s=3600), mk("b", quota_reset_s=60)]
    assert order_candidates("reset-window", cs)[0]["provider"] == "b"


def test_strategy_fusion_panel_first():
    cs = [mk("a", intelligence=5), mk("b", intelligence=9), mk("c", intelligence=8)]
    out = order_candidates("fusion", cs)
    assert out[0]["provider"] == "b"  # самый умный — в панели первым


def test_ledger_rpm_and_cooldown():
    L = QuotaLedger()
    k = ("groq", "m", "")
    assert L.allow(k, rpm=2)
    L.record(k)
    L.record(k)
    assert not L.allow(k, rpm=2)  # лимит исчерпан — не пускаем ДО 429
    L.fail(("x", "m", ""), 429)
    assert not L.allow(("x", "m", ""))  # cooldown 120с после 429


def test_ledger_penalty_decay():
    L = QuotaLedger()
    k = ("groq", "m", "")
    L.fail(k, 500)
    assert L.penalty[k] > 0
    for _ in range(30):
        L.record(k)
    assert L.penalty[k] == 0  # decay до нуля успешными запросами


def test_breaker_three_states():
    B = CircuitBreaker()
    assert not B.is_open("groq")
    for _ in range(5):
        B.error("groq")
    assert B.is_open("groq")  # open после 5 ошибок
    B.opened_at["groq"] = time.time() - 61
    assert not B.is_open("groq")  # half-open → probe разрешён
    B.success("groq")
    assert B.fails["groq"] == 0


def test_tier_resolution():
    s = SimpleNamespace(MODEL="base/m", MODEL_OPUS="o/m", MODEL_SONNET="",
                        MODEL_HAIKU="h/m", MODEL_FABLE="")
    assert resolve_tier_slug("claude-opus-4-5", s) == "o/m"
    assert resolve_tier_slug("claude-sonnet-4", s) == "base/m"  # пустой SONNET → fallback
    assert resolve_tier_slug("haiku-turbo", s) == "h/m"
    assert resolve_tier_slug("auto", s) == "base/m"


def test_alias_dedup_shared_ledger_key():
    assert ledger_key("kimi", "k2") == ledger_key("moonshot", "k2") != ledger_key("groq", "k2")
    assert ledger_key("qwen", "x") == ledger_key("dashscope", "x") == ledger_key("bailian", "x")
    assert "kimi" in UPSTREAM_GROUPS and UPSTREAM_GROUPS["kimi"] == "moonshot"


def _canned(text="hi"):
    return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def test_failover_next_provider_on_429(monkeypatch):
    calls = []

    async def fake_chat(req, api_key, base_url, timeout):
        calls.append(req.model)
        if len(calls) == 1:
            raise Exception("429 rate limited")
        return _canned("second-wins")

    monkeypatch.setattr(S, "ledger", QuotaLedger())
    monkeypatch.setattr(S, "breaker", CircuitBreaker())
    monkeypatch.setattr(S, "seed_candidates", lambda: [
        {**mk("badprov"), "enabled": True}, {**mk("goodprov"), "enabled": True}])
    monkeypatch.setattr(S, "provider_creds", lambda p: ("k", "http://127.0.0.1:9"))
    monkeypatch.setattr(S.default_provider, "chat", fake_chat)
    prov, model, data = asyncio.run(S.run_chain([{"role": "user", "content": "hi"}], "auto", "priority", False))
    assert data["choices"][0]["message"]["content"] == "second-wins"
    assert len(calls) == 2  # первый упал → второй подхватил


def test_shared_upstream_cooldown_skips_alias(monkeypatch):
    """kimi упал с 429 → moonshot (тот же апстрим) пропускается: общий счётчик работает."""
    calls = []

    async def always_429(req, api_key, base_url, timeout):
        calls.append(req.model)
        raise Exception("429 rate limited")

    monkeypatch.setattr(S, "ledger", QuotaLedger())
    monkeypatch.setattr(S, "breaker", CircuitBreaker())
    monkeypatch.setattr(S, "seed_candidates", lambda: [
        {**mk("kimi", priority=9), "model": "k2", "enabled": True},
        {**mk("moonshot", priority=8), "model": "k2", "enabled": True}])
    monkeypatch.setattr(S, "provider_creds", lambda p: ("k", "http://127.0.0.1:9"))
    monkeypatch.setattr(S.default_provider, "chat", always_429)
    with pytest.raises(Exception):
        asyncio.run(S.run_chain([{"role": "user", "content": "hi"}], "auto", "priority", False))
    assert len(calls) == 1  # второй кандидат — тот же апстрим на cooldown → не дёргаем


def test_oauth_401_reresolves_once(monkeypatch):
    """401 у подписочного тира → один повтор с перечитанным токеном, а не уход на запасного."""
    chat_calls, creds_calls = [], []

    async def flaky_oauth(req, api_key, base_url, timeout):
        chat_calls.append(api_key)
        if len(chat_calls) == 1:
            raise Exception("401 Unauthorized")
        return _canned("oauth-recovered")

    def counting_creds(p):
        creds_calls.append(p)
        return ("STALE" if len(creds_calls) == 1 else "FRESH", "http://127.0.0.1:9")

    monkeypatch.setattr(S, "ledger", QuotaLedger())
    monkeypatch.setattr(S, "breaker", CircuitBreaker())
    monkeypatch.setattr(S, "seed_candidates", lambda: [{**mk("codex_oauth"), "enabled": True}])
    monkeypatch.setattr(S, "provider_creds", counting_creds)
    monkeypatch.setattr(S.default_provider, "chat", flaky_oauth)
    prov, model, data = asyncio.run(S.run_chain([{"role": "user", "content": "hi"}], "auto", "priority", False))
    assert data["choices"][0]["message"]["content"] == "oauth-recovered"
    assert chat_calls == ["STALE", "FRESH"]  # повтор пошёл уже со свежим ключом
    assert creds_calls == ["codex_oauth", "codex_oauth"]


def test_non_oauth_401_no_retry(monkeypatch):
    """401 у обычного API-ключа повтора не даёт — сразу failover (повтор бессмыслен)."""
    calls = []

    async def always_401(req, api_key, base_url, timeout):
        calls.append(1)
        raise Exception("401 Unauthorized")

    monkeypatch.setattr(S, "ledger", QuotaLedger())
    monkeypatch.setattr(S, "breaker", CircuitBreaker())
    monkeypatch.setattr(S, "seed_candidates", lambda: [{**mk("groq"), "enabled": True}])
    monkeypatch.setattr(S, "provider_creds", lambda p: ("k", "http://127.0.0.1:9"))
    monkeypatch.setattr(S.default_provider, "chat", always_401)
    with pytest.raises(Exception):
        asyncio.run(S.run_chain([{"role": "user", "content": "hi"}], "auto", "priority", False))
    assert len(calls) == 1


def test_status_of_prefers_response_code():
    resp = SimpleNamespace(status_code=503)
    assert S._status_of(SimpleNamespace(response=resp)) == 503
    assert S._status_of(Exception("429 slow down")) == 429
    assert S._status_of(Exception("boom")) == 500


def test_creds_resolution_does_not_stall_loop(monkeypatch):
    """Медленный резолв ключей (сетевой OAuth-refresh) не стопает event loop:
    два параллельных run_chain перекрываются во времени."""
    import time as _t

    def slow_creds(p):
        _t.sleep(0.3)
        return ("k", "http://127.0.0.1:9")

    async def fast_chat(req, api_key, base_url, timeout):
        return _canned("ok")

    monkeypatch.setattr(S, "ledger", QuotaLedger())
    monkeypatch.setattr(S, "breaker", CircuitBreaker())
    monkeypatch.setattr(S, "seed_candidates", lambda: [{**mk("groq"), "enabled": True}])
    monkeypatch.setattr(S, "provider_creds", slow_creds)
    monkeypatch.setattr(S.default_provider, "chat", fast_chat)

    async def both():
        return await asyncio.gather(
            S.run_chain([{"role": "user", "content": "a"}], "auto", "priority", False),
            S.run_chain([{"role": "user", "content": "b"}], "auto", "priority", False))

    t0 = _t.time()
    res = asyncio.run(both())
    dt = _t.time() - t0
    assert len(res) == 2
    assert dt < 0.55, f"loop stalled: {dt:.2f}s (serial would be >= 0.6s)"
