"""Encrypted keys (FreeLLMAPI): AES-256-GCM in SQLite, decrypt in-memory per request.
Plus single unified `feir-...` bearer token outward.
"""
from __future__ import annotations
import os
import secrets
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key(master: str) -> bytes:
    raw = master.encode()
    if len(raw) < 32:
        raw = raw.ljust(32, b"0")
    return raw[:32]


def encrypt(master: str, plaintext: str) -> str:
    aes = AESGCM(_key(master))
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(master: str, blob: str) -> str:
    raw = base64.b64decode(blob.encode())
    nonce, ct = raw[:12], raw[12:]
    aes = AESGCM(_key(master))
    return aes.decrypt(nonce, ct, None).decode()


def new_unified_key() -> str:
    return "feir-" + secrets.token_urlsafe(24)
