"""SQLite store: request logs, usage, quota snapshots (OmniRoute observability lite)
+ encrypted provider-key vault (FreeLLMAPI) + fallback chain + memory + webhooks + custom catalog.
"""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS requests(
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, provider TEXT, model TEXT,
 strategy TEXT, latency_ms REAL, in_tok INTEGER, out_tok INTEGER,
 cost REAL, status INTEGER, mock INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS provider_keys(provider TEXT PRIMARY KEY, blob TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS memory(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, note TEXT);
"""


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    # ---- requests ----
    def log(self, provider: str, model: str, strategy: str, latency_ms: float,
            in_tok: int = 0, out_tok: int = 0, cost: float = 0.0, status: int = 200, mock: int = 0):
        self.db.execute(
            "INSERT INTO requests(ts,provider,model,strategy,latency_ms,in_tok,out_tok,cost,status,mock) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (time.time(), provider, model, strategy, latency_ms, in_tok, out_tok, cost, status, mock))
        self.db.commit()

    def recent(self, n: int = 100) -> list[dict]:
        cur = self.db.execute("SELECT ts,provider,model,strategy,latency_ms,in_tok,out_tok,cost,status,mock FROM requests ORDER BY id DESC LIMIT ?", (n,))
        cols = ["ts", "provider", "model", "strategy", "latency_ms", "in_tok", "out_tok", "cost", "status", "mock"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def stats(self) -> dict:
        cur = self.db.execute("SELECT COUNT(*), COALESCE(SUM(in_tok+out_tok),0), COALESCE(SUM(cost),0) FROM requests")
        n, toks, cost = cur.fetchone()
        return {"requests": n, "tokens": toks, "cost": round(cost or 0, 4)}

    # ---- kv ----
    def get(self, k: str, default: str = "") -> str:
        cur = self.db.execute("SELECT v FROM kv WHERE k=?", (k,))
        r = cur.fetchone()
        return r[0] if r else default

    def set(self, k: str, v: str):
        self.db.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
        self.db.commit()

    def get_json(self, k: str, default):
        raw = self.get(k, "")
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    def set_json(self, k: str, v):
        self.set(k, json.dumps(v, ensure_ascii=False))

    # ---- encrypted key vault ----
    def vault_set(self, provider: str, blob: str):
        self.db.execute("INSERT INTO provider_keys(provider,blob,updated) VALUES(?,?,?) "
                        "ON CONFLICT(provider) DO UPDATE SET blob=excluded.blob, updated=excluded.updated",
                        (provider, blob, time.time()))
        self.db.commit()

    def vault_get(self, provider: str) -> str:
        cur = self.db.execute("SELECT blob FROM provider_keys WHERE provider=?", (provider,))
        r = cur.fetchone()
        return r[0] if r else ""

    def vault_del(self, provider: str):
        self.db.execute("DELETE FROM provider_keys WHERE provider=?", (provider,))
        self.db.commit()

    def vault_list(self) -> list[dict]:
        cur = self.db.execute("SELECT provider, updated FROM provider_keys ORDER BY provider")
        return [{"provider": p, "updated": u, "key": "••••••••"} for p, u in cur.fetchall()]

    # ---- memory (FTS-lite via LIKE) ----
    def mem_add(self, note: str) -> int:
        cur = self.db.execute("INSERT INTO memory(ts,note) VALUES(?,?)", (time.time(), note))
        self.db.commit()
        return cur.lastrowid

    def mem_search(self, q: str = "", n: int = 20) -> list[dict]:
        if q:
            cur = self.db.execute("SELECT id,ts,note FROM memory WHERE note LIKE ? ORDER BY id DESC LIMIT ?",
                                  (f"%{q}%", n))
        else:
            cur = self.db.execute("SELECT id,ts,note FROM memory ORDER BY id DESC LIMIT ?", (n,))
        return [{"id": i, "ts": t, "note": s} for i, t, s in cur.fetchall()]

    def mem_del(self, mid: int):
        self.db.execute("DELETE FROM memory WHERE id=?", (mid,))
        self.db.commit()
