from __future__ import annotations

import logging
import re
import threading
import time

import httpx

from ..core.events import ingest
from ..core.tools.registry import Tool, ToolResult, obj

log = logging.getLogger("tacit.slack")
API = "https://slack.com/api"


class Slack:
    def __init__(self, app):
        self.app = app
        s = app.settings
        self.token = s.slack_bot_token
        self.channels = s.list(s.slack_channels)
        self.bot_id = None

    def ok(self) -> bool:
        return bool(self.token)

    def call(self, method, **params):
        r = httpx.post(f"{API}/{method}", headers={"Authorization": f"Bearer {self.token}"}, json={k: v for k, v in params.items() if v is not None}, timeout=30)
        d = r.json()
        if not d.get("ok"):
            raise RuntimeError(f"Slack {method}: {d.get('error', d)}")
        return d

    def register(self, reg):
        def post(ctx, channel, text, thread_ts=None):
            d = self.call("chat.postMessage", channel=channel, text=text, thread_ts=thread_ts)
            ingest(self.app, "slack", "message", self.app.settings.handle, text, channel, f"slack:{channel}:{thread_ts or d.get('ts')}", meta={"channel": channel, "ts": d.get("ts")}, external_id=f"slack:{channel}:{d.get('ts')}", actor_type="tacit")
            return ToolResult({"posted": f"{d.get('channel')}@{d.get('ts')}"}, undo={"tool": "slack_delete", "args": {"channel": d.get("channel"), "ts": d.get("ts")}})
        reg.add(Tool("slack_post", "Post a message to a Slack channel (or thread).", obj({"channel": {"type": "string"}, "text": {"type": "string"}, "thread_ts": {"type": "string"}}, ["channel", "text"]), post, "write", "slack", "slack"))

        def delete(ctx, channel, ts):
            self.call("chat.delete", channel=channel, ts=ts)
            return {"deleted": f"{channel}@{ts}"}
        reg.add(Tool("slack_delete", "Delete a message Tacit posted.", obj({"channel": {"type": "string"}, "ts": {"type": "string"}}, ["channel", "ts"]), delete, "write", "slack", "slack"))

        def history(ctx, channel, limit=30):
            d = self.call("conversations.history", channel=channel, limit=limit)
            return {"messages": [{"user": m.get("user"), "text": m.get("text"), "ts": m.get("ts")} for m in d.get("messages", [])]}
        reg.add(Tool("slack_history", "Read recent messages in a channel.", obj({"channel": {"type": "string"}, "limit": {"type": "integer"}}, ["channel"]), history, "read", "slack", "slack"))

    def start(self):
        if not self.ok() or not self.channels:
            return None
        t = threading.Thread(target=self._loop, daemon=True, name="tacit-slack")
        t.start()
        return t

    def _loop(self):
        try:
            self.bot_id = self.call("auth.test").get("user_id")
        except Exception as e:
            log.warning("auth failed: %s", e)
            return
        last = self.app.get_setting("slack.last") or {}
        while True:
            for ch in self.channels:
                try:
                    d = self.call("conversations.history", channel=ch, oldest=last.get(ch, str(time.time() - 3600)), limit=100)
                    for m in sorted(d.get("messages", []), key=lambda m: float(m["ts"])):
                        last[ch] = m["ts"]
                        user = m.get("user") or m.get("bot_id") or "unknown"
                        is_bot = user == self.bot_id or bool(m.get("bot_id"))
                        text = m.get("text") or ""
                        eid = ingest(self.app, "slack", "message", user, text, ch, f"slack:{ch}:{m.get('thread_ts') or m['ts']}", ts=float(m["ts"]),
                                     meta={"channel": ch, "ts": m["ts"], "thread_ts": m.get("thread_ts")}, external_id=f"slack:{ch}:{m['ts']}", actor_type="tacit" if is_bot else "human")
                        if eid and not is_bot:
                            self.app.bus.emit("slack.message", {"channel": ch, "user": user, "text": text[:2000]})
                            if self.bot_id and f"<@{self.bot_id}>" in text:
                                self.handle_mention(ch, user, text, m.get("thread_ts") or m["ts"])
                except Exception as e:
                    log.warning("poll %s: %s", ch, e)
            self.app.set_setting("slack.last", last)
            time.sleep(20)

    def handle_mention(self, channel, user, text, thread_ts):
        ask = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
        r = self.app.agent.run(f"slack:{channel}", f"slack:{user}", ask)
        reply = r["output"] or "Working on it — this needs an approval in the Tacit console."
        try:
            self.call("chat.postMessage", channel=channel, text=reply, thread_ts=thread_ts)
        except Exception as e:
            log.warning("reply failed: %s", e)
