"""allow / ask / deny for every (principal, tool). First matching rule wins; otherwise the risk-class default."""
import fnmatch

from sqlalchemy import select

from .. import models as M


class Policy:
    def __init__(self, settings):
        self.defaults = {"read": settings.default_read, "write": settings.default_write, "exec": settings.default_exec}

    def rules(self, db):
        return list(db.scalars(select(M.Policy).order_by(M.Policy.created_at)))

    def decide(self, db, principal: str, tool) -> tuple[str, str]:
        for r in self.rules(db):
            if fnmatch.fnmatch(principal, r.principal) and fnmatch.fnmatch(tool.name, r.tool):
                return r.decision, f"rule {r.id}: {r.principal} × {r.tool}"
        return self.defaults.get(tool.risk, "ask"), f"default for {tool.risk} tools"

    def visible(self, db, principal: str, tools: list) -> list:
        return [t for t in tools if self.decide(db, principal, t)[0] != "deny"]
