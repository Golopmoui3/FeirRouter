"""SQLite store: request logs, usage, quota snapshots (OmniRoute observability lite)."""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS requests(
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, provider TEXT, model TEXT,
 strategy TEXT, latency_ms REAL, in_tok INTEGER, out_tok INTEGER,
 cost REAL, status INTEGER, mock INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)

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

    def get(self, k: str, default: str = "") -> str:
        cur = self.db.execute("SELECT v FROM kv WHERE k=?", (k,))
        r = cur.fetchone()
        return r[0] if r else default

    def set(self, k: str, v: str):
        self.db.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
        self.db.commit()
