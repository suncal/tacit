"""No model at all. Deterministic, explainable, and honest about it.

Agent turns: a small grammar of team requests. Drafts: nearest-example retrieval with light slot filling.
Exists so the trust machinery is testable and demoable without any key — and so a reviewer can see
the harness work without trusting an AI."""
from __future__ import annotations

import json
import re

from .base import Brain, Turn
from .. import text as T
from ..ids import new_id


class LocalBrain(Brain):
    name = "local"
    model = "—"
    is_llm = False

    # ------------------------------------------------------------------ drafts
    def draft(self, playbook: dict, trigger_text: str, examples: list[dict], context: str = "", memory: str = "") -> str:
        if not examples:
            return playbook.get("response", {}).get("template", "")
        ts = T.shingles(trigger_text)
        best = max(examples, key=lambda e: T.jaccard(ts, T.shingles(e.get("trigger", ""))))
        close = T.jaccard(ts, T.shingles(best.get("trigger", ""))) >= 0.4
        template = playbook.get("response", {}).get("template", "")
        resp = (best.get("response") if close and best.get("response") else template) or best.get("response", "")
        # carry over @mentions / numbers from the new trigger when the example used them
        mentions = re.findall(r"@\w+", trigger_text)
        old_mentions = re.findall(r"@\w+", best.get("trigger", ""))
        for o, n in zip(old_mentions, mentions):
            resp = resp.replace(o, n)
        return resp

    # ------------------------------------------------------------------ agent
    def complete(self, system: str, messages: list[dict], tools: list) -> Turn:
        names = {t.name for t in tools}
        last_user, results = "", []
        for m in messages:
            c = m["content"]
            if m["role"] != "user":
                continue
            if isinstance(c, str):
                last_user, results = c, []
            else:
                for b in c:
                    if b.get("type") == "text":
                        last_user, results = b["text"], []
                    elif b.get("type") == "tool_result":
                        results.append(b)
        if results:
            return Turn(text=self._summarize(results))
        return self._plan(last_user.strip(), names)

    def _call(self, _name, **kw):
        return {"id": new_id("call"), "name": _name, "input": kw}

    def _plan(self, text: str, names: set) -> Turn:
        low = text.lower()
        def T_(t, *calls): return Turn(text=t, tool_calls=list(calls))
        m = re.match(r"^(?:please\s+)?(?:remember|note|save)(?: that)?[:\s]+(.+)$", text, flags=re.I | re.S)
        if m and "memory_remember" in names:
            return T_("Saving that to org memory.", self._call("memory_remember", text=m.group(1).strip()))
        m = re.match(r"^(?:create|add|make|open)\s+(?:a\s+)?task[:\s]+(.+)$", text, flags=re.I | re.S)
        if m and "task_create" in names:
            title, assignee = m.group(1).strip(), ""
            a = re.search(r"\b(?:for|assign(?:ed)? to)\s+@?([A-Za-z][\w.-]*)\s*$", title)
            if a:
                assignee, title = a.group(1), title[:a.start()].strip()
            return T_("Creating the task.", self._call("task_create", title=title, assignee=assignee))
        if re.search(r"\b(list|show|what are|open)\b.*\btasks?\b", low) and "task_list" in names:
            return T_("Pulling the task list.", self._call("task_list", status="open"))
        m = re.match(r"^(?:complete|finish|close|done)\s+(?:task\s+)?(task_\w+)", text, flags=re.I)
        if m and "task_complete" in names:
            return T_("Closing it.", self._call("task_complete", id=m.group(1)))
        m = re.match(r"^((?:every|daily|weekly|on)\s+[^,]+?)\s*[:,]\s+(.+)$", text, flags=re.I | re.S)
        if m and "automation_create" in names:
            prompt = m.group(2).strip()
            name = re.sub(r"[^a-z0-9]+", "-", prompt.lower())[:40].strip("-")
            return T_("Setting up that automation.", self._call("automation_create", name=name, schedule=m.group(1).strip(), prompt=prompt))
        m = re.search(r"(https?://\S+)", text)
        if m and "web_fetch" in names and re.search(r"\b(fetch|read|summari[sz]e|what does|open)\b", low):
            return T_("Fetching that page.", self._call("web_fetch", url=m.group(1).rstrip(").,")))
        m = re.match(r"^(?:run|exec(?:ute)?|sh)[:\s]+(.+)$", text, flags=re.I | re.S)
        if m and "shell_run" in names:
            return T_("Running that command.", self._call("shell_run", command=m.group(1).strip()))
        m = re.match(r"^(?:write|save)\s+file\s+([\w./-]+)\s*[:\s]\s*(.+)$", text, flags=re.I | re.S)
        if m and "file_write" in names:
            return T_("Writing the file.", self._call("file_write", path=m.group(1), content=m.group(2)))
        m = re.match(r"^(?:read|cat|show)\s+(?:file\s+)?((?=[\w./-]*[./])[\w./-]+)\s*$", text, flags=re.I)
        if m and "file_read" in names:
            return T_("Reading the file.", self._call("file_read", path=m.group(1)))
        m = re.search(r"\b(?:issues?|prs?|pull requests?)\b.*?\b(?:in|on|for)\s+([\w.-]+/[\w.-]+)", text, flags=re.I)
        if m and "github_list_issues" in names:
            return T_("Looking at the repo.", self._call("github_list_issues", repo=m.group(1)))
        m = re.match(r"^(?:comment|reply)\s+on\s+([\w.-]+/[\w.-]+)#(\d+)[:\s]+(.+)$", text, flags=re.I | re.S)
        if m and "github_comment" in names:
            return T_("Posting the comment.", self._call("github_comment", repo=m.group(1), number=int(m.group(2)), body=m.group(3).strip()))
        m = re.match(r"^(?:post|say|send)\s+(?:to|in)\s+(#?[\w-]+)[:\s]+(.+)$", text, flags=re.I | re.S)
        if m and "slack_post" in names:
            return T_("Posting to Slack.", self._call("slack_post", channel=m.group(1), text=m.group(2).strip()))
        if re.search(r"\b(what did you do|audit|recent actions|activity)\b", low) and "audit_recent" in names:
            return T_("Here is my recent activity.", self._call("audit_recent", limit=20))
        if len(low.split()) <= 2 and re.match(r"^(hi|hello|hey|yo|help)\b", low):
            return T_("Hi — I'm Tacit. Try `remember that …`, `create task: …`, `what do we know about …`, `daily 09:00: …`, or `run: …`.")
        if "memory_search" in names:
            return T_("Checking what we know.", self._call("memory_search", query=text))
        return T_(f"Local mode (no model): I understood {text!r} but have no tool for it.")

    def _summarize(self, results: list[dict]) -> str:
        lines = []
        for r in results:
            c = r["content"]
            try:
                d = json.loads(c) if isinstance(c, str) else c
            except Exception:
                d = {"raw": c}
            if r.get("is_error"):
                lines.append(f"That failed: {d.get('error') if isinstance(d, dict) else d}"); continue
            if not isinstance(d, dict):
                lines.append(str(d)[:1500]); continue
            if "saved" in d:
                lines.append(f"Remembered: “{d['saved']}”")
            elif "results" in d:
                lines.append("Here's what we know:\n" + "\n".join(f"• {x['text']}" for x in d["results"]) if d["results"] else "Nothing in memory matches that yet.")
            elif "tasks" in d:
                lines.append("Open tasks:\n" + "\n".join(f"• {t['title']}" + (f" (@{t['assignee']})" if t.get("assignee") else "") + f" — `{t['id']}`" for t in d["tasks"]) if d["tasks"] else "No open tasks.")
            elif "automations" in d:
                lines.append("Automations:\n" + "\n".join(f"• {a['name']} — {a['trigger'].get('human','')}" for a in d["automations"]) if d["automations"] else "No automations yet.")
            elif "trigger" in d and "name" in d:
                lines.append(f"Automation **{d['name']}** is live: {d['trigger'].get('human','')}.")
            elif "title" in d and str(d.get("id", "")).startswith("task"):
                lines.append(f"Task created: **{d['title']}** (`{d['id']}`).")
            elif d.get("status") == "done":
                lines.append(f"Done — closed `{d['id']}`.")
            elif "issues" in d:
                lines.append(f"Open issues in {d.get('repo','')}:\n" + "\n".join(f"• #{i['number']} {i['title']}" for i in d["issues"][:20]) if d["issues"] else "No open issues.")
            elif "text" in d and "url" in d:
                lines.append(f"From {d['url']}:\n{d['text'][:1200]}")
            elif "stdout" in d:
                lines.append(f"Exit {d['exit']}\n```\n{(d['stdout'] or d['stderr']).strip()[:3000]}\n```")
            elif "content" in d and "path" in d:
                lines.append(f"```\n{d['content'][:3000]}\n```")
            elif "events" in d:
                lines.append("Recent activity:\n" + "\n".join(f"• {e['actor']} → {e['action']} {e['target']}" for e in d["events"][:20]))
            elif "bytes" in d and "path" in d:
                lines.append(f"Wrote {d['path']} ({d['bytes']} bytes).")
            elif d.get("comment_url") or d.get("html_url") or d.get("posted"):
                lines.append(f"Posted: {d.get('comment_url') or d.get('html_url') or d.get('posted')}")
            else:
                lines.append("```json\n" + json.dumps(d, indent=1)[:2000] + "\n```")
        return "\n\n".join(lines)
