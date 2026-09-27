"""Sessions (signed cookie) for people, API keys for machines. Passwords: scrypt from the stdlib."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as M
from .core.ids import new_id
from .db import get_db
from .settings import get_settings

COOKIE = "tacit_session"
SESSION_TTL = 60 * 60 * 24 * 14


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        cand = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1)
        return hmac.compare_digest(cand.hex(), h)
    except Exception:
        return False


def _serializer():
    return URLSafeTimedSerializer(get_settings().secret_key, salt="session")


def make_session_cookie(user_id: str) -> str:
    return _serializer().dumps({"u": user_id, "t": time.time()})


def read_session_cookie(value: str) -> Optional[str]:
    try:
        return _serializer().loads(value, max_age=SESSION_TTL)["u"]
    except (BadSignature, KeyError):
        return None


def new_api_key() -> tuple[str, str, str]:
    raw = "tk_" + secrets.token_urlsafe(32)
    return raw, raw[:10], hashlib.sha256(raw.encode()).hexdigest()


class Principal:
    def __init__(self, kind: str, id: str, name: str, role: str = "admin"):
        self.kind, self.id, self.name, self.role = kind, id, name, role

    @property
    def label(self) -> str:
        return f"{'user' if self.kind == 'user' else 'apikey'}:{self.name}"


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        raw = auth[7:].strip()
        h = hashlib.sha256(raw.encode()).hexdigest()
        k = db.scalar(select(M.ApiKey).where(M.ApiKey.key_hash == h))
        if k:
            k.last_used_at = time.time(); db.commit()
            return Principal("apikey", k.id, k.name)
        raise HTTPException(401, "invalid API key")
    cookie = request.cookies.get(COOKIE)
    uid = read_session_cookie(cookie) if cookie else None
    if uid:
        u = db.get(M.User, uid)
        if u:
            return Principal("user", u.id, u.email, u.role)
    # first-run convenience: no users exist yet → open console, so setup is possible.
    # never on a public demo, where the database is always seeded.
    if not get_settings().demo_mode and db.scalar(select(M.User.id).limit(1)) is None:
        return Principal("user", "setup", "setup", "admin")
    raise HTTPException(401, "not signed in")


def require_admin(p: Principal = Depends(current_principal)) -> Principal:
    if p.role != "admin":
        raise HTTPException(403, "admin only")
    return p
