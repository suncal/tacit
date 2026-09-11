"""Change previews: what will happen if this action runs. Shown before approval, stored with the action."""
from __future__ import annotations


def preview(tool, ctx, args: dict) -> dict:
    if tool.previewer:
        try:
            return tool.previewer(ctx, **args)
        except Exception as e:
            return {"system": tool.system, "kind": "unknown", "summary": f"{tool.name} (preview failed: {e})"}
    if tool.risk == "read":
        return {"system": tool.system, "kind": "read", "summary": f"{tool.name}"}
    text = args.get("body") or args.get("text") or args.get("content") or args.get("title") or ""
    target = args.get("repo") or args.get("channel") or args.get("issue_id") or args.get("path") or args.get("team_key") or ""
    number = args.get("number")
    where = f"{target}#{number}" if number else target
    if tool.name == "note":
        return {"system": "notes", "kind": "create", "summary": f"reply in {target or 'thread'} — target system not connected, recorded as a note", "text": text[:4000], "target": target}
    verb = {"github_comment": "comment on", "github_create_issue": "open issue in", "github_create_pr": "open PR in",
            "slack_post": "post in", "linear_comment": "comment on", "linear_create_issue": "create issue in",
            "task_create": "create task", "memory_remember": "remember", "automation_create": "create automation",
            "file_write": "write", "note": "note"}.get(tool.name, tool.name)
    return {"system": tool.system, "kind": "create", "summary": f"{verb} {where}".strip(), "text": text[:4000], "target": where}
