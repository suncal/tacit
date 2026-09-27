"""The agent loop.

brain proposes → policy decides (allow / ask / deny) → budgets are checked → the tool runs inside the run's
transaction (every write records its undo) → everything is audited. A run pauses on 'ask' and resumes from its
stored transcript when a human decides. Nothing executes silently; anything that executed can be undone.
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from typing import Any, Optional

from .. import models as M
from ..db import session
from .audit import audit
from .budgets import BudgetExceeded, check as check_budget
from .ids import new_id
from .memory import search as memory_search
from .preview import preview as make_preview
from .tools.registry import ToolResult

log = logging.getLogger("tacit.agent")
MAX_STEPS = 8

SYSTEM = """You are @{handle}, the AI teammate for {org}. You are self-hosted by this team and answer to them.
You know the company's shared memory (below), can create tasks and automations, and can act in the team's tools.
Be concise and concrete. When someone gives you a fact, decision or preference worth keeping, save it with memory_remember.
Search memory before guessing about the company. Never invent facts.
Some tools pause for human approval; if one does, say so plainly and stop.

Channel: {channel}   Requester: {principal}   Now: {ts}

Relevant org memory:
{memory}
"""


def _short(obj, n=600):
    s = json.dumps(obj, default=str)
    return s if len(s) <= n else s[:n] + "…"


class Agent:
    def __init__(self, app):
        self.app = app

    # ------------------------------------------------------------------ public
    def run(self, channel: str, principal: str, text: str, context: Optional[str] = None,
            playbook_id: Optional[str] = None, draft_id: Optional[str] = None) -> dict:
        with session() as db:
            r = M.Run(id=new_id("run"), channel=channel, principal=principal, input=text, playbook_id=playbook_id, draft_id=draft_id)
            db.add(r)
            audit(db, principal, "run.start", r.id, {"channel": channel, "input": text[:500]})
            rid = r.id
        content = text if not context else f"{text}\n\n<context>\n{context}\n</context>"
        return self._loop(rid, [{"role": "user", "content": content}], [])

    def resume(self, run_id: str) -> Optional[dict]:
        with session() as db:
            r = db.get(M.Run, run_id)
            if not r or r.status != "waiting":
                return self.public(r) if r else None
            messages, steps = list(r.messages), list(r.steps)
        return self._loop(run_id, messages, steps)

    def decide_approval(self, approval_id: str, approve: bool, by: str = "console") -> Optional[dict]:
        with session() as db:
            a = db.get(M.Approval, approval_id)
            if not a or a.status != "pending":
                return None
            a.status = "approved" if approve else "denied"
            a.decided_at, a.decided_by = time.time(), by
            audit(db, by, "approval." + a.status, a.tool, {"approval": a.id, "args": a.args, "run": a.run_id})
            run_id, pb_id = a.run_id, a.playbook_id
            # An approval granted faster than the preview could be read is a signature, not oversight.
            # It still happened and is still logged — it simply cannot be evidence that the job is safe.
            from .oversight_quality import decision_quality
            q = decision_quality(db, a) or {}
            considered = q.get("attention") == "considered"
            if pb_id:
                pb = db.get(M.Playbook, pb_id)
                if pb:
                    if not approve:
                        pb.rejections += 1
                    elif considered:
                        pb.approvals += 1
            if approve and not considered:
                audit(db, by, "approval.unread", a.tool,
                      {"approval": a.id, "seconds": q.get("seconds"), "needed_seconds": q.get("needed_seconds"),
                       "note": "approved faster than the preview could be read — not counted towards autonomy"})
            r = db.get(M.Run, run_id)
            if r and r.draft_id:
                d = db.get(M.Draft, r.draft_id)
                if d:
                    d.status = "executed" if approve else "rejected"
                    d.resolved_at = time.time()
        return self.resume(run_id)

    def undo_run(self, run_id: str, by: str = "console") -> dict:
        """Reverse every reversible action of a run, newest first. Idempotent."""
        with session() as db:
            r = db.get(M.Run, run_id)
            if not r:
                raise ValueError("no such run")
            actions = [a for a in reversed(r.actions) if a.status == "done"]
            results = []
            ctx = {"db": db, "principal": by, "channel": r.channel, "run_id": r.id, "bus": self.app.bus, "brain": self.app.brain}
            for a in actions:
                if not a.undo:
                    results.append({"action": a.id, "tool": a.tool, "undone": False, "why": "irreversible"})
                    continue
                tool = self.app.registry.get(a.undo["tool"])
                try:
                    if not tool:
                        raise RuntimeError(f"undo tool {a.undo['tool']} not available")
                    out = tool.fn(ctx, **(a.undo.get("args") or {}))
                    a.status, a.undone_at = "undone", time.time()
                    results.append({"action": a.id, "tool": a.tool, "undone": True, "result": _short(out.data if isinstance(out, ToolResult) else out, 200)})
                    audit(db, by, "action.undone", a.tool, {"run": r.id, "action": a.id, "undo": a.undo["tool"]})
                except Exception as e:
                    a.status = "undo_failed"
                    results.append({"action": a.id, "tool": a.tool, "undone": False, "why": str(e)})
                    audit(db, by, "action.undo_failed", a.tool, {"run": r.id, "action": a.id, "error": str(e)}, ok=False)
            undone = sum(1 for x in results if x["undone"])
            r.tx_status = "undone" if undone and undone == len([x for x in results if x.get("why") != "irreversible"]) else ("partial" if undone else r.tx_status)
            if r.playbook_id:
                pb = db.get(M.Playbook, r.playbook_id)
                if pb and undone:
                    pb.undos += 1
            audit(db, by, "run.undo", r.id, {"undone": undone, "total": len(actions)})
            return {"run": r.id, "tx_status": r.tx_status, "results": results}

    def public(self, r: M.Run) -> dict:
        return {"id": r.id, "channel": r.channel, "principal": r.principal, "input": r.input, "output": r.output, "status": r.status,
                "steps": r.steps, "tx_status": r.tx_status, "playbook_id": r.playbook_id, "draft_id": r.draft_id, "replay_of": r.replay_of,
                "usage": r.usage, "created_at": r.created_at, "finished_at": r.finished_at,
                "actions": [{"id": a.id, "tool": a.tool, "args": a.args, "result": a.result, "undo": a.undo, "status": a.status, "preview": a.preview, "ts": a.ts} for a in r.actions]}

    # ------------------------------------------------------------------ loop
    def _loop(self, rid: str, messages: list[dict], steps: list[dict]) -> dict:
        app = self.app
        with session() as db:
            r = db.get(M.Run, rid)
            channel, principal, text = r.channel, r.principal, r.input
            tools = app.policy.visible(db, principal, app.registry.all())
            mem = memory_search(db, text, limit=10)
            mem_txt = "\n".join(f"- {m.text}" for m in mem) or "- (nothing relevant yet)"
        system = SYSTEM.format(handle=app.settings.handle, org=app.settings.org_name, channel=channel, principal=principal,
                               ts=time.strftime("%Y-%m-%d %H:%M"), memory=mem_txt)
        usage_total = {"input_tokens": 0, "output_tokens": 0, "usd": 0.0}
        try:
            for _ in range(MAX_STEPS):
                pending = self._pending_calls(messages)
                if not pending:
                    turn = app.brain.complete(system, messages, tools)
                    for k in ("input_tokens", "output_tokens", "usd"):
                        usage_total[k] += turn.usage.get(k, 0) or 0
                    content = turn.raw or ([{"type": "text", "text": turn.text}] if turn.text else [])
                    content = content + [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["input"]}
                                         for c in turn.tool_calls if not any(b.get("id") == c["id"] for b in content)]
                    if turn.text:
                        steps.append({"type": "say", "text": turn.text, "ts": time.time()})
                    if not turn.tool_calls:
                        return self._finish(rid, "done", turn.text, steps, messages + [{"role": "assistant", "content": content}], usage_total)
                    messages.append({"role": "assistant", "content": content})
                    pending = turn.tool_calls
                results, waiting = [], False
                for c in pending:
                    if self._has_result(messages, c["id"]):
                        continue
                    res = self._execute(rid, channel, principal, c, steps)
                    if res is None:
                        waiting = True
                        continue
                    results.append(res)
                if waiting:
                    if results:
                        messages.append({"role": "user", "content": results})
                    with session() as db:
                        r = db.get(M.Run, rid)
                        r.status, r.steps, r.messages, r.output = "waiting", steps, messages, "Waiting for approval."
                        r.usage = self._merge_usage(r.usage, usage_total)
                        return self.public(r)
                messages.append({"role": "user", "content": results})
            return self._finish(rid, "done", f"Stopped after {MAX_STEPS} steps.", steps, messages, usage_total)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            log.error("run %s failed: %s\n%s", rid, err, traceback.format_exc())
            steps.append({"type": "error", "text": err, "ts": time.time()})
            with session() as db:
                audit(db, principal, "run.error", rid, {"error": err}, ok=False)
            return self._finish(rid, "error", err, steps, messages, usage_total)

    def _finish(self, rid, status, output, steps, messages, usage):
        with session() as db:
            r = db.get(M.Run, rid)
            r.status, r.output, r.steps, r.messages, r.finished_at = status, output or "", steps, messages, time.time()
            r.usage = self._merge_usage(r.usage, usage)
            if r.tx_status == "open":
                r.tx_status = "committed"
            audit(db, r.principal, "run." + status, rid, {"output": (output or "")[:500]}, ok=status != "error")
            return self.public(r)

    @staticmethod
    def _merge_usage(old, new):
        old = dict(old or {})
        for k, v in new.items():
            old[k] = round((old.get(k, 0) or 0) + (v or 0), 6)
        return old

    def _pending_calls(self, messages):
        def calls_of(m):
            return [{"id": b["id"], "name": b["name"], "input": b["input"]} for b in m["content"] if b.get("type") == "tool_use"] if isinstance(m["content"], list) else []
        if not messages:
            return []
        if messages[-1]["role"] == "assistant":
            return calls_of(messages[-1])
        if len(messages) >= 2 and messages[-2]["role"] == "assistant":
            return [c for c in calls_of(messages[-2]) if not self._has_result(messages, c["id"])]
        return []

    @staticmethod
    def _has_result(messages, call_id):
        return any(b.get("type") == "tool_result" and b.get("tool_use_id") == call_id
                   for m in messages if m["role"] == "user" and isinstance(m["content"], list) for b in m["content"])

    # ------------------------------------------------------------------ execution
    def _execute(self, rid, channel, principal, call, steps):
        app = self.app
        tool = app.registry.get(call["name"])
        with session() as db:
            if not tool:
                steps.append({"type": "tool", "name": call["name"], "ok": False, "text": "unknown tool", "ts": time.time()})
                return self._err(call, "unknown tool")
            decision, why = app.policy.decide(db, principal, tool)
            if decision == "deny":
                audit(db, principal, "tool.denied", tool.name, {"args": call["input"], "why": why}, ok=False)
                steps.append({"type": "tool", "name": tool.name, "ok": False, "text": f"denied by policy ({why})", "ts": time.time()})
                return self._err(call, "denied by policy: " + why)
            try:
                check_budget(db, principal, tool)
            except BudgetExceeded as e:
                audit(db, principal, "tool.budget", tool.name, {"args": call["input"], "why": str(e)}, ok=False)
                steps.append({"type": "tool", "name": tool.name, "ok": False, "text": str(e), "ts": time.time()})
                return self._err(call, str(e))
            if decision == "ask":
                r = db.get(M.Run, rid)
                existing = next((a for a in db.query(M.Approval).filter_by(run_id=rid) if a.call_id == call["id"]), None)
                if existing is None:
                    ctx = {"db": db, "principal": principal, "channel": channel, "run_id": rid}
                    pv = make_preview(tool, ctx, call["input"] or {})
                    a = M.Approval(id=new_id("apr"), run_id=rid, call_id=call["id"], tool=tool.name, args=call["input"] or {},
                                   preview=pv, principal=principal, reason=why, playbook_id=r.playbook_id)
                    db.add(a)
                    audit(db, principal, "tool.ask", tool.name, {"approval": a.id, "args": call["input"], "preview": pv.get("summary")})
                    db.flush()
                    try:
                        from .notify import approval_pending
                        approval_pending(self.app, db, a)
                    except Exception:
                        log.warning("approval notification failed", exc_info=True)
                    steps.append({"type": "approval", "name": tool.name, "approval": a.id, "args": call["input"], "preview": pv, "text": "waiting for approval", "ts": time.time()})
                    return None
                if existing.status == "pending":
                    return None
                if existing.status == "denied":
                    steps.append({"type": "tool", "name": tool.name, "ok": False, "text": "a human declined this action", "ts": time.time()})
                    return self._err(call, "a human declined this action")
            return self._run_tool(db, rid, channel, principal, tool, call, steps)

    def _run_tool(self, db, rid, channel, principal, tool, call, steps):
        ctx = {"db": db, "principal": principal, "channel": channel, "run_id": rid, "bus": self.app.bus, "brain": self.app.brain}
        args = call["input"] or {}
        try:
            out = tool.fn(ctx, **args)
            res = out if isinstance(out, ToolResult) else ToolResult(out if isinstance(out, dict) else {"result": out})
            if tool.risk != "read":
                pv = res.preview or make_preview(tool, ctx, args)
                act = M.Action(id=new_id("act"), run_id=rid, tool=tool.name, args=args, result=res.data, undo=res.undo, preview=pv)
                db.add(act); db.flush()
                r = db.get(M.Run, rid)
                from .ledger import record as ledger_record
                ledger_record(db, act, r)
                if r.playbook_id:
                    pb = db.get(M.Playbook, r.playbook_id)
                    if pb:
                        pb.executions += 1
            audit(db, principal, "tool.run", tool.name, {"args": args, "ok": True, "reversible": res.undo is not None})
            steps.append({"type": "tool", "name": tool.name, "ok": True, "args": args, "result": _short(res.data), "reversible": res.undo is not None, "ts": time.time()})
            return {"type": "tool_result", "tool_use_id": call["id"], "content": json.dumps(res.data, default=str)[:60000]}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            audit(db, principal, "tool.run", tool.name, {"args": args, "error": err}, ok=False)
            steps.append({"type": "tool", "name": tool.name, "ok": False, "args": args, "text": err, "ts": time.time()})
            return self._err(call, err)

    @staticmethod
    def _err(call, msg):
        return {"type": "tool_result", "tool_use_id": call["id"], "content": json.dumps({"error": msg}), "is_error": True}
