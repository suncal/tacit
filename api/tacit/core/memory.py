"""Dependency-free relevance over org memory: token overlap, recency tie-break. Explainable on purpose."""
from sqlalchemy import select

from .. import models as M
from . import text as T


def search(db, query: str, limit: int = 8) -> list[M.Memory]:
    toks = set(T.tokens(query))
    rows = list(db.scalars(select(M.Memory).order_by(M.Memory.created_at.desc()).limit(3000)))
    if not toks:
        return rows[:limit]
    scored = []
    for m in rows:
        hay = set(T.tokens(m.text + " " + " ".join(m.tags or [])))
        overlap = len(toks & hay)
        if overlap:
            scored.append((overlap + 0.5 * T.jaccard(toks, hay), m.created_at, m))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [s[2] for s in scored[:limit]]
