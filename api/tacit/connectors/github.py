from __future__ import annotations

import base64
import logging
import re
import threading
import time

import httpx

from ..core.events import ingest
from ..core.tools.registry import Tool, ToolResult, obj

log = logging.getLogger("tacit.github")
API = "https://api.github.com"


class GitHub:
    def __init__(self, app):
        self.app = app
        s = app.settings
        self.token = s.github_token or _gh_cli_token()
        self.repos = s.list(s.github_repos)
        self.handle = "@" + s.handle

    def ok(self) -> bool:
        return bool(self.token)

    def _h(self):
        return {"Authorization": f"Bearer {self.token}", "X-GitHub-Api-Version": "2022-11-28", "Accept": "application/vnd.github+json", "User-Agent": "tacit/0.1"}

    def get(self, path, **params):
        r = httpx.get(API + path, headers=self._h(), params={k: v for k, v in params.items() if v is not None}, timeout=30)
        return r.status_code, (r.json() if r.content else {})

    def post(self, path, body):
        r = httpx.post(API + path, headers=self._h(), json=body, timeout=30)
        return r.status_code, (r.json() if r.content else {})

    def delete(self, path):
        r = httpx.delete(API + path, headers=self._h(), timeout=30)
        return r.status_code

    def patch(self, path, body):
        r = httpx.patch(API + path, headers=self._h(), json=body, timeout=30)
        return r.status_code, (r.json() if r.content else {})

    # ------------------------------------------------------------------ tools
    def register(self, reg):
        repo = {"repo": {"type": "string", "description": "owner/name"}}

        def list_issues(ctx, repo, state="open", kind="issues"):
            st, data = self.get(f"/repos/{repo}/issues", state=state, per_page=30)
            if st != 200:
                raise RuntimeError(f"GitHub {st}: {data.get('message', data)}")
            items = [i for i in data if (("pull_request" in i) == (kind == "prs"))]
            return {"repo": repo, "issues": [{"number": i["number"], "title": i["title"], "author": i["user"]["login"], "labels": [l["name"] for l in i.get("labels", [])], "url": i["html_url"]} for i in items]}
        reg.add(Tool("github_list_issues", "List open issues (kind=issues) or pull requests (kind=prs) in a repo.", obj(dict(repo, state={"type": "string"}, kind={"type": "string"}), ["repo"]), list_issues, "read", "github", "github"))

        def get_issue(ctx, repo, number):
            st, i = self.get(f"/repos/{repo}/issues/{number}")
            if st != 200:
                raise RuntimeError(f"GitHub {st}: {i.get('message', i)}")
            st2, comments = self.get(f"/repos/{repo}/issues/{number}/comments", per_page=30)
            return {"number": i["number"], "title": i["title"], "body": (i.get("body") or "")[:8000], "state": i["state"], "author": i["user"]["login"], "url": i["html_url"],
                    "comments": [{"author": c["user"]["login"], "body": (c.get("body") or "")[:2000]} for c in (comments if st2 == 200 else [])]}
        reg.add(Tool("github_get_issue", "Read an issue or PR with its comments.", obj(dict(repo, number={"type": "integer"}), ["repo", "number"]), get_issue, "read", "github", "github"))

        def get_file(ctx, repo, path, ref=None):
            st, d = self.get(f"/repos/{repo}/contents/{path}", ref=ref)
            if st != 200:
                raise RuntimeError(f"GitHub {st}: {d.get('message', d)}")
            content = base64.b64decode(d.get("content", "")).decode("utf-8", "replace") if d.get("encoding") == "base64" else ""
            return {"path": path, "content": content[:60000], "sha": d.get("sha")}
        reg.add(Tool("github_get_file", "Read a file from a repo.", obj(dict(repo, path={"type": "string"}, ref={"type": "string"}), ["repo", "path"]), get_file, "read", "github", "github"))

        def pr_diff(ctx, repo, number):
            st, files = self.get(f"/repos/{repo}/pulls/{number}/files", per_page=50)
            if st != 200:
                raise RuntimeError(f"GitHub {st}: {files.get('message', files)}")
            return {"files": [{"filename": f["filename"], "status": f["status"], "additions": f["additions"], "deletions": f["deletions"], "patch": (f.get("patch") or "")[:6000]} for f in files]}
        reg.add(Tool("github_pr_diff", "Get the changed files + patches of a pull request.", obj(dict(repo, number={"type": "integer"}), ["repo", "number"]), pr_diff, "read", "github", "github"))

        def comment(ctx, repo, number, body):
            st, d = self.post(f"/repos/{repo}/issues/{number}/comments", {"body": body})
            if st not in (200, 201):
                raise RuntimeError(f"GitHub {st}: {d.get('message', d)}")
            ingest(self.app, "github", "comment", self.app.settings.handle, body, repo, f"github:{repo}#{number}", meta={"repo": repo, "number": number}, external_id=f"gh:c:{d['id']}", actor_type="tacit")
            return ToolResult({"comment_url": d["html_url"], "comment_id": d["id"]}, undo={"tool": "github_delete_comment", "args": {"repo": repo, "comment_id": d["id"]}})
        reg.add(Tool("github_comment", "Post a comment on an issue or PR.", obj(dict(repo, number={"type": "integer"}, body={"type": "string"}), ["repo", "number", "body"]), comment, "write", "github", "github"))

        def delete_comment(ctx, repo, comment_id):
            st = self.delete(f"/repos/{repo}/issues/comments/{comment_id}")
            if st not in (204, 404):
                raise RuntimeError(f"GitHub {st} deleting comment")
            return {"deleted": comment_id}
        reg.add(Tool("github_delete_comment", "Delete a comment Tacit posted.", obj(dict(repo, comment_id={"type": "integer"}), ["repo", "comment_id"]), delete_comment, "write", "github", "github"))

        def create_issue(ctx, repo, title, body="", labels=None):
            st, d = self.post(f"/repos/{repo}/issues", {"title": title, "body": body, "labels": labels or []})
            if st not in (200, 201):
                raise RuntimeError(f"GitHub {st}: {d.get('message', d)}")
            return ToolResult({"number": d["number"], "html_url": d["html_url"]}, undo={"tool": "github_close_issue", "args": {"repo": repo, "number": d["number"]}})
        reg.add(Tool("github_create_issue", "Open a new issue.", obj(dict(repo, title={"type": "string"}, body={"type": "string"}, labels={"type": "array", "items": {"type": "string"}}), ["repo", "title"]), create_issue, "write", "github", "github"))

        def close_issue(ctx, repo, number):
            st, d = self.patch(f"/repos/{repo}/issues/{number}", {"state": "closed"})
            if st != 200:
                raise RuntimeError(f"GitHub {st}: {d.get('message', d)}")
            return ToolResult({"number": number, "state": "closed"}, undo={"tool": "github_reopen_issue", "args": {"repo": repo, "number": number}})
        reg.add(Tool("github_close_issue", "Close an issue or PR.", obj(dict(repo, number={"type": "integer"}), ["repo", "number"]), close_issue, "write", "github", "github"))

        def reopen_issue(ctx, repo, number):
            st, d = self.patch(f"/repos/{repo}/issues/{number}", {"state": "open"})
            if st != 200:
                raise RuntimeError(f"GitHub {st}: {d.get('message', d)}")
            return ToolResult({"number": number, "state": "open"}, undo={"tool": "github_close_issue", "args": {"repo": repo, "number": number}})
        reg.add(Tool("github_reopen_issue", "Reopen an issue or PR.", obj(dict(repo, number={"type": "integer"}), ["repo", "number"]), reopen_issue, "write", "github", "github"))

        def create_pr(ctx, repo, title, head, base="main", body=""):
            st, d = self.post(f"/repos/{repo}/pulls", {"title": title, "head": head, "base": base, "body": body})
            if st not in (200, 201):
                raise RuntimeError(f"GitHub {st}: {d.get('message', d)}")
            return ToolResult({"number": d["number"], "html_url": d["html_url"]}, undo={"tool": "github_close_issue", "args": {"repo": repo, "number": d["number"]}})
        reg.add(Tool("github_create_pr", "Open a pull request from an existing branch.", obj(dict(repo, title={"type": "string"}, head={"type": "string"}, base={"type": "string"}, body={"type": "string"}), ["repo", "title", "head"]), create_pr, "write", "github", "github"))

    # ------------------------------------------------------------------ poller: ingest + mentions
    def start(self):
        if not self.ok() or not self.repos:
            return None
        t = threading.Thread(target=self._loop, daemon=True, name="tacit-github")
        t.start()
        return t

    def _loop(self):
        s = self.app.settings
        since = self.app.get_setting("github.since") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        while True:
            try:
                newest = since
                for repo in self.repos:
                    st, comments = self.get(f"/repos/{repo}/issues/comments", since=since, per_page=50, sort="created", direction="asc")
                    for c in (comments if st == 200 else []):
                        newest = max(newest, c["created_at"])
                        number = int(c["issue_url"].rsplit("/", 1)[1])
                        author = c["user"]["login"]
                        eid = ingest(self.app, "github", "comment", author, c.get("body") or "", repo, f"github:{repo}#{number}",
                                     ts=_ts(c["created_at"]), meta={"repo": repo, "number": number}, external_id=f"gh:c:{c['id']}",
                                     actor_type="tacit" if author.lower() == s.handle.lower() or author.endswith("[bot]") else "human")
                        if eid and self.handle.lower() in (c.get("body") or "").lower():
                            self._mention(repo, number, author, c.get("body") or "")
                    st, issues = self.get(f"/repos/{repo}/issues", since=since, per_page=30, sort="created", direction="asc")
                    for i in (issues if st == 200 else []):
                        if i["created_at"] < since:
                            continue
                        newest = max(newest, i["created_at"])
                        kind = "pr.opened" if "pull_request" in i else "issue.opened"
                        eid = ingest(self.app, "github", kind, i["user"]["login"], f"{i['title']}\n\n{(i.get('body') or '')[:2000]}", repo, f"github:{repo}#{i['number']}",
                                     ts=_ts(i["created_at"]), meta={"repo": repo, "number": i["number"], "url": i["html_url"]}, external_id=f"gh:i:{i['id']}")
                        if eid:
                            self.app.bus.emit(f"github.{kind}", {"repo": repo, "number": i["number"], "title": i["title"], "url": i["html_url"]})
                            if self.handle.lower() in ((i.get("body") or "") + i["title"]).lower():
                                self._mention(repo, i["number"], i["user"]["login"], i.get("body") or "")
                since = newest
                self.app.set_setting("github.since", since)
            except Exception as e:
                log.warning("poll error: %s", e)
            time.sleep(60)

    def _mention(self, repo, number, author, body):
        ask = re.sub(re.escape(self.handle), "", body, flags=re.I).strip()
        st, issue = self.get(f"/repos/{repo}/issues/{number}")
        ctx = f"GitHub {repo}#{number} — {issue.get('title', '')}\n\n{(issue.get('body') or '')[:4000]}" if st == 200 else ""
        self.app.agent.run(f"github:{repo}#{number}", f"github:{author}", ask + f"\n\n(Reply by calling github_comment on repo={repo} number={number}.)", context=ctx)


def _ts(iso: str) -> float:
    import datetime as dt
    return dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()


def _gh_cli_token() -> str:
    import shutil
    import subprocess
    if not shutil.which("gh"):
        return ""
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""
