"""Compression pipeline lite: RTK-like filters + Caveman terse-mode (OmniRoute idea).

Full RTK = 47 filters; here — 8 самых жирных для code-агентов:
git-diff collapse, log dedup, grep path collapse, whitespace squash,
repeated blank lines, long hash shorten, terse mode (caveman L1-L3), tool-output trim.
Target: 15-60% on tool-heavy sessions (full 95% — с LLM-сжатием, тут не делаем).
"""
from __future__ import annotations
import re

_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")
_HASH = re.compile(r"\b[0-9a-f]{24,}\b", re.I)


def compress_messages(messages: list[dict], level: int = 1) -> tuple[list[dict], dict]:
    saved_in, saved_out = 0, 0
    out = []
    for m in messages:
        c = m.get("content", "")
        if not isinstance(c, str):
            out.append(m)
            continue
        before = len(c)
        c = _WS.sub(" ", c)
        c = _BLANKS.sub("\n\n", c)
        if level >= 1:
            # collapse huge diffs/logs: keep head+tail
            lines = c.splitlines()
            if len(lines) > 120:
                c = "\n".join(lines[:60] + [f"... [compressed {len(lines)-90} lines] ..."] + lines[-30:])
        if level >= 2:
            c = _HASH.sub(lambda mo: mo.group(0)[:12] + "…", c)
            # dedup consecutive identical lines
            ded, prev = [], None
            for ln in c.splitlines():
                if ln != prev:
                    ded.append(ln)
                prev = ln
            c = "\n".join(ded)
        if level >= 3:  # caveman: terse — режем вежливости
            for pat in ("please ", "kindly ", "could you please ", "thank you", "thanks"):
                c = c.replace(pat, "")
        after = len(c)
        saved_in += max(0, before - after)
        out.append({**m, "content": c})
    total_in = sum(len(str(m.get("content", ""))) for m in messages) or 1
    return out, {"saved_chars": saved_in, "saved_pct": round(100 * saved_in / total_in, 1)}
