"""Pattern mining: turn a stream of human actions into candidate playbooks.

For every human 'response' event we find its trigger (the previous event in the same thread by
someone else) or note that it starts a thread on a cadence. Responses by the same person in the
same system are clustered by content similarity; clusters with enough evidence become playbooks.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import text as T

RESPONSE_KINDS = {"message", "comment", "review", "reply", "issue.comment", "pr.comment", "email"}
TRIGGER_WINDOW_S = 6 * 3600
MIN_EVIDENCE = 3
SIM_THRESHOLD = 0.35
MERGE_THRESHOLD = 0.30
MIN_TOKENS = 5


@dataclass
class Pair:
    trigger: Optional[dict]
    response: dict
    latency: float


@dataclass
class Candidate:
    actor: str
    system: str
    kind: str
    members: list[Pair] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.members)


def _find_trigger(resp: dict, thread: list[dict]) -> Optional[dict]:
    """Most recent earlier event in the thread by a different actor, within the window."""
    best = None
    for e in thread:
        if e["ts"] >= resp["ts"] or e["actor"] == resp["actor"]:
            continue
        if resp["ts"] - e["ts"] > TRIGGER_WINDOW_S:
            continue
        if best is None or e["ts"] > best["ts"]:
            best = e
    return best


def _pair_sim(a: Pair, b: Pair, sh_r: dict, sh_t: dict) -> float:
    """Two occurrences belong to the same pattern if the responses look alike — or if both the
    triggers and the responses look somewhat alike (a paraphrased reply to the same kind of ask)."""
    r = T.jaccard(sh_r[id(a)], sh_r[id(b)])
    if a.trigger and b.trigger:
        t = T.jaccard(sh_t[id(a)], sh_t[id(b)])
        return max(r, 0.5 * r + 0.5 * t)
    return r


def _cluster(pairs: list[Pair]) -> list[list[Pair]]:
    """Greedy agglomeration on a combined similarity, then a merge pass so paraphrase families
    (the same reply written three ways) end up as one pattern. n is small; O(n²) is fine."""
    sh_r = {id(p): T.shingles(p.response["text"]) for p in pairs}
    sh_t = {id(p): T.shingles(p.trigger["text"]) if p.trigger else set() for p in pairs}
    clusters: list[list[Pair]] = []
    for p in pairs:
        best, best_s = None, 0.0
        for c in clusters:
            s = max(_pair_sim(p, q, sh_r, sh_t) for q in c[-6:])
            if s > best_s:
                best, best_s = c, s
        if best is not None and best_s >= SIM_THRESHOLD:
            best.append(p)
        else:
            clusters.append([p])
    # merge pass: mean cross-similarity between clusters
    merged = True
    while merged and len(clusters) > 1:
        merged = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                a, b = clusters[i], clusters[j]
                cross = [_pair_sim(x, y, sh_r, sh_t) for x in a[:8] for y in b[:8]]
                if cross and sum(cross) / len(cross) >= MERGE_THRESHOLD:
                    clusters[i] = a + b
                    del clusters[j]
                    merged = True
                    break
            if merged:
                break
    return clusters


def _cadence(ts_list: list[float]) -> Optional[dict]:
    """Detect a period even when some occurrences are missing (holidays happen).
    Base period = the smallest typical gap; accept if most gaps are integer multiples of it."""
    if len(ts_list) < 3:
        return None
    ts_list = sorted(ts_list)
    gaps = [b - a for a, b in zip(ts_list, ts_list[1:]) if b - a > 3600]
    if len(gaps) < 2:
        return None
    base = statistics.median(sorted(gaps)[: max(2, len(gaps) // 2)])
    if base <= 0:
        return None
    ok = 0
    for g in gaps:
        k = round(g / base)
        if k >= 1 and abs(g - k * base) / base <= 0.15:
            ok += 1
    if ok / len(gaps) < 0.7:
        return None
    import datetime as dt
    hours = [dt.datetime.fromtimestamp(t).hour for t in ts_list]
    dows = [dt.datetime.fromtimestamp(t).weekday() for t in ts_list]
    hour = int(statistics.median(hours))
    if 6.5 * 86400 <= base <= 7.5 * 86400:
        dow = max(set(dows), key=dows.count)
        if dows.count(dow) / len(dows) < 0.7:
            return None
        return {"kind": "weekly", "dow": dow, "hour": hour, "human": f"every {['mon','tue','wed','thu','fri','sat','sun'][dow]} ~{hour:02d}:00"}
    if 0.8 * 86400 <= base <= 1.3 * 86400:
        return {"kind": "daily", "hour": hour, "human": f"daily ~{hour:02d}:00"}
    if base <= 3.5 * 86400:
        return {"kind": "interval", "seconds": int(base), "human": f"every ~{int(base / 3600)}h"}
    return None


def mine(events: Iterable[dict]) -> list[dict]:
    """events: dicts with id, system, kind, actor, actor_type, target, thread_key, text, ts.
    Returns playbook dicts ready to persist (or diff against existing)."""
    evs = sorted((e for e in events if e.get("actor_type", "human") == "human"), key=lambda e: e["ts"])
    threads: dict[str, list[dict]] = defaultdict(list)
    for e in evs:
        threads[e["thread_key"]].append(e)

    # 1. pair every response with its trigger
    by_actor: dict[tuple, list[Pair]] = defaultdict(list)
    for e in evs:
        if e["kind"] not in RESPONSE_KINDS or not e.get("text"):
            continue
        trig = _find_trigger(e, threads[e["thread_key"]])
        latency = (e["ts"] - trig["ts"]) if trig else 0.0
        by_actor[(e["actor"], e["system"], e["kind"])].append(Pair(trig, e, latency))

    # 2. cluster per (actor, system, kind)
    out = []
    for (actor, system, kind), pairs in by_actor.items():
        for cluster in _cluster(pairs):
            if len(cluster) < MIN_EVIDENCE:
                continue
            triggered = [p for p in cluster if p.trigger]
            scheduled = [p for p in cluster if not p.trigger]
            resp_texts = [p.response["text"] for p in cluster]
            if statistics.median(len(T.tokens(t)) for t in resp_texts) < MIN_TOKENS:
                continue                                    # "lunch?" is not a job
            consistency = _mean_pairwise(resp_texts)
            if consistency < 0.25:
                continue
            targets = [p.response.get("target", "") for p in cluster]
            target = max(set(targets), key=targets.count)
            if targets.count(target) / len(targets) < 0.6:
                target = ""                                 # pattern spans many places (e.g. one comment per issue)
            if len(triggered) >= max(2, len(cluster) // 2):
                trig_texts = [p.trigger["text"] for p in triggered]
                kws = T.keywords(trig_texts)
                if not kws:
                    continue                                # nothing to recognise the trigger by → not learnable
                trig_kinds = [p.trigger["kind"] for p in triggered]
                trigger = {"mode": "reply", "kind": max(set(trig_kinds), key=trig_kinds.count), "keywords": kws,
                           "target": target, "match": "any" if len(kws) > 2 else "all"}
                lat = statistics.median([p.latency for p in triggered])
                name = _name_reply(system, target, kws, kind, trigger["kind"])
            else:
                cad = _cadence([p.response["ts"] for p in scheduled or cluster])
                if not cad:
                    continue
                trigger = {"mode": "schedule", "cadence": cad, "target": target}
                lat = 0.0
                name = _name_schedule(system, target, cad, resp_texts)
            tmpl = T.template(resp_texts)
            examples = [{"trigger": (p.trigger or {}).get("text", ""), "trigger_event_id": (p.trigger or {}).get("id"),
                         "response": p.response["text"], "response_event_id": p.response.get("id"), "ts": p.response["ts"]}
                        for p in sorted(cluster, key=lambda p: -p.response["ts"])[:5]]
            out.append({
                "name": name, "system": system, "actor": actor, "trigger": trigger,
                "response": {"kind": kind, "target": target, "template": tmpl, "tool": _tool_for(system, kind)},
                "evidence_count": len(cluster), "consistency": round(consistency, 3), "median_latency_s": lat,
                "examples": examples,
                "delegability": round(min(1.0, len(cluster) / 12) * consistency, 3),
            })
    out = _dedupe(out)
    out.sort(key=lambda p: -p["delegability"])
    return out


def _dedupe(cands: list[dict]) -> list[dict]:
    """Two candidates for the same person/system whose trigger keywords overlap and whose replies look
    alike are one job, not two."""
    keep: list[dict] = []
    for c in cands:
        merged = False
        for k in keep:
            if (k["actor"], k["system"], k["trigger"].get("mode")) != (c["actor"], c["system"], c["trigger"].get("mode")):
                continue
            if c["trigger"].get("mode") == "reply":
                a, b = set(k["trigger"].get("keywords") or []), set(c["trigger"].get("keywords") or [])
                if not (a & b):
                    continue
            elif (k["trigger"].get("cadence") or {}).get("kind") != (c["trigger"].get("cadence") or {}).get("kind") or k["trigger"].get("target") != c["trigger"].get("target"):
                continue
            if T.similarity(k["response"]["template"], c["response"]["template"]) < MERGE_THRESHOLD:
                continue
            k["evidence_count"] += c["evidence_count"]
            k["examples"] = sorted(k["examples"] + c["examples"], key=lambda e: -e["ts"])[:6]
            k["consistency"] = round((k["consistency"] + c["consistency"]) / 2, 3)
            k["delegability"] = round(min(1.0, k["evidence_count"] / 12) * k["consistency"], 3)
            if c["trigger"].get("mode") == "reply":
                k["trigger"]["keywords"] = sorted(a & b) or k["trigger"]["keywords"]
                k["trigger"]["match"] = "any" if len(k["trigger"]["keywords"]) > 2 else "all"
            merged = True
            break
        if not merged:
            keep.append(c)
    return keep


def _mean_pairwise(texts: list[str]) -> float:
    if len(texts) < 2:
        return 0.0
    sh = [T.shingles(t) for t in texts]
    s, n = 0.0, 0
    for i in range(len(sh)):
        for j in range(i + 1, len(sh)):
            s += T.jaccard(sh[i], sh[j]); n += 1
    return s / n if n else 0.0


KIND_NOUN = {"pr.opened": "new pull requests", "issue.opened": "new issues", "message": "threads", "comment": "comments", "email": "emails"}


def _name_reply(system: str, target: str, kws: list[str], kind: str, trig_kind: str = "") -> str:
    noun = KIND_NOUN.get(trig_kind, trig_kind or "threads")
    where = f" in {target}" if target else ""
    if trig_kind in ("pr.opened", "issue.opened"):
        return f"First reply on {noun}{where}"
    what = " / ".join(kws[:2]) if kws else kind
    verb = {"github": "Reply to", "slack": "Answer", "linear": "Respond to", "email": "Reply to"}.get(system, "Respond to")
    return f"{verb} “{what}” {noun}{where}"


def _name_schedule(system: str, target: str, cad: dict, texts: list[str]) -> str:
    first = T.template(texts).strip().splitlines()[0].strip(" :-•") if texts else "update"
    first = first[:44] + ("…" if len(first) > 44 else "")
    return f"Post “{first}” {cad['human']}" + (f" in {target}" if target else "")


def _tool_for(system: str, kind: str) -> str:
    return {"github": "github_comment", "slack": "slack_post", "linear": "linear_comment", "email": "email_send"}.get(system, "note")
