from .. import models as M


def audit(db, actor: str, action: str, target: str = "", detail: dict | None = None, ok: bool = True) -> None:
    db.add(M.AuditEvent(actor=actor, action=action, target=target, detail=detail or {}, ok=ok))
