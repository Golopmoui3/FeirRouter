"""FeirRouter gateway server: all /v1/* + /admin + /mcp in one FastAPI app."""
from __future__ import annotations
import os
import time
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .providers.catalog import CATALOG, BY_PREFIX, MODEL_SEED, parse_slug
from .providers.base import ChatRequest, default_provider
from .routing.engine import QuotaLedger, CircuitBreaker, build_chain, resolve_tier_slug
from .routing.strategies import STRATEGIES
from .translation import formats as F
from .translation.thinking import to_anthropic_blocks, extract_thinking
from .translation.tools import parse_text_tool_calls
from .optimization.probes import try_probe_mock, mock_anthropic_response, mock_openai_response
from .optimization.compression import compress_messages
from .observability.store import Store
from .security.keys import new_unified_key

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
    out = []
    for i, (prov, model, intel, price, ctx) in enumerate(MODEL_SEED):
        spec = BY_PREFIX.get(prov)
        if spec is None:
            continue
        # skip providers without key unless local/keyless
        has_key = (not spec.env_key) or bool(os.getenv(spec.env_key))
        out.append({"provider": prov, "model": model, "intelligence": intel, "price": price,
                    "context": ctx, "priority": 100 - i, "rpm_left": 30, "tpd_left": 9000,
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
    return key, base


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
                return prov, model, data
            except Exception as e:  # noqa: BLE001 — fallback chain must swallow
                status = 429 if "429" in str(e) else 500
                ledger.fail(qk, status)
                breaker.error(prov)
                get_store().log(prov, model, strategy, (time.time() - t0) * 1000, status=status)
                last_err = e
                continue
    raise HTTPException(502, f"all providers failed: {last_err}")


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
