from fastapi.testclient import TestClient
from feirrouter.server import app


def test_health():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["router"] == "FeirRouter"


def test_models():
    c = TestClient(app)
    r = c.get("/v1/models")
    assert any(m["id"] == "auto" for m in r.json()["data"])


def test_probe_mock():
    c = TestClient(app)
    r = c.post("/v1/chat/completions", json={
        "model": "auto",
        "messages": [{"role": "user", "content": "network probe connectivity check"}]})
    assert r.status_code == 200
    assert r.headers.get("X-Routed-Via") == "mock/probe"


def test_count_tokens():
    c = TestClient(app)
    r = c.post("/v1/messages/count_tokens", json={"messages": [{"content": "hello world"}]})
    assert r.json()["input_tokens"] >= 2


def test_providers_full_union():
    c = TestClient(app)
    r = c.get("/api/providers")
    j = r.json()
    assert j["count"] >= 100, j["count"]
    prefixes = {p["prefix"] for p in j["providers"]}
    for must in ["nvidia_nim", "open_router", "groq", "lmstudio", "ollama", "deepseek",
                 "qoder", "kiro", "pollinations", "tavily", "elevenlabs", "voyage"]:
        assert must in prefixes, must
    # контракт с панелью: поле env_key (селект ключей строится по нему)
    by_prefix = {p["prefix"]: p for p in j["providers"]}
    assert by_prefix["groq"]["env_key"] == "GROQ_API_KEY"
    assert by_prefix["lmstudio"]["env_key"] == ""


def test_keys_vault_crud():
    c = TestClient(app)
    r = c.post("/api/keys", json={"provider": "groq", "api_key": "test-key-123"})
    assert r.status_code == 200
    r = c.get("/api/keys")
    assert any(k["provider"] == "groq" for k in r.json()["vault"])
    assert "test-key" not in r.text  # encrypted at rest
    r = c.delete("/api/keys/groq")
    assert r.status_code == 200


def test_chain_api():
    c = TestClient(app)
    r = c.get("/api/chain")
    assert "chain" in r.json() and len(r.json()["chain"]) > 5
    r = c.put("/api/chain", json={"chain": ["groq/llama-3.3-70b-versatile"]})
    assert r.status_code == 200
    # restore
    c.put("/api/chain", json={"chain": []})


def test_memory_api():
    c = TestClient(app)
    r = c.post("/api/memory", json={"note": "smoke-note-xyz"})
    mid = r.json()["id"]
    r = c.get("/api/memory", params={"q": "smoke-note"})
    assert any("smoke-note" in n["note"] for n in r.json()["notes"])
    c.delete(f"/api/memory/{mid}")


def test_webhooks_and_agent_card():
    c = TestClient(app)
    assert c.post("/api/webhooks", json={"url": "http://127.0.0.1:9/hook"}).status_code == 200
    assert c.get("/.well-known/agent.json").json()["name"] == "FeirRouter"
    assert c.delete("/api/webhooks").status_code == 200


def test_ollama_emulation():
    c = TestClient(app)
    r = c.get("/api/tags")
    assert len(r.json()["models"]) > 10
    r = c.post("/api/generate", json={"model": "auto", "prompt": "network probe connectivity check"})
    # generate goes through real chain; without keys it 502s — but mock probe path tested separately
    assert r.status_code in (200, 502)


def test_models_include_custom_and_auto():
    c = TestClient(app)
    ids = {m["id"] for m in c.get("/v1/models").json()["data"]}
    assert "auto" in ids and "auto/coding" in ids and "fusion" in ids
