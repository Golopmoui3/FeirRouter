"""CLI: setup-* generators + launchers + doctor (FreeLLMAPI + FCC idea, 10+ agents)."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


BASE = "http://127.0.0.1:8081/v1"


def unified_key() -> str:
    try:
        from .config import settings
        from .observability.store import Store
        s = Store(settings.FEIR_DB_PATH)
        return s.get("unified_key") or os.getenv("FEIR_UNIFIED_KEY", "")
    except Exception:
        return os.getenv("FEIR_UNIFIED_KEY", "")


def write_config(path: Path, content: str, backup: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and backup:
        path.with_suffix(path.suffix + ".feir.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def cmd_setup_claude(a):
    key = a.api_key or unified_key()
    url = a.url or BASE
    # env-file for claude launcher
    print(f"Claude Code → base={url} model=sonnet")
    print(f"  export ANTHROPIC_BASE_URL={url}")
    print(f"  export ANTHROPIC_AUTH_TOKEN={key or 'feir-...'}")
    print("  Then run: python -m feirrouter launch -- claude")


def cmd_setup_codex(a):
    key = a.api_key or unified_key()
    url = a.url or BASE
    cfg = Path.home() / ".codex" / "config.toml"
    snippet = f'\n[model_providers.feir]\nbase_url = "{url}"\nenv_key = "FEIR_CODEX_KEY"\nwire_api = "responses"\n'
    print(f"Add to {cfg}:\n{snippet}\nFEIR_CODEX_KEY={key or 'feir-...'}")
    print("Then: python -m feirrouter launch-codex")


def cmd_setup_opencode(a):
    key = a.api_key or unified_key()
    url = a.url or BASE
    cfg = {"provider": {"feir": {"npm": "@ai-sdk/openai-compatible",
                                 "options": {"baseURL": url, "apiKey": key or "feir-..."}}}}
    print("Merge into opencode.json:")
    print(json.dumps(cfg, indent=2, ensure_ascii=False))


def cmd_setup_generic(name: str, a):
    print(f"[{name}] base_url={a.url or BASE} api_key={(a.api_key or unified_key() or 'feir-...')[:10]}... model=auto")


def _read_env_file(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _upsert_env(lines: list[str], key: str, val: str) -> list[str]:
    out, done = [], False
    for ln in lines:
        if ln.startswith(key + "=") and not done:
            out.append(f"{key}={val}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{key}={val}")
    return out


def cmd_setup_wizard(a):
    """Интерактивный setup: ключи → .env, без простыни вручную (ответ на критику README)."""
    import getpass
    from .providers.catalog import CATALOG
    from .routing.strategies import STRATEGIES
    env_path = Path.cwd() / ".env"
    if not env_path.exists() and Path(".env.example").exists():
        env_path.write_text(Path(".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    lines = _read_env_file(env_path)
    print("== FeirRouter setup ==  (Enter = пропустить)")
    print(f"1) Стратегии: {', '.join(STRATEGIES)}")
    s = input("   strategy [auto]: ").strip() or "auto"
    if s in STRATEGIES:
        lines = _upsert_env(lines, "FEIR_STRATEGY", s)
    print("2) Базовая модель (fallback + per-tier через MODEL_OPUS/SONNET/HAIKU/FABLE)")
    m = input("   MODEL [nvidia_nim/stepfun-ai/step-3.5-flash]: ").strip()
    if m:
        lines = _upsert_env(lines, "MODEL", m)
    print("3) Ключи free-провайдеров (вставляй, скрытый ввод):")
    added = []
    for p in CATALOG:
        if not (p.has_free and p.chat and p.env_key) or os.getenv(p.env_key):
            continue
        v = getpass.getpass(f"   {p.title} [{p.env_key}] (free: {p.free_budget}): ").strip()
        if v:
            lines = _upsert_env(lines, p.env_key, v)
            added.append(p.prefix)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved {env_path}: strategy + MODEL + {len(added)} keys {added}")
    if input("4) Проверить connectivity (GET <base>/models)? [y/N]: ").strip().lower() == "y":
        import httpx
        for p in CATALOG:
            if p.prefix not in added:
                continue
            try:
                r = httpx.get(p.base_url.rstrip("/") + "/models",
                              headers={"Authorization": f"Bearer {os.getenv(p.env_key, '')}"}, timeout=10)
                print(f"   {p.prefix}: HTTP {r.status_code}")
            except Exception as e:
                print(f"   {p.prefix}: FAIL {str(e)[:100]}")
    print("Готово. Старт: python -m feirrouter serve. Проверка: python -m feirrouter doctor")


def cmd_benchmark(a):
    """Замер latency каждого слоя пайплайна (ответ на критику 'лотерея')."""
    import timeit
    from .optimization.probes import try_probe_mock
    from .optimization.compression import compress_messages
    from .translation import formats as F
    from .translation.thinking import to_anthropic_blocks
    from .translation.tools import parse_text_tool_calls
    from .routing.strategies import order_candidates
    from .providers.catalog import MODEL_SEED
    big = "line %d " % 1 + "x" * 200
    msgs = [{"role": "user", "content": "\n".join(f"{big} {i}" for i in range(600))}]
    cands = [{"provider": f"p{i}", "model": f"m{i}", "priority": i, "intelligence": 7,
              "price": 0.1 * (i % 5), "penalty": 0, "open": True, "load": i, "latency_ms": 500,
              "errors": 0, "rpm_left": 30, "tpd_left": 9000, "quota_reset_s": 3600,
              "cache_affinity": 0, "context": 128000} for i in range(60)]
    think_txt = "<think>plan a</think>answer b" * 20
    tool_txt = "do x <toolcall>{\"name\": \"read\", \"arguments\": {\"f\": \"a\"}}</toolcall>"
    oai = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello world"}]
    cases = {
        "probes.try_probe_mock": lambda: try_probe_mock({"messages": msgs[:1]}),
        "compression.L2 (120KB tool output)": lambda: compress_messages(msgs, level=2),
        "routing.auto-order (60 cands)": lambda: order_candidates("auto", cands, {}),
        "translation.oai->anthropic": lambda: F.openai_to_anthropic(oai),
        "thinking.extract": lambda: to_anthropic_blocks(think_txt),
        "tools.parse": lambda: parse_text_tool_calls(tool_txt),
    }
    n = a.iters
    rows = []
    print(f"== FeirRouter benchmark ({n} iters) ==")
    for name, fn in cases.items():
        fn()  # warmup
        dt = timeit.timeit(fn, number=n) / n * 1000
        rows.append((name, dt))
        print(f"  {name:38} {dt:8.3f} ms/req")
    total = sum(d for _, d in rows)
    print(f"  {'TOTAL pipeline overhead (in-proc)':38} {total:8.3f} ms/req")
    if a.write:
        doc = ["# Benchmarks — FeirRouter pipeline overhead (in-process, без сети)",
               "", f"Measured: `{n}` iters. Машина: смотри ниже. Сеть НЕ включена — это накладные расходы самого роутера.",
               "", "| Stage | ms/req |", "|---|---|"]
        doc += [f"| {k} | {v:.3f} |" for k, v in rows]
        doc += [f"| **TOTAL** | **{total:.3f}** |", "",
                "Вывод: весь in-process пайплайн — доли миллисекунды; доминирует сеть до провайдера (сотни мс).",
                "Перезамер: `python -m feirrouter benchmark --iters 200 --write`"]
        Path("docs/BENCHMARKS.md").write_text("\n".join(doc) + "\n", encoding="utf-8")
        print("wrote docs/BENCHMARKS.md")


def cmd_oauth(a):
    import json as _json
    from .config import settings
    from .observability.store import Store
    from . import oauth as O
    from .security.keys import encrypt
    store = Store(settings.FEIR_DB_PATH)
    if a.oauth_cmd == "status":
        for r in O.oauth_status(store):
            print(f" {r['provider']:15} [{r['source']:5}] {r['note']}")
        return
    if a.oauth_cmd == "import":
        res = O.import_cli_creds()
        for prov, val in res.items():
            if isinstance(val, dict):
                store.vault_set(prov, encrypt(settings.FEIR_MASTER_KEY, _json.dumps(val)))
                print(f" OK {prov}: imported to encrypted vault")
            else:
                print(f" -- {prov}: {val}")
        return
    if a.oauth_cmd == "login" and a.provider == "google":
        cid = a.client_id or input("Google OAuth client_id (Desktop app, Cloud Console): ").strip()
        if not cid:
            print("нужен client_id — см. docs/OAUTH.md")
            return
        blob = O.login_google(cid, a.client_secret, a.no_browser)
        store.vault_set("gemini_oauth", encrypt(settings.FEIR_MASTER_KEY, _json.dumps(blob)))
        print("OK gemini_oauth: token saved to encrypted vault")
        return


def cmd_launch(a):
    from .config import settings
    env = dict(os.environ)
    key = unified_key()
    env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{settings.FEIR_PORT}/v1"
    env["ANTHROPIC_AUTH_TOKEN"] = key or "feir-no-auth"
    env["OPENAI_BASE_URL"] = f"http://127.0.0.1:{settings.FEIR_PORT}/v1"
    env["OPENAI_API_KEY"] = key or "feir-no-auth"
    env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = "190000"
    child = a.child or ["claude"]
    print("launch:", " ".join(child))
    sys.exit(subprocess.call(child, env=env))


def cmd_doctor(a):
    import socket
    from .providers.catalog import CATALOG
    print("FeirRouter doctor")
    n = 0
    seen_keys: dict[str, list[str]] = {}
    for p in CATALOG:
        val = os.getenv(p.env_key, "") if p.env_key else ""
        has = (not p.env_key) or bool(val) or _vault_has(p.prefix)
        if val:
            seen_keys.setdefault(val, []).append(p.env_key)
        flag = "OK " if has else "-- "
        if has:
            n += 1
        print(f" {flag} {p.prefix:15} {p.title} [{p.tier}]{' free' if p.has_free else ''}")
    print(f"\n{n}/{len(CATALOG)} providers ready. Admin: http://127.0.0.1:8081/admin")
    # key reuse: один и тот же ключ под разными именами = общий лимит, предупредим
    dupes = {v: ks for v, ks in seen_keys.items() if len(ks) > 1}
    for v, ks in dupes.items():
        print(f" WARN key reuse: {', '.join(ks)} share one key (shared upstream quota!)")
    # чужие шлюзы на стандартных портах: два роутера с одним ключом = двойной расход лимита
    for port, who in [(3001, "FreeLLMAPI?"), (20128, "OmniRoute?"), (8082, "free-claude-code?"),
                      (3456, "Claude Code Router?")]:
        s = socket.socket()
        s.settimeout(0.3)
        try:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                print(f" WARN port {port} busy — {who} may be running. Two gateways + one key = 2x quota burn.")
        finally:
            s.close()


def _vault_has(prefix: str) -> bool:
    try:
        from .config import settings
        from .observability.store import Store
        return bool(Store(settings.FEIR_DB_PATH).vault_get(prefix))
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(prog="feirrouter")
    sub = ap.add_subparsers(dest="cmd")
    for name in ["setup-claude", "setup-codex", "setup-opencode", "setup-aider", "setup-cursor",
                 "setup-cline", "setup-gemini", "setup-qwen", "setup-dsh", "setup-pi", "setup-aider2"]:
        s = sub.add_parser(name)
        s.add_argument("--url", default="")
        s.add_argument("--api-key", default="")
    s = sub.add_parser("launch")
    s.add_argument("child", nargs="*")
    s = sub.add_parser("launch-codex")
    s.add_argument("child", nargs="*")
    sub.add_parser("doctor")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8081)
    sub.add_parser("setup")
    s = sub.add_parser("benchmark")
    s.add_argument("--iters", type=int, default=200)
    s.add_argument("--write", action="store_true")
    s = sub.add_parser("oauth")
    o = s.add_subparsers(dest="oauth_cmd")
    s_login = o.add_parser("login", help="OAuth login (google)")
    s_login.add_argument("provider", choices=["google"])
    s_login.add_argument("--client-id", default="")
    s_login.add_argument("--client-secret", default="")
    s_login.add_argument("--no-browser", action="store_true")
    o.add_parser("import", help="import tokens from official CLIs (claude/codex/gemini)")
    o.add_parser("status", help="oauth token status")
    a, rest = ap.parse_known_args()
    # `python -m feirrouter --port 8081` → serve
    if a.cmd is None:
        import sys as _s
        _s.argv = ["feir-server", *rest]
        from .server import main as serve
        return serve()
    if a.cmd == "setup-claude":
        return cmd_setup_claude(a)
    if a.cmd == "setup-codex":
        return cmd_setup_codex(a)
    if a.cmd == "setup-opencode":
        return cmd_setup_opencode(a)
    if a.cmd.startswith("setup-"):
        return cmd_setup_generic(a.cmd, a)
    if a.cmd in ("launch", "launch-codex"):
        if a.cmd == "launch-codex" and not a.child:
            a.child = ["codex"]
        return cmd_launch(a)
    if a.cmd == "doctor":
        return cmd_doctor(a)
    if a.cmd == "setup":
        return cmd_setup_wizard(a)
    if a.cmd == "benchmark":
        return cmd_benchmark(a)
    if a.cmd == "oauth":
        return cmd_oauth(a)
    if a.cmd == "serve":
        import sys as _s
        _s.argv = ["feir-server", "--port", str(a.port)]
        from .server import main as serve
        return serve()


if __name__ == "__main__":
    main()
