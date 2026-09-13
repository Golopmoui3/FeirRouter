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
    from .providers.catalog import CATALOG
    print("FeirRouter doctor")
    n = 0
    for p in CATALOG:
        has = (not p.env_key) or bool(os.getenv(p.env_key))
        flag = "OK " if has else "-- "
        if has:
            n += 1
        print(f" {flag} {p.prefix:15} {p.title} [{p.tier}]{' free' if p.has_free else ''}")
    print(f"\n{n}/{len(CATALOG)} providers ready. Admin: http://127.0.0.1:8081/admin")


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
    if a.cmd == "serve":
        import sys as _s
        _s.argv = ["feir-server", "--port", str(a.port)]
        from .server import main as serve
        return serve()


if __name__ == "__main__":
    main()
