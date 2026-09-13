"""OAuth для подписочных тиров (OmniRoute Tier-1, честный объём).

Что реально работает:
- Google (gemini_oauth): документированный OAuth2 PKCE loopback-flow. Нужен свой
  OAuth-клиент типа "Desktop app" из Google Cloud Console (5 минут, бесплатно).
  Refresh — автоматически по refresh_token.
- Импорт своих же токенов из официальных CLI (как у CCR/OmniRoute "local login import"):
  Claude Code (~/.claude/.credentials.json), Codex CLI (~/.codex/auth.json),
  Gemini CLI (~/.muse/oauth_creds.json) → шифрованный vault. Команда = согласие.
  Refresh у них проприетарный → при протухании просто повтори import (статус подскажет).

Чего НЕТ и почему:
- GitHub device-flow не делаем: токен OAuth App не даёт scope models:read,
  для GitHub Models нужен PAT — вводится вручную через vault/env.
- Claude/Codex OAuth через браузер не реверсим: недокументировано,
  это нарушало бы ToS-friendly принцип. Только import своих токенов.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import queue
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = "https://www.googleapis.com/auth/cloud-platform"
CALLBACK_PORT = 8765

SUBSCRIPTION_PROVIDERS = ("claude_oauth", "codex_oauth", "gemini_oauth")


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_google_auth_url(client_id: str, verifier: str, port: int = CALLBACK_PORT) -> tuple[str, str]:
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    qs = urlencode({"response_type": "code", "client_id": client_id,
                    "redirect_uri": f"http://127.0.0.1:{port}/callback",
                    "scope": GOOGLE_SCOPES, "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "access_type": "offline", "prompt": "consent"})
    return GOOGLE_AUTH_URL + "?" + qs, challenge


def wait_for_code(port: int = CALLBACK_PORT, timeout: int = 180) -> str:
    q: queue.Queue = queue.Queue()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            code = parse_qs(urlparse(self.path).query).get("code", [""])[0]
            q.put(code)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h1>OK — вернись в терминал</h1>".encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        code = q.get(timeout=timeout)
    finally:
        srv.shutdown()
    if not code:
        raise RuntimeError("no code in callback (доступ запрещён или таймаут)")
    return code


def exchange_google_code(client_id: str, verifier: str, code: str,
                         client_secret: str = "", port: int = CALLBACK_PORT) -> dict:
    body = {"grant_type": "authorization_code", "code": code, "client_id": client_id,
            "redirect_uri": f"http://127.0.0.1:{port}/callback", "code_verifier": verifier}
    if client_secret:
        body["client_secret"] = client_secret
    r = httpx.post(GOOGLE_TOKEN_URL, data=body, timeout=30)
    r.raise_for_status()
    tok = r.json()
    return {"type": "oauth", "provider": "gemini_oauth",
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token", ""),
            "expires_at": time.time() + int(tok.get("expires_in", 3600)),
            "refreshable": True, "client_id": client_id}


def refresh_google(blob: dict) -> dict:
    if not blob.get("refresh_token"):
        raise RuntimeError("no refresh_token — повтори login")
    body = {"grant_type": "refresh_token", "refresh_token": blob["refresh_token"],
            "client_id": blob.get("client_id", "")}
    r = httpx.post(GOOGLE_TOKEN_URL, data=body, timeout=30)
    r.raise_for_status()
    tok = r.json()
    blob = {**blob, "access_token": tok["access_token"],
            "expires_at": time.time() + int(tok.get("expires_in", 3600))}
    if tok.get("refresh_token"):
        blob["refresh_token"] = tok["refresh_token"]
    return blob


def login_google(client_id: str, client_secret: str = "", no_browser: bool = False) -> dict:
    verifier, _ = pkce_pair()
    url, _ = build_google_auth_url(client_id, verifier)
    if not no_browser:
        webbrowser.open(url)
    print("Открой в браузере (если не открылся сам):\n" + url)
    code = wait_for_code()
    return exchange_google_code(client_id, verifier, code, client_secret)


def import_cli_creds(home: Path | None = None) -> dict[str, str]:
    """Читает ТОЛЬКО свои локальные файлы официальных CLI. Возвращает статусы."""
    home = home or Path.home()
    out: dict[str, str] = {}
    # Claude Code
    try:
        raw = json.loads((home / ".claude" / ".credentials.json").read_text(encoding="utf-8"))
        o = raw.get("claudeAiOauth", {})
        if o.get("accessToken"):
            out["claude_oauth"] = {"type": "oauth", "provider": "claude_oauth",
                                   "access_token": o["accessToken"],
                                   "refresh_token": o.get("refreshToken", ""),
                                   "expires_at": int(o.get("expiresAt", 0)) / 1000 or time.time() + 3600,
                                   "refreshable": False}
        else:
            out["claude_oauth"] = "file found, no claudeAiOauth.accessToken"
    except FileNotFoundError:
        out["claude_oauth"] = "not found (~/.claude/.credentials.json — сделай `claude login`)"
    except Exception as e:
        out["claude_oauth"] = f"parse error: {e}"[:120]
    # Codex CLI
    try:
        raw = json.loads((home / ".codex" / "auth.json").read_text(encoding="utf-8"))
        tok = (raw.get("tokens") or {}).get("access_token") or raw.get("OPENAI_API_KEY", "")
        out["codex_oauth"] = ({"type": "oauth", "provider": "codex_oauth",
                               "access_token": tok, "refresh_token": "",
                               "expires_at": time.time() + 3600 * 20, "refreshable": False}
                              if tok else "file found, no token")
    except FileNotFoundError:
        out["codex_oauth"] = "not found (~/.codex/auth.json — сделай `codex login`)"
    except Exception as e:
        out["codex_oauth"] = f"parse error: {e}"[:120]
    # Gemini CLI
    try:
        raw = json.loads((home / ".muse" / "oauth_creds.json").read_text(encoding="utf-8"))
        acc = raw.get("access_token") or raw.get("access") or ""
        if acc:
            exp = raw.get("expiry_date") or raw.get("expires_at") or 0
            try:
                exp = int(exp) / 1000 if int(exp) > 10**12 else int(exp)
            except Exception:
                exp = time.time() + 3600
            out["gemini_oauth"] = {"type": "oauth", "provider": "gemini_oauth",
                                   "access_token": acc,
                                   "refresh_token": raw.get("refresh_token") or raw.get("refresh") or "",
                                   "expires_at": exp or time.time() + 3600, "refreshable": False}
        else:
            out["gemini_oauth"] = "file found, no access token"
    except FileNotFoundError:
        out["gemini_oauth"] = "not found (~/.muse/oauth_creds.json — сделай `gemini login`)"
    except Exception as e:
        out["gemini_oauth"] = f"parse error: {e}"[:120]
    return out


def resolve_if_oauth(prefix: str, value: str, store) -> str:
    """Vault/env значение → живой access token. Plain-ключи возвращаются как есть."""
    try:
        blob = json.loads(value)
    except Exception:
        return value
    if not isinstance(blob, dict) or "access_token" not in blob:
        return value
    if blob.get("expires_at", 0) - time.time() > 60:
        return blob["access_token"]
    # протух: google умеем рефрешить, остальные — только re-import
    if blob.get("refreshable") and blob.get("refresh_token") and prefix == "gemini_oauth":
        try:
            new_blob = refresh_google(blob)
            from .security.keys import encrypt
            from .config import settings
            store.vault_set(prefix, encrypt(settings.FEIR_MASTER_KEY, json.dumps(new_blob)))
            return new_blob["access_token"]
        except Exception:
            return blob["access_token"]  # пусть апстрим вернёт 401 → сработает failover
    return blob["access_token"]


def oauth_status(store) -> list[dict]:
    rows = []
    for prefix in SUBSCRIPTION_PROVIDERS:
        src, note = "none", "no token — `oauth login` / `oauth import` / env"
        val = os.getenv({"claude_oauth": "CLAUDE_OAUTH_TOKEN", "codex_oauth": "CODEX_OAUTH_TOKEN",
                         "gemini_oauth": "GEMINI_OAUTH_TOKEN"}[prefix], "")
        blob_raw = store.vault_get(prefix)
        raw = blob_raw or val
        if raw:
            src = "vault" if blob_raw else "env"
            try:
                blob = json.loads(raw)
                if isinstance(blob, dict) and "access_token" in blob:
                    left = int(blob.get("expires_at", 0) - time.time())
                    note = (f"oauth, expires in {left // 3600}h{(left % 3600) // 60}m"
                            if left > 0 else "EXPIRED — re-import/re-login")
                    note += "; refreshable" if blob.get("refreshable") else "; re-import on expiry"
                else:
                    note = "plain token"
            except Exception:
                note = "plain token"
        rows.append({"provider": prefix, "source": src, "note": note})
    return rows
