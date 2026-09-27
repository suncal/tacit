from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import COOKIE, Principal, current_principal, hash_password, make_session_cookie, new_api_key, require_admin, verify_password
from ..core.audit import audit
from ..core.ids import new_id
from ..db import get_db
from .deps import get_app

router = APIRouter(prefix="/auth", tags=["auth"])


class SetupIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {"needs_setup": db.scalar(select(M.User.id).limit(1)) is None}


@router.post("/setup", response_model=UserOut)
def setup(body: SetupIn, response: Response, db: Session = Depends(get_db), app=Depends(get_app)):
    if app.settings.demo_mode:
        raise HTTPException(403, "this is a public demo — sign in with the demo account shown on the page")
    if db.scalar(select(M.User.id).limit(1)) is not None:
        raise HTTPException(409, "already set up")
    u = M.User(id=new_id("usr"), email=body.email.lower(), name=body.name, role="admin", password_hash=hash_password(body.password))
    db.add(u); audit(db, u.email, "auth.setup", u.id); db.commit()
    response.set_cookie(COOKIE, make_session_cookie(u.id), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14)
    return UserOut(id=u.id, email=u.email, name=u.name, role=u.role)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    u = db.scalar(select(M.User).where(M.User.email == body.email.lower()))
    if not u or not verify_password(body.password, u.password_hash):
        audit(db, body.email, "auth.login_failed", "", ok=False); db.commit()
        raise HTTPException(401, "wrong email or password")
    audit(db, u.email, "auth.login", u.id); db.commit()
    response.set_cookie(COOKIE, make_session_cookie(u.id), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14)
    return UserOut(id=u.id, email=u.email, name=u.name, role=u.role)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if p.kind == "user" and p.id != "setup":
        u = db.get(M.User, p.id)
        return UserOut(id=u.id, email=u.email, name=u.name, role=u.role)
    return UserOut(id=p.id, email=p.name, name=p.name, role=p.role)


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("/keys")
def list_keys(_: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return {"keys": [{"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": k.created_at, "last_used_at": k.last_used_at} for k in db.scalars(select(M.ApiKey))]}


@router.post("/keys")
def create_key(body: ApiKeyIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    raw, prefix, h = new_api_key()
    k = M.ApiKey(id=new_id("key"), name=body.name, prefix=prefix, key_hash=h)
    db.add(k); audit(db, p.label, "apikey.create", k.id, {"name": body.name}); db.commit()
    return {"id": k.id, "name": k.name, "prefix": prefix, "key": raw, "note": "shown once"}


@router.delete("/keys/{key_id}")
def delete_key(key_id: str, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    k = db.get(M.ApiKey, key_id)
    if k:
        db.delete(k); audit(db, p.label, "apikey.delete", key_id); db.commit()
    return {"ok": True}
