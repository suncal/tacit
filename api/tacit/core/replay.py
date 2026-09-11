"""Replay: re-run a recorded run against the current brain with recorded tool results substituted in.
Nothing touches the outside world. The result is a decision diff: did the brain choose the same actions?
Evals grown from production, not from a spreadsheet."""
from __future__ import annotations

import json
import time

from .. import models as M
from ..db import session
from .audit import audit
from .ids import new_id


class RecordedTools:
    """Serves tool results from a recorded transcript. Unknown calls get a polite stub."""
    def __init__(self, messages: list[dict]):
        self.by_call: dict[str, str] = {}
        calls = {}
        for m in messages:
            if isinstance(m["content"], list):
                for b in m["content"]:
                    if b.get("type") == "tool_use":
                        calls[b["id"]] = (b["name"], json.dumps(b["input"], sort_keys=True))
                    elif b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                        self.by_call[calls[b["tool_use_id"]]] = b["content"]

    def result(self, name: str, args: dict) -> str:
        key = (name, json.dumps(args, sort_keys=True))
        if key in self.by_call:
            return self.by_call[key]
        for (n, _), v in self.by_call.items():   # same tool, different args → closest we have
            if n == name:
                return v
        return json.dumps({"replay": "no recorded result for this call"})


def replay(app, run_id: str, by: str = "console") -> dict:
    with session() as db:
        orig = db.get(M.Run, run_id)
        if not orig:
            raise ValueError("no such run")
        if orig.draft_id:
            return _replay_draft(app, db, orig, by)
        messages = list(orig.messages)
        first = messages[0]["content"] if messages else orig.input
        original_calls = [(b["name"], b["input"]) for m in messages if m["role"] == "assistant" and isinstance(m["content"], list) for b in m["content"] if b.get("type") == "tool_use"]
        principal, channel = orig.principal, orig.channel
        tools = app.policy.visible(db, principal, app.registry.all())
    rec = RecordedTools(messages)
    from .agent import SYSTEM
    from .memory import search
    with session() as db:
        mem = "\n".join(f"- {m.text}" for m in search(db, orig.input, 10)) or "- (nothing relevant yet)"
    system = SYSTEM.format(handle=app.settings.handle, org=app.settings.org_name, channel=channel, principal=principal, ts=time.strftime("%Y-%m-%d %H:%M"), memory=mem)
    msgs = [{"role": "user", "content": first}]
    new_calls, steps, text = [], [], ""
    for _ in range(8):
        turn = app.brain.complete(system, msgs, tools)
        text = turn.text or text
        if not turn.tool_calls:
            break
        content = turn.raw or [{"type": "text", "text": turn.text}]
        content = content + [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["input"]} for c in turn.tool_calls if not any(b.get("id") == c["id"] for b in content)]
        msgs.append({"role": "assistant", "content": content})
        results = []
        for c in turn.tool_calls:
            new_calls.append((c["name"], c["input"]))
            steps.append({"type": "tool", "name": c["name"], "args": c["input"], "ok": True, "replayed": True, "ts": time.time()})
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": rec.result(c["name"], c["input"])})
        msgs.append({"role": "user", "content": results})
    same = [c for c in new_calls if c in original_calls]
    diff = {"original": [{"tool": n, "args": a} for n, a in original_calls], "replayed": [{"tool": n, "args": a} for n, a in new_calls],
            "identical": new_calls == original_calls, "overlap": round(len(same) / max(len(original_calls), 1), 3)}
    with session() as db:
        r = M.Run(id=new_id("run"), channel=f"replay:{channel}", principal=principal, input=orig.input, output=text, status="done",
                  steps=steps, messages=msgs, tx_status="committed", replay_of=orig.id, finished_at=time.time(), usage={"model": getattr(app.brain, "model", "—")})
        db.add(r)
        audit(db, by, "run.replay", orig.id, {"replay": r.id, "identical": diff["identical"], "overlap": diff["overlap"]})
        rid = r.id
    return {"replay_run_id": rid, "output": text, "diff": diff}


def _replay_draft(app, db, orig: M.Run, by: str) -> dict:
    """A playbook run is a draft that got enacted. Replaying it means drafting again with the current brain
    and measuring how far the new draft is from the one that ran."""
    from . import text as T
    from .events import as_dict
    d = db.get(M.Draft, orig.draft_id)
    pb = db.get(M.Playbook, orig.playbook_id)
    trig = db.get(M.Event, d.trigger_event_id)
    pbd = {"name": pb.name, "actor": pb.actor, "org": app.settings.org_name, "response": pb.response}
    new_text = app.brain.draft(pbd, trig.text, pb.examples or [], app.shadow._thread_context(db, trig))
    old_text = d.content.get("text", "")
    sim = T.similarity(old_text, new_text)
    r = M.Run(id=new_id("run"), channel=f"replay:{orig.channel}", principal=orig.principal, input=orig.input, output=new_text, status="done",
              steps=[{"type": "say", "text": new_text, "replayed": True, "ts": time.time()}], messages=[{"role": "user", "content": as_dict(trig)["text"]}],
              tx_status="committed", replay_of=orig.id, playbook_id=pb.id, finished_at=time.time(), usage={"model": getattr(app.brain, "model", "—")})
    db.add(r)
    audit(db, by, "run.replay", orig.id, {"replay": r.id, "similarity": sim})
    return {"replay_run_id": r.id, "output": new_text,
            "diff": {"kind": "draft", "original_text": old_text, "replayed_text": new_text, "similarity": sim, "identical": sim >= 0.999,
                     "overlap": sim, "original": [{"tool": d.content.get("tool"), "args": d.content.get("args")}], "replayed": [{"tool": d.content.get("tool"), "args": {**(d.content.get("args") or {}), "text": new_text}}]}}
