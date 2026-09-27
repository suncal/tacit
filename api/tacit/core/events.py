"""Event ingestion: the single door through which every observed action enters Tacit."""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import select

from .. import models as M
from ..db import session
from .ids import new_id


def ingest(app, system: str, kind: str, actor: str, text: str = "", target: str = "", thread_key: str = "",
           ts: Optional[float] = None, meta: Optional[dict] = None, external_id: Optional[str] = None,
           actor_type: str = "human", shadow: bool = True) -> Optional[str]:
    """Persist an event (idempotent on external_id) and hand it to the shadow engine. Returns the event id."""
    with session() as db:
        if external_id and db.scalar(select(M.Event.id).where(M.Event.external_id == external_id)):
            return None
        e = M.Event(id=new_id("evt"), system=system, kind=kind, actor=actor, actor_type=actor_type, target=target or "",
                    thread_key=thread_key or f"{system}:{target}:{new_id('t')}", text=text or "", meta=meta or {},
                    ts=ts or time.time(), external_id=external_id)
        db.add(e)
        db.flush()
        eid = e.id
        if actor_type == "agent":
            from .oversight import on_agent_event
            on_agent_event(db, app, e)
        elif actor_type == "human":
            from .oversight import on_human_event
            on_human_event(db, e)
    if shadow and actor_type == "human":
        try:
            app.shadow.on_event(eid)
        except Exception as ex:  # shadowing must never break ingestion
            import logging
            logging.getLogger("tacit.events").exception("shadow failed for %s: %s", eid, ex)
    return eid


def as_dict(e: M.Event) -> dict:
    return {"id": e.id, "system": e.system, "kind": e.kind, "actor": e.actor, "actor_type": e.actor_type, "target": e.target,
            "thread_key": e.thread_key, "text": e.text, "meta": e.meta, "ts": e.ts, "external_id": e.external_id}
