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
