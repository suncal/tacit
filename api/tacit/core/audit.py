from .. import models as M
from .live import INTERESTING, live


def audit(db, actor: str, action: str, target: str = "", detail: dict | None = None, ok: bool = True) -> None:
    """Record it, and — when a person would want to see it happen — broadcast it to open consoles."""
    db.add(M.AuditEvent(actor=actor, action=action, target=target, detail=detail or {}, ok=ok))
    if action in INTERESTING:
        live.publish(action, {"actor": actor, "target": target, "ok": ok, "detail": _small(detail or {})})


def _small(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, str):
            out[k] = v[:180]
    return out
