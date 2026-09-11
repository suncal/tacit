"""Hard caps that no model can talk its way past."""
import fnmatch
import time

from sqlalchemy import func, select

from .. import models as M


class BudgetExceeded(RuntimeError):
    pass


def check(db, principal: str, tool) -> None:
    if tool.risk == "read":
        return
    for b in db.scalars(select(M.Budget)):
        if not fnmatch.fnmatch(principal, b.scope):
            continue
        hour_ago = time.time() - 3600
        writes = db.scalar(select(func.count(M.Action.id)).join(M.Run).where(M.Run.principal.like(_like(b.scope)), M.Action.ts >= hour_ago)) or 0
        if writes >= b.max_writes_per_hour:
            raise BudgetExceeded(f"budget '{b.scope}': {writes}/{b.max_writes_per_hour} writes in the last hour")
        day_ago = time.time() - 86400
        usd = 0.0
        for r in db.scalars(select(M.Run).where(M.Run.created_at >= day_ago)):
            if fnmatch.fnmatch(r.principal, b.scope):
                usd += float((r.usage or {}).get("usd", 0) or 0)
        if usd >= b.max_usd_per_day:
            raise BudgetExceeded(f"budget '{b.scope}': ${usd:.2f}/${b.max_usd_per_day:.2f} today")


def _like(pattern: str) -> str:
    return pattern.replace("*", "%")
