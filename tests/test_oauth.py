"""Тесты OAuth: PKCE, обмен кода, refresh, import CLI creds, статусы."""
import base64
import hashlib
import json
import time
from types import SimpleNamespace
from pathlib import Path

from feirrouter import oauth as O


def test_pkce_pair_verifies():
    v, c = O.pkce_pair()
    assert len(v) >= 43
    expect = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    assert c == expect


def test_google_auth_url_shape():
    url, ch = O.build_google_auth_url("CID123", "verifier-abc")
    assert "accounts.google.com" in url and "CID123" in url
    assert "code_challenge_method=S256" in url and f"code_challenge={ch}" in url


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def test_exchange_google_code(monkeypatch):
    seen = {}

    def fake_post(url, data=None, timeout=None):
        seen.update(data)
        return _Resp({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})

    monkeypatch.setattr(O.httpx, "post", fake_post)
    blob = O.exchange_google_code("CID", "ver", "CODE123")
    assert blob["access_token"] == "AT" and blob["refresh_token"] == "RT"
    assert blob["refreshable"] and blob["expires_at"] > time.time()
    assert seen["code"] == "CODE123" and seen["code_verifier"] == "ver"


def test_refresh_google(monkeypatch):
    monkeypatch.setattr(O.httpx, "post",
                        lambda url, data=None, timeout=None: _Resp({"access_token": "AT2", "expires_in": 100}))
    new = O.refresh_google({"refresh_token": "RT", "client_id": "CID"})
    assert new["access_token"] == "AT2" and new["refresh_token"] == "RT"


def test_import_cli_creds(tmp_path: Path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".credentials.json").write_text(json.dumps(
        {"claudeAiOauth": {"accessToken": "CLA", "refreshToken": "CLR", "expiresAt": 9999999999999}}))
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": "CODEXKEY"}))
    res = O.import_cli_creds(tmp_path)
    assert res["claude_oauth"]["access_token"] == "CLA"
    assert res["claude_oauth"]["refreshable"] is False
    assert res["codex_oauth"]["access_token"] == "CODEXKEY"
    assert "not found" in res["gemini_oauth"]


def test_resolve_plain_passthrough():
    assert O.resolve_if_oauth("groq", "gsk-plain", SimpleNamespace()) == "gsk-plain"


def test_resolve_fresh_oauth_blob():
    blob = json.dumps({"access_token": "FRESH", "expires_at": time.time() + 9999})
    assert O.resolve_if_oauth("gemini_oauth", blob, SimpleNamespace()) == "FRESH"


def test_resolve_expired_google_refreshes(monkeypatch):
    blob = json.dumps({"access_token": "OLD", "refresh_token": "RT",
                       "expires_at": time.time() - 10, "refreshable": True, "client_id": "C"})
    saved = {}

    class FakeStore:
        def vault_set(self, p, v):
            saved[p] = v

    monkeypatch.setattr(O, "refresh_google",
                        lambda b: {**b, "access_token": "NEW", "expires_at": time.time() + 9999})
    assert O.resolve_if_oauth("gemini_oauth", blob, FakeStore()) == "NEW"
    assert "gemini_oauth" in saved


def test_status_all_none(monkeypatch):
    for k in ("CLAUDE_OAUTH_TOKEN", "CODEX_OAUTH_TOKEN", "GEMINI_OAUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    rows = O.oauth_status(SimpleNamespace(vault_get=lambda p: ""))
    assert all(r["source"] == "none" for r in rows) and len(rows) == 3
