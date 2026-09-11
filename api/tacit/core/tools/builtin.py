"""Built-in tools. Every write returns a ToolResult with an undo recipe."""
from __future__ import annotations

import difflib
import html
import os
import re
import subprocess

import httpx
from sqlalchemy import select

from ... import models as M
from ..ids import new_id
from .registry import Registry, ToolResult, obj


def _safe_path(workspace: str, path: str) -> str:
    full = os.path.abspath(os.path.join(workspace, path))
    ws = os.path.abspath(workspace)
    if full != ws and not full.startswith(ws + os.sep):
        raise ValueError(f"path escapes workspace: {path}")
    return full


def strip_html(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def unified_diff(old: str, new: str, path: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=f"a/{path}", tofile=f"b/{path}"))


def register_builtins(reg: Registry, settings) -> None:
    ws = os.path.abspath(settings.workspace)

    # ------------------------------------------------------------------ memory
    @reg.tool("memory_remember", "Save a durable fact, decision or preference to shared org memory.",
              obj({"text": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, ["text"]), system="memory")
    def memory_remember(ctx, text, tags=None):
        db = ctx["db"]
        m = M.Memory(id=new_id("mem"), text=text.strip(), tags=tags or [], source=ctx.get("principal", ""))
        db.add(m); db.flush()
        return ToolResult({"id": m.id, "saved": text.strip()}, undo={"tool": "memory_forget", "args": {"id": m.id}})

    @reg.tool("memory_search", "Search shared org memory for relevant facts, decisions and context.", obj({"query": {"type": "string"}}, ["query"]), system="memory")
    def memory_search(ctx, query):
        from ..memory import search
        return {"results": [{"id": m.id, "text": m.text, "tags": m.tags} for m in search(ctx["db"], query)]}

    @reg.tool("memory_forget", "Delete a memory by id.", obj({"id": {"type": "string"}}, ["id"]), risk="write", system="memory")
    def memory_forget(ctx, id):
        db = ctx["db"]
        m = db.get(M.Memory, id)
        if not m:
            return {"deleted": id, "note": "already gone"}
        snapshot = {"text": m.text, "tags": m.tags}
        db.delete(m); db.flush()
        return ToolResult({"deleted": id}, undo={"tool": "memory_remember", "args": snapshot})

    # ------------------------------------------------------------------ tasks
    @reg.tool("task_create", "Create a task in the shared task list.",
              obj({"title": {"type": "string"}, "detail": {"type": "string"}, "assignee": {"type": "string"}, "due": {"type": "string"}}, ["title"]), system="tasks")
    def task_create(ctx, title, detail="", assignee="", due=""):
        db = ctx["db"]
        t = M.Task(id=new_id("task"), title=title.strip(), detail=detail, assignee=assignee, due=due, source=ctx.get("channel", ""))
        db.add(t); db.flush()
        return ToolResult({"id": t.id, "title": t.title}, undo={"tool": "task_delete", "args": {"id": t.id}})

    @reg.tool("task_list", "List tasks. status: open | done | all.", obj({"status": {"type": "string"}}), system="tasks")
    def task_list(ctx, status="open"):
        q = select(M.Task).order_by(M.Task.created_at.desc())
        if status and status != "all":
            q = q.where(M.Task.status == status)
        return {"tasks": [{"id": t.id, "title": t.title, "status": t.status, "assignee": t.assignee, "due": t.due} for t in ctx["db"].scalars(q)]}

    @reg.tool("task_complete", "Mark a task done.", obj({"id": {"type": "string"}}, ["id"]), system="tasks")
    def task_complete(ctx, id):
        t = ctx["db"].get(M.Task, id)
        if not t:
            raise ValueError(f"no task {id}")
        prev = t.status
        t.status = "done"; t.done_at = M.now()
        return ToolResult({"id": id, "status": "done"}, undo={"tool": "task_set_status", "args": {"id": id, "status": prev}})

    @reg.tool("task_set_status", "Set a task's status (open | done | cancelled).", obj({"id": {"type": "string"}, "status": {"type": "string"}}, ["id", "status"]), risk="write", system="tasks")
    def task_set_status(ctx, id, status):
        t = ctx["db"].get(M.Task, id)
        if not t:
            raise ValueError(f"no task {id}")
        prev = t.status
        t.status = status
        return ToolResult({"id": id, "status": status}, undo={"tool": "task_set_status", "args": {"id": id, "status": prev}})

    @reg.tool("task_delete", "Delete a task.", obj({"id": {"type": "string"}}, ["id"]), risk="write", system="tasks")
    def task_delete(ctx, id):
        db = ctx["db"]
        t = db.get(M.Task, id)
        if not t:
            return {"deleted": id, "note": "already gone"}
        snap = {"title": t.title, "detail": t.detail, "assignee": t.assignee, "due": t.due}
        db.delete(t); db.flush()
        return ToolResult({"deleted": id}, undo={"tool": "task_create", "args": snap})

    # ------------------------------------------------------------------ automations
    @reg.tool("automation_create",
              "Delegate a task to Tacit forever. schedule: 'every 30m' | 'daily 09:00' | 'weekly mon 09:00' | 'on github.pr.opened' | 'on webhook:deploy'.",
              obj({"name": {"type": "string"}, "schedule": {"type": "string"}, "prompt": {"type": "string"}}, ["name", "schedule", "prompt"]), risk="write", system="automations")
    def automation_create(ctx, name, schedule, prompt):
        from ..scheduler import parse_schedule, compute_next
        trig = parse_schedule(schedule)
        a = M.Automation(id=new_id("auto"), name=name, trigger=trig, prompt=prompt, next_run_at=compute_next(trig))
        ctx["db"].add(a); ctx["db"].flush()
        return ToolResult({"id": a.id, "name": name, "trigger": trig}, undo={"tool": "automation_delete", "args": {"id": a.id}})

    @reg.tool("automation_delete", "Delete an automation.", obj({"id": {"type": "string"}}, ["id"]), risk="write", system="automations")
    def automation_delete(ctx, id):
        db = ctx["db"]
        a = db.get(M.Automation, id)
        if not a:
            return {"deleted": id}
        snap = {"name": a.name, "schedule": a.trigger.get("human", ""), "prompt": a.prompt}
        db.delete(a); db.flush()
        return ToolResult({"deleted": id}, undo={"tool": "automation_create", "args": snap})

    @reg.tool("automation_list", "List automations.", obj({}), system="automations")
    def automation_list(ctx):
        return {"automations": [{"id": a.id, "name": a.name, "trigger": a.trigger, "enabled": a.enabled} for a in ctx["db"].scalars(select(M.Automation))]}

    # ------------------------------------------------------------------ web
    @reg.tool("web_fetch", "Fetch a URL and return its readable text (max 20k chars).", obj({"url": {"type": "string"}}, ["url"]), system="web")
    def web_fetch(ctx, url):
        if not url.startswith(("http://", "https://")):
            raise ValueError("only http(s) URLs")
        r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "tacit/0.1"})
        return {"url": url, "status": r.status_code, "text": strip_html(r.text)[:20000]}

    # ------------------------------------------------------------------ files / shell (workspace-jailed)
    @reg.tool("file_read", "Read a file inside the workspace.", obj({"path": {"type": "string"}}, ["path"]), system="files")
    def file_read(ctx, path):
        with open(_safe_path(ws, path), "r", errors="replace") as f:
            return {"path": path, "content": f.read(200000)}

    @reg.tool("file_list", "List files under a workspace directory.", obj({"path": {"type": "string"}}), system="files")
    def file_list(ctx, path="."):
        full, out = _safe_path(ws, path), []
        for root, dirs, files in os.walk(full):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".venv")]
            for fn in files:
                out.append(os.path.relpath(os.path.join(root, fn), ws))
                if len(out) >= 500:
                    return {"files": out, "truncated": True}
        return {"files": out}

    def _file_preview(ctx, path, content):
        full = _safe_path(ws, path)
        old = open(full, errors="replace").read() if os.path.exists(full) else ""
        diff = unified_diff(old, content, path)
        adds = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
        dels = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
        return {"system": "files", "kind": "update" if old else "create", "summary": f"{'modify' if old else 'create'} {path} (+{adds} −{dels})", "diff": diff[:20000]}

    @reg.tool("file_write", "Write a file inside the workspace (creates or overwrites).",
              obj({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]), risk="write", system="files", previewer=_file_preview)
    def file_write(ctx, path, content):
        full = _safe_path(ws, path)
        existed = os.path.exists(full)
        old = open(full, errors="replace").read() if existed else None
        pv = _file_preview(ctx, path, content)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        undo = {"tool": "file_write", "args": {"path": path, "content": old}} if existed else {"tool": "file_delete", "args": {"path": path}}
        return ToolResult({"path": path, "bytes": len(content)}, undo=undo, preview=pv)

    @reg.tool("file_delete", "Delete a file inside the workspace.", obj({"path": {"type": "string"}}, ["path"]), risk="write", system="files")
    def file_delete(ctx, path):
        full = _safe_path(ws, path)
        if not os.path.exists(full):
            return {"deleted": path, "note": "already gone"}
        old = open(full, errors="replace").read()
        os.remove(full)
        return ToolResult({"deleted": path}, undo={"tool": "file_write", "args": {"path": path, "content": old}})

    @reg.tool("shell_run", "Run a shell command in the workspace (60s timeout). Not reversible.",
              obj({"command": {"type": "string"}}, ["command"]), risk="exec", system="shell",
              previewer=lambda ctx, command: {"system": "shell", "kind": "exec", "summary": f"run `{command}`", "irreversible": True})
    def shell_run(ctx, command):
        p = subprocess.run(command, shell=True, cwd=ws, capture_output=True, text=True, timeout=60)
        return ToolResult({"exit": p.returncode, "stdout": p.stdout[-20000:], "stderr": p.stderr[-5000:]}, undo=None)

    # ------------------------------------------------------------------ meta
    @reg.tool("audit_recent", "Show what Tacit did recently.", obj({"limit": {"type": "integer"}}), system="audit")
    def audit_recent(ctx, limit=30):
        rows = ctx["db"].scalars(select(M.AuditEvent).order_by(M.AuditEvent.id.desc()).limit(limit))
        return {"events": [{"ts": e.ts, "actor": e.actor, "action": e.action, "target": e.target, "ok": e.ok} for e in rows]}

    @reg.tool("emit_event", "Fire an internal event that can trigger 'on <event>' automations.",
              obj({"event": {"type": "string"}, "payload": {"type": "object"}}, ["event"]), risk="write", system="automations")
    def emit_event(ctx, event, payload=None):
        bus = ctx.get("bus")
        return {"event": event, "automations_triggered": bus.emit(event, payload or {}) if bus else 0}

    @reg.tool("note", "Record a note (used when a playbook's target system is not connected).", obj({"text": {"type": "string"}, "target": {"type": "string"}}, ["text"]), risk="write", system="notes")
    def note(ctx, text, target=""):
        db = ctx["db"]
        m = M.Memory(id=new_id("mem"), kind="note", text=text, tags=["note", target] if target else ["note"], source=ctx.get("principal", ""))
        db.add(m); db.flush()
        return ToolResult({"id": m.id, "posted": f"note:{m.id}"}, undo={"tool": "memory_forget", "args": {"id": m.id}})
