"""Trust: how sure are we that Tacit can do this job? Explainable, conservative, per playbook."""
import math

HIT_THRESHOLD = 0.5          # a draft this similar to what the human actually did counts as a hit
STAGES = ["candidate", "shadow", "propose", "auto", "retired"]


def wilson_lower(hits: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval — punishes small samples, the honest way."""
    if n == 0:
        return 0.0
    p = hits / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def trust(pb) -> dict:
    n = pb.drafts_scored
    hits = pb.drafts_hit
    mean = (pb.score_sum / n) if n else 0.0
    lb = wilson_lower(hits, n)
    approvals_n = pb.approvals + pb.rejections
    approval_rate = (pb.approvals / approvals_n) if approvals_n else None
    return {"scored": n, "hits": hits, "hit_rate": round(hits / n, 3) if n else 0.0, "mean_score": round(mean, 3),
            "trust": round(lb, 3), "approvals": pb.approvals, "rejections": pb.rejections,
            "approval_rate": round(approval_rate, 3) if approval_rate is not None else None,
            "executions": pb.executions, "undos": pb.undos}


def recommendation(pb, min_scored: int, min_trust: float) -> dict | None:
    """What should happen next with this playbook, and why. Never applied automatically."""
    t = trust(pb)
    if pb.stage == "candidate":
        return {"to": "shadow", "why": f"{pb.evidence_count} past occurrences, consistency {pb.consistency:.0%}. Shadowing costs nothing — it only drafts."}
    if pb.stage == "shadow":
        if t["scored"] >= min_scored and t["trust"] >= min_trust:
            return {"to": "propose", "why": f"{t['hits']}/{t['scored']} shadow drafts matched what {pb.actor} actually did (trust {t['trust']:.0%} ≥ {min_trust:.0%})."}
        if t["scored"] >= min_scored and t["trust"] < 0.3:
            return {"to": "retired", "why": f"Only {t['hits']}/{t['scored']} drafts matched — the real replies carry information Tacit can't see (live numbers, judgement). Retire it, or connect the data it needs."}
        return None
    if pb.stage == "propose":
        n = pb.approvals + pb.rejections
        if n >= min_scored and pb.rejections / n <= 0.1 and pb.undos == 0:
            return {"to": "auto", "why": f"{pb.approvals} approved, {pb.rejections} rejected, 0 undos. Every auto action stays reversible."}
        if n >= min_scored and pb.rejections / n > 0.4:
            return {"to": "shadow", "why": f"{pb.rejections}/{n} proposals rejected — back to shadow to re-learn."}
        return None
    if pb.stage == "auto" and pb.undos >= 3:
        return {"to": "propose", "why": f"{pb.undos} undos since going auto — demote to propose."}
    return None
