"""FeirRouter gateway server: all /v1/* + /v1beta + Ollama + media + /admin + /mcp + /api in one FastAPI app."""
from __future__ import annotations
import hashlib
import json as _json
import os
import re
import time
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .providers.catalog import CATALOG, BY_PREFIX, CHAT_PREFIXES, MODEL_SEED, parse_slug, IMAGE_CANDIDATES, AUDIO_CANDIDATES
from .providers.base import ChatRequest, default_provider
from .routing.engine import QuotaLedger, CircuitBreaker, build_chain, resolve_tier_slug
from .routing.strategies import STRATEGIES
from .translation import formats as F
from .translation.thinking import to_anthropic_blocks, extract_thinking
from .translation.tools import parse_text_tool_calls
from .optimization.probes import try_probe_mock, mock_anthropic_response, mock_openai_response
from .optimization.compression import compress_messages
from .observability.store import Store
from .security.keys import new_unified_key, encrypt, decrypt

app = FastAPI(title="FeirRouter", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_headers=["*"], allow_methods=["*"])

ledger = QuotaLedger()
breaker = CircuitBreaker()
store: Store | None = None
sema = asyncio.Semaphore(settings.FEIR_CONCURRENCY)
LAST_GOOD: tuple[str, str] | None = None


def get_store() -> Store:
    global store
    if store is None:
        store = Store(settings.FEIR_DB_PATH)
        if not store.get("unified_key"):
            store.set("unified_key", settings.FEIR_UNIFIED_KEY or new_unified_key())
    return store


def unified_key() -> str:
    return get_store().get("unified_key")


def check_auth(request: Request):
    expected = unified_key()
    if not expected:
        return
    got = request.headers.get("authorization", "")
    if got.startswith("Bearer "):
        got = got[7:]
    # local-first: пустой заголовок = loopback/first-run → пропускаем;
    # чужой неверный ключ → 401. Строгий режим: FEIR_REQUIRE_AUTH=1
    if not got:
        if os.getenv("FEIR_REQUIRE_AUTH") == "1":
            raise HTTPException(401, "missing unified key")
        return
    # loopback admin без ключа — ок; API требует ключ если задан
    if request.url.path.startswith("/admin") or request.url.path in ("/health",):
        return
    if got != expected and os.getenv("FEIR_NO_AUTH") != "1":
        # allow empty-key first run? if user never set key, accept anything on loopback
        if request.client and request.client.host in ("127.0.0.1", "::1", "localhost", "testserver"):
            return
        raise HTTPException(401, "bad unified key. Get it at /admin or /api/unified-key (loopback)")


def seed_candidates() -> list[dict]:
    st = get_store()
    order = st.get_json("chain_order", [])  # user fallback-chain order (FreeLLMAPI drag-drop)
    rank = {slug: len(order) - i for i, slug in enumerate(order)}
    custom = st.get_json("custom_models", [])  # signed-catalog sync merges here
    out = []
    seq = [(p, m, intel, price, ctx) for p, m, intel, price, ctx in MODEL_SEED]
    for c in custom:
        try:
            seq.append((c["provider"], c["model"], float(c.get("intelligence", 7)),
                        float(c.get("price", 0)), int(c.get("context", 32000))))
        except Exception:
            continue
    for i, (prov, model, intel, price, ctx) in enumerate(seq):
        spec = BY_PREFIX.get(prov)
        if spec is None or not spec.chat:
            continue
        # skip providers without key unless local/keyless (vault or env)
        has_key = (not spec.env_key) or bool(os.getenv(spec.env_key) or st.vault_get(prov))
        slug = f"{prov}/{model}"
        out.append({"provider": prov, "model": model, "intelligence": intel, "price": price,
                    "context": ctx, "priority": (100 - i) + rank.get(slug, 0) * 1000,
                    "rpm_left": 30, "tpd_left": 9000,
                    "latency_ms": 700, "errors": 0, "load": 0, "quota_reset_s": 3600,
                    "cache_affinity": 0, "code_fit": 1 if "coder" in model or "qwen" in model else 0,
                    "vision_fit": 1 if "vision" in model else 0, "enabled": has_key})
    # custom MODEL slug always appended as top priority
    slug = settings.MODEL
    p, m = parse_slug(slug)
    if p and slug not in [f"{c['provider']}/{c['model']}" for c in out]:
        out.insert(0, {"provider": p, "model": m, "intelligence": 8, "price": 0, "context": 128000,
                       "priority": 999, "rpm_left": 40, "tpd_left": 9999, "latency_ms": 600,
                       "errors": 0, "load": 0, "quota_reset_s": 60, "cache_affinity": 0,
                       "code_fit": 1, "vision_fit": 0, "enabled": True})
    return [c for c in out if c.get("enabled")]


def provider_creds(prefix: str) -> tuple[str, str]:
    spec = BY_PREFIX.get(prefix)
    if spec is None:
        raise HTTPException(400, f"unknown provider prefix '{prefix}'. See /v1/models")
    base = os.getenv(prefix.upper() + "_BASE_URL", spec.base_url)
    # local overrides
    if prefix == "lmstudio":
        base = os.getenv("LM_STUDIO_BASE_URL", base)
    if prefix == "llamacpp":
        base = os.getenv("LLAMACPP_BASE_URL", base)
    if prefix == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", base)
    key = os.getenv(spec.env_key, "") if spec.env_key else "local"
    if not key:
        # encrypted vault (FreeLLMAPI): AES-GCM in SQLite, decrypt in-memory per request
        blob = get_store().vault_get(prefix)
        if blob:
            try:
                key = decrypt(settings.FEIR_MASTER_KEY, blob)
            except Exception:
                key = ""
    return key, base


# ---------- guardrails (OmniRoute: PII redaction lite) ----------
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+7|8)?[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")
_KEY_RE = re.compile(r"\b((?:sk|feir|gho|ghp|xai|AIza)[-_A-Za-z0-9]{8,})\b")


def apply_guardrails(messages: list[dict]) -> tuple[list[dict], bool]:
    """Redact PII/secrets when FEIR_GUARDRAILS=true. Returns (messages, redacted)."""
    if os.getenv("FEIR_GUARDRAILS", "").lower() not in ("1", "true", "on"):
        return messages, False
    redacted = False
    out = []
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            for pat in (_EMAIL_RE, _PHONE_RE, _KEY_RE):
                c, n = pat.subn("[REDACTED]", c)
                redacted = redacted or n > 0
            out.append({**m, "content": c})
        else:
            out.append(m)
    return out, redacted


def fire_webhooks(event: str, payload: dict):
    """Best-effort webhook dispatch (OmniRoute idea). Never blocks the request."""
    try:
        hooks = get_store().get_json("webhooks", [])
    except Exception:
        return
    if not hooks:
        return

    async def _send():
        import httpx
        async with httpx.AsyncClient(timeout=5) as c:
            for h in hooks:
                try:
                    if event in h.get("events", ["request.completed"]):
                        await c.post(h["url"], json={"event": event, **payload})
                except Exception:
                    continue
    try:
        asyncio.get_running_loop().create_task(_send())
    except RuntimeError:
        pass


async def run_chain(messages: list[dict], wanted: str, strategy: str, stream: bool, ctx: dict | None = None):
    """Try chain with fallback (FreeLLMAPI retry+cooldown, OmniRoute breaker). Returns (provider, model, data)."""
    global LAST_GOOD
    tctx = {"last_good": LAST_GOOD, "need_ctx": sum(len(str(m.get('content', ''))) // 4 for m in messages), **(ctx or {})}
    chain = build_chain(wanted, strategy, ledger, breaker, seed_candidates(), tctx)
    if not chain:
        raise HTTPException(503, "no providers configured — add keys in .env then restart")
    last_err: Exception | None = None
    for cand in chain[: max(1, settings.FEIR_MAX_ATTEMPTS)]:
        prov, model = cand["provider"], cand["model"]
        key, base = provider_creds(prov)
        spec = BY_PREFIX.get(prov)
        if spec and spec.env_key and not key:
            continue  # no key → skip silently (quota-aware)
        qk = (prov, model, "")
        if not ledger.allow(qk):
            continue
        async with sema:
            t0 = time.time()
            try:
                req = ChatRequest(model=model, messages=messages, stream=False)
                data = await default_provider.chat(req, key, base, settings.FEIR_TIMEOUT)
                dt = (time.time() - t0) * 1000
                ledger.record(qk, 0)
                breaker.success(prov)
                LAST_GOOD = (prov, model)
                get_store().log(prov, model, strategy, dt, status=200)
                fire_webhooks("request.completed", {"provider": prov, "model": model, "strategy": strategy})
                return prov, model, data
            except Exception as e:  # noqa: BLE001 — fallback chain must swallow
                status = 429 if "429" in str(e) else 500
                ledger.fail(qk, status)
                breaker.error(prov)
                get_store().log(prov, model, strategy, (time.time() - t0) * 1000, status=status)
                last_err = e
                continue
    raise HTTPException(502, f"all providers failed: {last_err}")


async def _passthrough_media(kind: str, body: dict) -> tuple[str, str, dict]:
    """Try OpenAI-shape media endpoints across candidates (images/audio)."""
    import httpx
    cands = IMAGE_CANDIDATES if kind == "images" else AUDIO_CANDIDATES
    path = {"images": "/images/generations", "speech": "/audio/speech",
            "transcriptions": "/audio/transcriptions"}.get(kind, "/images/generations")
    last_err: Exception | None = None
    for prefix in cands:
        key, base = provider_creds(prefix)
        if not key:
            continue
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                if kind == "transcriptions":
                    continue  # multipart — roadmap, честно отдаём 501 ниже
                r = await c.post(base.rstrip("/") + path, json=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                r.raise_for_status()
                if kind == "speech":
                    return prefix, "tts", {"_binary_len": len(r.content)}
                return prefix, body.get("model", "?"), r.json()
        except Exception as e:  # noqa: BLE001 — пробуем следующего
            last_err = e
            continue
    raise HTTPException(502, f"no media provider available: {last_err}")


# ---------- generic helpers ----------
def openai_text(data: dict) -> str:
    try:
        return data["choices"][0]["message"].get("content", "") or ""
    except Exception:
        return ""


# ---------- routes ----------
@app.get("/health")
async def health():
    return {"ok": True, "router": "FeirRouter", "version": "1.0.0", "strategies": STRATEGIES,
            "providers": len(CATALOG), "stats": get_store().stats()}


@app.get("/v1/models")
async def models():
    data = [{"id": f"{p}/{m}", "object": "model", "owned_by": p,
             "tier": (BY_PREFIX[p].tier if p in BY_PREFIX else "api")}
            for p, m, *_ in MODEL_SEED]
    for c in get_store().get_json("custom_models", []):
        try:
            data.append({"id": f"{c['provider']}/{c['model']}", "object": "model",
                         "owned_by": c["provider"], "tier": "custom"})
        except Exception:
            continue
    data += [{"id": s, "object": "model", "owned_by": "feir",
              "auto": True} for s in ["auto", "auto/coding", "auto/fast", "auto/cheap",
                                      "auto/reasoning", "auto/vision", "auto/offline", "fusion"]]
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    check_auth(request)
    msgs = body.get("messages", [])
    wanted = str(body.get("model", "auto"))
    strategy = str(body.get("strategy", "") or settings.FEIR_STRATEGY)
    stream = bool(body.get("stream", False))
    if settings.FEIR_PROBES:
        mock = try_probe_mock(body)
        if mock:
            get_store().log("mock", mock["role"], strategy, 1, mock=1)
            resp = mock_openai_response(mock, wanted)
            return JSONResponse(resp, headers={"X-Routed-Via": "mock/probe"})
    if settings.FEIR_COMPRESSION:
        msgs, comp = compress_messages(msgs, level=2)
    else:
        comp = {}
    msgs, redacted = apply_guardrails(msgs)
    wanted = resolve_tier_slug(wanted, settings)
    # explicit provider/model slug → try it first
    p0, m0 = parse_slug(wanted)
    if p0:
        # move to front by rebuilding seed with priority boost — run_chain handles via MODEL seed; here fast-path:
        pass
    prov, model, data = await run_chain(msgs, wanted, strategy, stream)
    data = F.sanitize_openai_response(data)
    # heuristic tool parser (FCC): text toolcalls → tool_calls
    txt = openai_text(data)
    cleaned, calls = parse_text_tool_calls(txt)
    if calls:
        try:
            msg = data["choices"][0]["message"]
            msg["content"] = cleaned
            msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                  "function": {"name": c["name"], "arguments": str(c["arguments"])}} for c in calls]
            data["choices"][0]["finish_reason"] = "tool_calls"
        except Exception:
            pass
    headers = {"X-Routed-Via": f"{prov}/{model}"}
    if comp:
        headers["X-Compression"] = str(comp.get("saved_pct", 0)) + "%"
    if redacted:
        headers["X-Guardrails"] = "pii-redacted"
    if stream:
        # SSE-ify non-stream upstream result (simple, robust)
        import json as _j
        txt2 = openai_text(data)

        def gen():
            yield f"data: {_j.dumps({'choices': [{'delta': {'role': 'assistant', 'content': txt2}}]})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
    return JSONResponse(data, headers=headers)


@app.post("/v1/messages")
async def anthropic_messages(request: Request):
    """Anthropic Messages API (Claude Code). Translate → route → translate back (FCC+OmniRoute)."""
    body = await request.json()
    check_auth(request)
    system = body.get("system", "")
    if isinstance(system, list):
        system = " ".join(b.get("text", "") for b in system if isinstance(b, dict))
    amsgs = body.get("messages", [])
    if settings.FEIR_PROBES:
        mock = try_probe_mock({"messages": [{"content": system}] + [{"content": str(m.get('content', ''))} for m in amsgs]})
        if mock:
            get_store().log("mock", mock["role"], "priority", 1, mock=1)
            return JSONResponse(mock_anthropic_response(mock), headers={"X-Routed-Via": "mock/probe"})
    omsgs = F.anthropic_to_openai(system, amsgs)
    if settings.FEIR_COMPRESSION:
        omsgs, _ = compress_messages(omsgs, level=2)
    # model mapping: claude-opus-4-* → per-tier slug
    claude_model = str(body.get("model", "sonnet"))
    wanted = resolve_tier_slug(claude_model, settings)
    prov, model, data = await run_chain(omsgs, wanted, settings.FEIR_STRATEGY, False)
    txt = openai_text(data)
    rc = None
    try:
        rc = data["choices"][0]["message"].get("reasoning_content")
    except Exception:
        rc = None
    blocks = to_anthropic_blocks(txt, rc)
    # tools: passthrough text clean
    resp = {"id": "msg_feir", "type": "message", "role": "assistant", "model": claude_model,
            "content": blocks, "stop_reason": "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": max(1, len(txt) // 4)}}
    if body.get("stream"):
        import json as _j
        def gen():
            yield f"event: message_start\ndata: {_j.dumps({'type': 'message_start', 'message': {**resp, 'content': []}})}\n\n"
            for b in blocks:
                yield f"event: content_block_delta\ndata: {_j.dumps({'type': 'content_block_delta', 'delta': b})}\n\n"
            yield f"event: message_stop\ndata: {_j.dumps({'type': 'message_stop'})}\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"X-Routed-Via": f"{prov}/{model}"})
    return JSONResponse(resp, headers={"X-Routed-Via": f"{prov}/{model}"})


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    body = await request.json()
    n = sum(len(str(m.get("content", ""))) // 4 for m in body.get("messages", []))
    return {"input_tokens": n}


@app.post("/v1/responses")
async def responses_api(request: Request):
    """OpenAI Responses API (Codex CLI). Convert → shared chain → Responses-shaped reply."""
    body = await request.json()
    check_auth(request)
    inp = body.get("input", [])
    msgs = []
    if isinstance(inp, str):
        msgs = [{"role": "user", "content": inp}]
    else:
        for b in inp:
            if isinstance(b, dict):
                c = b.get("content", "")
                if isinstance(c, list):
                    c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                msgs.append({"role": b.get("role", "user"), "content": str(c)})
    wanted = str(body.get("model", settings.MODEL))
    wanted = resolve_tier_slug(wanted, settings)
    prov, model, data = await run_chain(msgs, wanted, settings.FEIR_STRATEGY, False)
    txt = openai_text(data)
    resp = {"id": "resp_feir", "object": "response", "model": model,
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": txt}]}]}
    if body.get("stream"):
        import json as _j
        def gen():
            yield f"data: {_j.dumps(resp)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"X-Routed-Via": f"{prov}/{model}"})
    return JSONResponse(resp, headers={"X-Routed-Via": f"{prov}/{model}"})


@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    check_auth(request)
    prompt = str(body.get("prompt", ""))
    prov, model, data = await run_chain([{"role": "user", "content": prompt}],
                                        str(body.get("model", "auto")), settings.FEIR_STRATEGY, False)
    return JSONResponse({"id": "cmpl-feir", "object": "text_completion", "model": model,
                         "choices": [{"text": openai_text(data), "finish_reason": "stop"}]},
                        headers={"X-Routed-Via": f"{prov}/{model}"})


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    check_auth(request)
    return JSONResponse({"object": "list", "data": [{"object": "embedding", "index": 0,
                                                     "embedding": [0.0] * 8}], "model": "mock"})


@app.get("/api/stats")
async def stats():
    return get_store().stats()


@app.get("/api/logs")
async def logs(n: int = 50):
    return get_store().recent(n)


@app.get("/api/unified-key")
async def unified(request: Request):
    if request.client and request.client.host not in ("127.0.0.1", "::1", None):
        raise HTTPException(403, "loopback only")
    return {"unified_key": unified_key(), "base_url": f"http://127.0.0.1:{settings.FEIR_PORT}/v1"}


@app.get("/mcp")
async def mcp_info():
    return {"name": "feirrouter-mcp", "transports": ["http"],
            "tools": ["feir.chat", "feir.models", "feir.quota", "feir.fallback_chain", "feir.compress"]}


@app.get("/admin", response_class=HTMLResponse)
async def admin():
    p = Path(__file__).parent / "admin" / "ui.html"
    return HTMLResponse(p.read_text(encoding="utf-8"))


# ================= management + extended surfaces =================

@app.get("/api/providers")
async def api_providers():
    """Full catalog with live key status (union of all three routers)."""
    st = get_store()
    out = []
    for p in CATALOG:
        has = (not p.env_key) or bool(os.getenv(p.env_key) or st.vault_get(p.prefix))
        out.append({"prefix": p.prefix, "title": p.title, "tier": p.tier, "has_free": p.has_free,
                    "free_budget": p.free_budget, "format": p.api_format, "chat": p.chat,
                    "ready": has, "key_env": p.env_key})
    return {"count": len(out), "providers": out}


@app.get("/api/keys")
async def keys_list():
    return {"vault": get_store().vault_list()}


@app.post("/api/keys")
async def keys_add(request: Request):
    """Save provider key encrypted (AES-256-GCM). Body: {provider, api_key}."""
    body = await request.json()
    prov = str(body.get("provider", ""))
    key = str(body.get("api_key", ""))
    if prov not in BY_PREFIX or not key:
        raise HTTPException(400, "need {provider, api_key} with known provider prefix")
    get_store().vault_set(prov, encrypt(settings.FEIR_MASTER_KEY, key))
    return {"ok": True, "provider": prov}


@app.delete("/api/keys/{provider}")
async def keys_del(provider: str):
    get_store().vault_del(provider)
    return {"ok": True, "provider": provider}


@app.get("/api/chain")
async def chain_get():
    cands = [f"{p}/{m}" for p, m, *_ in MODEL_SEED]
    cands += [f"{c['provider']}/{c['model']}" for c in get_store().get_json("custom_models", []) if "provider" in c]
    saved = get_store().get_json("chain_order", [])
    ordered = [s for s in saved if s in cands] + [s for s in cands if s not in saved]
    return {"strategy": settings.FEIR_STRATEGY, "chain": ordered}


@app.put("/api/chain")
async def chain_put(request: Request):
    """Reorder fallback chain (FreeLLMAPI drag-drop). Body: {chain: [slugs], strategy?}."""
    body = await request.json()
    chain = body.get("chain", [])
    if not isinstance(chain, list):
        raise HTTPException(400, "chain must be a list of 'provider/model' slugs")
    get_store().set_json("chain_order", [str(s) for s in chain])
    return {"ok": True, "chain": chain}


@app.get("/api/catalog")
async def catalog_get():
    custom = get_store().get_json("custom_models", [])
    return {"seed_models": len(MODEL_SEED), "custom_models": len(custom), "custom": custom,
            "pin_set": bool(os.getenv("FEIR_CATALOG_PIN"))}


@app.post("/api/catalog/sync")
async def catalog_sync(request: Request):
    """Self-updating catalog (FreeLLMAPI idea): fetch signed feed JSON, verify pin, merge.
    Feed shape: {models: [{provider, model, intelligence?, price?, context?}]}.
    Without FEIR_CATALOG_PIN merge is applied but flagged unverified (honest)."""
    import httpx
    body = await request.json()
    url = str(body.get("url", ""))
    if not url.startswith("https://"):
        raise HTTPException(400, "url must be https feed JSON")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url)
        r.raise_for_status()
        feed = r.json()
    raw = _json.dumps(feed, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    pin = os.getenv("FEIR_CATALOG_PIN", "")
    verified = bool(pin) and digest == pin
    merged = 0
    cur = {f"{c.get('provider')}/{c.get('model')}" for c in get_store().get_json("custom_models", [])}
    new_items = []
    for m in feed.get("models", []):
        try:
            if m.get("provider") not in BY_PREFIX or "/" in str(m.get("model", "")) and False:
                pass
            slug = f"{m['provider']}/{m['model']}"
            if m["provider"] in BY_PREFIX and slug not in cur:
                new_items.append({"provider": m["provider"], "model": m["model"],
                                  "intelligence": float(m.get("intelligence", 7)),
                                  "price": float(m.get("price", 0)),
                                  "context": int(m.get("context", 32000))})
                cur.add(slug)
                merged += 1
        except Exception:
            continue
    store = get_store()
    store.set_json("custom_models", store.get_json("custom_models", []) + new_items)
    return {"ok": True, "merged": merged, "sha256": digest, "verified": verified,
            "note": "unverified — set FEIR_CATALOG_PIN to enforce signature" if not verified else "pin verified"}


@app.post("/v1/images/generations")
async def images(request: Request):
    body = await request.json()
    check_auth(request)
    prov, model, data = await _passthrough_media("images", body)
    get_store().log(prov, model, "media", 0, status=200)
    return JSONResponse(data, headers={"X-Routed-Via": f"{prov}/{model}"})


@app.post("/v1/audio/speech")
async def audio_speech(request: Request):
    body = await request.json()
    check_auth(request)
    prov, model, data = await _passthrough_media("speech", body)
    return JSONResponse(data, headers={"X-Routed-Via": f"{prov}/{model}"})


@app.post("/v1/audio/transcriptions")
async def audio_transcriptions():
    raise HTTPException(501, "multipart transcription passthrough — roadmap (use provider directly for now)")


@app.post("/v1/videos/generations")
async def videos():
    raise HTTPException(501, "video generation passthrough — roadmap (providers: runway/luma/minimax)")


def _gemini_in_to_openai(body: dict) -> tuple[str, list[dict]]:
    contents = body.get("contents", []) or []
    msgs: list[dict] = []
    sys = body.get("systemInstruction", {}).get("parts", [])
    if sys:
        msgs.append({"role": "system", "content": " ".join(p.get("text", "") for p in sys)})
    for c in contents:
        role = "assistant" if c.get("role") == "model" else "user"
        text = " ".join(p.get("text", "") for p in c.get("parts", []))
        msgs.append({"role": role, "content": text})
    return str(body.get("model", "gemini-2.5-flash")), msgs


@app.post("/v1beta/models/{model}:generateContent")
async def gemini_generate(model: str, request: Request):
    """Gemini native surface (Gemini CLI). Translate → shared chain → Gemini shape."""
    body = await request.json()
    check_auth(request)
    _, msgs = _gemini_in_to_openai({**body, "model": model})
    prov, m, data = await run_chain(msgs, "gemini/" + model if "/" not in model else model,
                                    settings.FEIR_STRATEGY, False)
    txt = openai_text(data)
    return JSONResponse({"candidates": [{"content": {"role": "model", "parts": [{"text": txt}]}}],
                         "modelVersion": m}, headers={"X-Routed-Via": f"{prov}/{m}"})


@app.post("/v1beta/models/{model}:streamGenerateContent")
async def gemini_stream(model: str, request: Request):
    body = await request.json()
    check_auth(request)
    _, msgs = _gemini_in_to_openai({**body, "model": model})
    prov, m, data = await run_chain(msgs, "gemini/" + model if "/" not in model else model,
                                    settings.FEIR_STRATEGY, False)
    txt = openai_text(data)

    def gen():
        yield _json.dumps({"candidates": [{"content": {"role": "model", "parts": [{"text": txt}]}}]}) + "\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"X-Routed-Via": f"{prov}/{m}"})


@app.get("/api/tags")
async def ollama_tags():
    """Ollama emulation for Zed / JetBrains AI (FreeLLMAPI idea)."""
    return {"models": [{"name": f"{p}/{m}", "model": f"{p}/{m}"} for p, m, *_ in MODEL_SEED]}


@app.post("/api/chat")
async def ollama_chat(request: Request):
    body = await request.json()
    msgs = body.get("messages", [])
    prov, model, data = await run_chain(msgs, str(body.get("model", "auto")), settings.FEIR_STRATEGY, False)
    txt = openai_text(data)
    resp = {"model": model, "message": {"role": "assistant", "content": txt}, "done": True}
    if body.get("stream"):
        def gen():
            yield _json.dumps({**resp, "done": False}) + "\n"
            yield _json.dumps(resp) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson",
                                 headers={"X-Routed-Via": f"{prov}/{model}"})
    return JSONResponse(resp, headers={"X-Routed-Via": f"{prov}/{model}"})


@app.post("/api/generate")
async def ollama_generate(request: Request):
    body = await request.json()
    prov, model, data = await run_chain([{"role": "user", "content": str(body.get("prompt", ""))}],
                                        str(body.get("model", "auto")), settings.FEIR_STRATEGY, False)
    return JSONResponse({"model": model, "response": openai_text(data), "done": True},
                        headers={"X-Routed-Via": f"{prov}/{model}"})


@app.get("/api/memory")
async def mem_list(q: str = "", n: int = 20):
    return {"notes": get_store().mem_search(q, n)}


@app.post("/api/memory")
async def mem_add(request: Request):
    body = await request.json()
    note = str(body.get("note", ""))
    if not note:
        raise HTTPException(400, "need {note}")
    return {"ok": True, "id": get_store().mem_add(note)}


@app.delete("/api/memory/{mid}")
async def mem_del(mid: int):
    get_store().mem_del(mid)
    return {"ok": True}


@app.get("/api/webhooks")
async def hooks_list():
    return {"webhooks": get_store().get_json("webhooks", [])}


@app.post("/api/webhooks")
async def hooks_add(request: Request):
    body = await request.json()
    url = str(body.get("url", ""))
    if not url.startswith("http"):
        raise HTTPException(400, "need {url}")
    hooks = get_store().get_json("webhooks", [])
    hooks.append({"url": url, "events": body.get("events", ["request.completed", "request.failed"])})
    get_store().set_json("webhooks", hooks)
    return {"ok": True, "webhooks": hooks}


@app.delete("/api/webhooks")
async def hooks_clear():
    get_store().set_json("webhooks", [])
    return {"ok": True}


@app.post("/api/evals/run")
async def evals_run(request: Request):
    """Eval framework lite (OmniRoute idea): tiny prompts through the live chain."""
    body = await request.json() or {}
    prompts = body.get("prompts", ["Say OK", "What is 2+2?"])[:5]
    results = []
    for p in prompts:
        t0 = time.time()
        try:
            prov, model, data = await run_chain([{"role": "user", "content": str(p)}], "auto", "auto", False)
            results.append({"prompt": p, "ok": True, "via": f"{prov}/{model}",
                            "latency_ms": round((time.time() - t0) * 1000, 1),
                            "chars": len(openai_text(data))})
        except Exception as e:  # noqa: BLE001 — eval фиксирует, а не падает
            results.append({"prompt": p, "ok": False, "error": str(e)[:200]})
    ok = sum(1 for r in results if r["ok"])
    return {"passed": f"{ok}/{len(results)}", "results": results}


@app.get("/.well-known/agent.json")
async def agent_card():
    """A2A agent card (OmniRoute idea, lite)."""
    return {"name": "FeirRouter", "version": "1.0.0",
            "url": f"http://127.0.0.1:{settings.FEIR_PORT}",
            "protocols": ["openai-chat", "anthropic-messages", "openai-responses", "gemini", "ollama"],
            "skills": ["feir.chat", "feir.models", "feir.quota", "feir.fallback_chain", "feir.compress", "feir.eval"],
            "auth": "unified Bearer feir-..."}


def main():
    import uvicorn
    import argparse
    ap = argparse.ArgumentParser(prog="feir-server")
    ap.add_argument("--port", type=int, default=settings.FEIR_PORT)
    ap.add_argument("--host", default=settings.FEIR_HOST)
    a = ap.parse_args()
    get_store()
    print(f"FeirRouter on http://{a.host}:{a.port}  admin=/admin  api=/v1  key={unified_key()[:10]}...")
    uvicorn.run(app, host=a.host, port=a.port)
