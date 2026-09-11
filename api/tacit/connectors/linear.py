from __future__ import annotations

import logging
import re
import threading
import time

import httpx

from ..core.events import ingest
from ..core.tools.registry import Tool, ToolResult, obj

log = logging.getLogger("tacit.linear")
API = "https://api.linear.app/graphql"


class Linear:
    def __init__(self, app):
        self.app = app
        self.token = app.settings.linear_api_key
        self.handle = "@" + app.settings.handle

    def ok(self) -> bool:
        return bool(self.token)

    def gql(self, query, variables=None):
        r = httpx.post(API, headers={"Authorization": self.token}, json={"query": query, "variables": variables or {}}, timeout=30)
        d = r.json()
        if r.status_code != 200 or d.get("errors"):
            raise RuntimeError(f"Linear: {d.get('errors') or d}")
        return d["data"]

    def register(self, reg):
        def search(ctx, query, limit=15):
            d = self.gql("query($q:String!,$n:Int!){ issueSearch(query:$q, first:$n){ nodes{ identifier title state{name} assignee{name} url } } }", {"q": query, "n": limit})
            return {"issues": [{"id": i["identifier"], "title": i["title"], "state": i["state"]["name"], "assignee": (i.get("assignee") or {}).get("name"), "url": i["url"]} for i in d["issueSearch"]["nodes"]]}
        reg.add(Tool("linear_search", "Search Linear issues.", obj({"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]), search, "read", "linear", "linear"))

        def create(ctx, team_key, title, description=""):
            t = self.gql("query($k:String!){ teams(filter:{key:{eq:$k}}){ nodes{ id } } }", {"k": team_key})["teams"]["nodes"]
            if not t:
                raise RuntimeError(f"no Linear team {team_key}")
            d = self.gql("mutation($i:IssueCreateInput!){ issueCreate(input:$i){ issue{ id identifier url } } }", {"i": {"teamId": t[0]["id"], "title": title, "description": description}})
            iss = d["issueCreate"]["issue"]
            return ToolResult({"id": iss["identifier"], "html_url": iss["url"]}, undo={"tool": "linear_archive_issue", "args": {"issue_uuid": iss["id"]}})
        reg.add(Tool("linear_create_issue", "Create a Linear issue in a team (by key, e.g. ENG).", obj({"team_key": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}}, ["team_key", "title"]), create, "write", "linear", "linear"))

        def archive(ctx, issue_uuid):
            self.gql("mutation($id:String!){ issueArchive(id:$id){ success } }", {"id": issue_uuid})
            return {"archived": issue_uuid}
        reg.add(Tool("linear_archive_issue", "Archive a Linear issue (undo of create).", obj({"issue_uuid": {"type": "string"}}, ["issue_uuid"]), archive, "write", "linear", "linear"))

        def comment(ctx, issue_id, body):
            i = self.gql("query($id:String!){ issue(id:$id){ id } }", {"id": issue_id})["issue"]
            d = self.gql("mutation($i:CommentCreateInput!){ commentCreate(input:$i){ comment{ id url } } }", {"i": {"issueId": i["id"], "body": body}})
            c = d["commentCreate"]["comment"]
            ingest(self.app, "linear", "comment", self.app.settings.handle, body, issue_id, f"linear:{issue_id}", meta={"issue": issue_id}, external_id=f"linear:c:{c['id']}", actor_type="tacit")
            return ToolResult({"comment_url": c["url"]}, undo={"tool": "linear_delete_comment", "args": {"comment_id": c["id"]}})
        reg.add(Tool("linear_comment", "Comment on a Linear issue (identifier like ENG-123).", obj({"issue_id": {"type": "string"}, "body": {"type": "string"}}, ["issue_id", "body"]), comment, "write", "linear", "linear"))

        def delete_comment(ctx, comment_id):
            self.gql("mutation($id:String!){ commentDelete(id:$id){ success } }", {"id": comment_id})
            return {"deleted": comment_id}
        reg.add(Tool("linear_delete_comment", "Delete a comment Tacit posted.", obj({"comment_id": {"type": "string"}}, ["comment_id"]), delete_comment, "write", "linear", "linear"))

    def start(self):
        if not self.ok():
            return None
        t = threading.Thread(target=self._loop, daemon=True, name="tacit-linear")
        t.start()
        return t

    def _loop(self):
        while True:
            try:
                d = self.gql("query{ comments(first:50, orderBy:createdAt){ nodes{ id body createdAt user{name} issue{ identifier title description } } } }")
                for c in d["comments"]["nodes"]:
                    iss = c["issue"]
                    who = (c.get("user") or {}).get("name", "someone")
                    eid = ingest(self.app, "linear", "comment", who, c["body"] or "", iss["identifier"], f"linear:{iss['identifier']}", ts=_ts(c["createdAt"]), meta={"issue": iss["identifier"]}, external_id=f"linear:c:{c['id']}",
                                 actor_type="tacit" if who.lower() == self.app.settings.handle.lower() else "human")
                    if eid and self.handle.lower() in (c["body"] or "").lower():
                        ask = re.sub(re.escape(self.handle), "", c["body"], flags=re.I).strip()
                        self.app.agent.run(f"linear:{iss['identifier']}", f"linear:{who}", ask + f"\n\n(Reply by calling linear_comment on issue_id={iss['identifier']}.)",
                                           context=f"Linear {iss['identifier']} — {iss['title']}\n\n{(iss.get('description') or '')[:4000]}")
            except Exception as e:
                log.warning("poll: %s", e)
            time.sleep(60)


def _ts(iso: str) -> float:
    import datetime as dt
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
