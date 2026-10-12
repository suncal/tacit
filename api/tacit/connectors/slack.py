"""Slack: learn from a workspace's conversations, reply when summoned, and undo what it posted.

Three ways in, chosen by what is configured:
  * Socket Mode (TACIT_SLACK_APP_TOKEN, xapp-…): a websocket Slack pushes events into. No public URL,
    no rate-limited polling. This is the right mode for a laptop demo and for most self-hosted installs.
  * Polling (bot token only): conversations.history every 20 s. Slack limits apps created after May 2025
    to 1 request/minute on that method, so polling is a fallback, not the default.
  * Export import (`tacit import-slack-export <zip or dir>`): a workspace export is the only cheap way
    to get *history* into Tacit, and history is what mining needs. Zero API calls.
Every message is ingested with thread_key slack:<channel>:<thread root ts>, so a reply in a thread is
paired with the message it answers.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import threading
import time
import zipfile
from typing import Optional

import httpx

from ..core.events import ingest
from ..core.tools.registry import Tool, ToolResult, obj

log = logging.getLogger("tacit.slack")
API = "https://slack.com/api"
SKIP_SUBTYPES = {"channel_join", "channel_leave", "channel_topic", "channel_purpose", "bot_message", "message_changed",
                 "message_deleted", "tombstone", "joiner_notification", "channel_name", "pinned_item"}


class Slack:
    def __init__(self, app):
        self.app = app
        s = app.settings
        self.token = s.slack_bot_token
        self.app_token = s.slack_app_token
        self.channels = s.list(s.slack_channels)
        self.bot_id: Optional[str] = None
        self.names: dict[str, str] = {}          # user id → display name, filled lazily
        self._stop = threading.Event()

    def ok(self) -> bool:
        return bool(self.token)

    @property
    def mode(self) -> str:
        return "socket" if self.app_token else "poll"

    # ------------------------------------------------------------------ api
    def call(self, method, _token=None, **params):
        r = httpx.post(f"{API}/{method}", headers={"Authorization": f"Bearer {_token or self.token}"},
                       json={k: v for k, v in params.items() if v is not None}, timeout=30)
        d = r.json()
        if not d.get("ok"):
            raise RuntimeError(f"Slack {method}: {d.get('error', d)}")
        return d

    def name(self, user_id: str) -> str:
        """Human-readable actor for the console; falls back to the id. Cached for the process."""
        if not user_id or user_id in self.names:
            return self.names.get(user_id, user_id)
        try:
            u = self.call("users.info", user=user_id)["user"]
            self.names[user_id] = u.get("profile", {}).get("display_name") or u.get("real_name") or u.get("name") or user_id
        except Exception:
            self.names[user_id] = user_id
        return self.names[user_id]

    # ------------------------------------------------------------------ tools
    def register(self, reg):
        def post(ctx, channel, text, thread_ts=None):
            d = self.call("chat.postMessage", channel=channel, text=text, thread_ts=thread_ts)
            ingest(self.app, "slack", "message", self.app.settings.handle, text, channel, f"slack:{channel}:{thread_ts or d.get('ts')}",
                   meta={"channel": channel, "ts": d.get("ts"), "thread_ts": thread_ts}, external_id=f"slack:{channel}:{d.get('ts')}", actor_type="tacit")
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

    # ------------------------------------------------------------------ ingest one message
    def ingest_message(self, channel: str, m: dict, *, live: bool = True) -> Optional[str]:
        """One Slack message dict (API or export shape) → one event. Returns the event id, None if skipped/duplicate."""
        if m.get("type", "message") != "message" or m.get("subtype") in SKIP_SUBTYPES:
            return None
        ts = m.get("ts")
        if not ts:
            return None
        user = m.get("user") or m.get("bot_id") or "unknown"
        is_bot = bool(m.get("bot_id")) or (self.bot_id is not None and user == self.bot_id)
        text = m.get("text") or ""
        actor = (m.get("user_profile") or {}).get("real_name") or (self.names.get(user) if not live else self.name(user)) or user
        if is_bot:
            actor = user
        thread_root = m.get("thread_ts") or ts
        return ingest(self.app, "slack", "message", actor, text, channel, f"slack:{channel}:{thread_root}", ts=float(ts),
                      meta={"channel": channel, "ts": ts, "thread_ts": m.get("thread_ts"), "user_id": user},
                      external_id=f"slack:{channel}:{ts}", actor_type="tacit" if is_bot else "human", shadow=live)

    # ------------------------------------------------------------------ live
    def start(self):
        if not self.ok():
            return None
        if self.mode == "poll" and not self.channels:
            return None
        t = threading.Thread(target=self._socket_loop if self.mode == "socket" else self._poll_loop, daemon=True, name="tacit-slack")
        t.start()
        return t

    def _auth(self) -> bool:
        try:
            self.bot_id = self.call("auth.test").get("user_id")
            return True
        except Exception as e:
            log.warning("auth failed: %s", e)
            return False

    def _socket_loop(self):
        """Socket Mode: open a websocket, ack every envelope, hand events to handle_event. Reconnects forever."""
        from websockets.sync.client import connect
        if not self._auth():
            return
        while not self._stop.is_set():
            try:
                url = self.call("apps.connections.open", _token=self.app_token)["url"]
                with connect(url, max_size=2**22) as ws:
                    log.info("socket mode connected")
                    for raw in ws:
                        env = json.loads(raw)
                        if env.get("envelope_id"):
                            ws.send(json.dumps({"envelope_id": env["envelope_id"]}))
                        kind = env.get("type")
                        if kind == "disconnect":
                            break
                        if kind == "events_api":
                            try:
                                self.handle_event((env.get("payload") or {}).get("event") or {})
                            except Exception as e:
                                log.exception("event failed: %s", e)
                        if self._stop.is_set():
                            break
            except Exception as e:
                log.warning("socket mode: %s (reconnecting in 5s)", e)
                time.sleep(5)

    def handle_event(self, ev: dict) -> Optional[str]:
        """Events API payloads. `message` is ingested; `app_mention` summons the agent. Returns the event id if ingested."""
        if ev.get("type") == "app_mention":
            self.handle_mention(ev.get("channel", ""), ev.get("user", ""), ev.get("text") or "", ev.get("thread_ts") or ev.get("ts"))
            return None
        if ev.get("type") != "message":
            return None
        ch = ev.get("channel", "")
        if self.channels and ch not in self.channels:
            return None
        eid = self.ingest_message(ch, ev)
        if eid and not ev.get("bot_id"):
            self.app.bus.emit("slack.message", {"channel": ch, "user": ev.get("user"), "text": (ev.get("text") or "")[:2000]})
        return eid

    def _poll_loop(self):
        if not self._auth():
            return
        last = self.app.get_setting("slack.last") or {}
        while not self._stop.is_set():
            for ch in self.channels:
                try:
                    d = self.call("conversations.history", channel=ch, oldest=last.get(ch, str(time.time() - 3600)), limit=100)
                    for m in sorted(d.get("messages", []), key=lambda m: float(m["ts"])):
                        last[ch] = m["ts"]
                        eid = self.ingest_message(ch, m)
                        if m.get("reply_count"):                       # history never includes thread replies
                            for r in self.call("conversations.replies", channel=ch, ts=m["ts"], limit=100).get("messages", [])[1:]:
                                self.ingest_message(ch, r)
                        if eid and not m.get("bot_id"):
                            text = m.get("text") or ""
                            self.app.bus.emit("slack.message", {"channel": ch, "user": m.get("user"), "text": text[:2000]})
                            if self.bot_id and f"<@{self.bot_id}>" in text:
                                self.handle_mention(ch, m.get("user", ""), text, m.get("thread_ts") or m["ts"])
                except Exception as e:
                    log.warning("poll %s: %s", ch, e)
            self.app.set_setting("slack.last", last)
            self._stop.wait(20)

    def handle_mention(self, channel, user, text, thread_ts):
        ask = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
        r = self.app.agent.run(f"slack:{channel}", f"slack:{user}", ask)
        reply = r["output"] or "Working on it — this needs an approval in the Tacit console."
        try:
            self.call("chat.postMessage", channel=channel, text=reply, thread_ts=thread_ts)
        except Exception as e:
            log.warning("reply failed: %s", e)

    # ------------------------------------------------------------------ export import
    def import_export(self, path: str, channels: Optional[list[str]] = None, progress=None) -> dict:
        """Load a Slack workspace export (zip or unpacked dir): users.json, channels.json, <channel>/<date>.json.
        Needs no token. Channel directories are named by channel *name*; events use that name as the target."""
        files = _ExportFiles(path)
        for u in files.json("users.json") or []:
            self.names[u["id"]] = (u.get("profile") or {}).get("display_name") or u.get("real_name") or u.get("name") or u["id"]
        chans = {c["name"]: c for c in (files.json("channels.json") or [])}
        n_msgs = n_files = skipped = 0
        for day_file in sorted(files.day_files()):
            ch = day_file.split("/", 1)[0]
            if channels and ch not in channels:
                continue
            for m in files.json(day_file) or []:
                if m.get("user") and m["user"] not in self.names and (m.get("user_profile") or {}).get("real_name"):
                    self.names[m["user"]] = m["user_profile"]["real_name"]
                if self.ingest_message(ch, m, live=False):
                    n_msgs += 1
                else:
                    skipped += 1
            n_files += 1
            if progress and n_files % 50 == 0:
                progress(f"{n_files} day-files, {n_msgs} messages")
        return {"path": path, "channels": sorted({f.split('/', 1)[0] for f in files.day_files()} & set(channels or chans or {f.split('/', 1)[0] for f in files.day_files()})),
                "day_files": n_files, "messages": n_msgs, "skipped": skipped, "users": len(self.names)}


class _ExportFiles:
    """Uniform view over a zip or a directory."""
    def __init__(self, path: str):
        self.path = path
        self.zip = zipfile.ZipFile(path) if os.path.isfile(path) else None
        if self.zip:
            names = self.zip.namelist()
            root = os.path.commonprefix([n for n in names if "/" in n]).split("/")[0] if names and all("/" in n for n in names) else ""
            self.prefix = root + "/" if root and all(n.startswith(root + "/") for n in names) else ""
            self.members = [n[len(self.prefix):] for n in names]
        else:
            self.members = [os.path.relpath(os.path.join(dp, f), path) for dp, _, fs in os.walk(path) for f in fs]

    def json(self, rel: str):
        try:
            if self.zip:
                with self.zip.open(self.prefix + rel) as f:
                    return json.load(io.TextIOWrapper(f, encoding="utf-8"))
            with open(os.path.join(self.path, rel), encoding="utf-8") as f:
                return json.load(f)
        except (KeyError, FileNotFoundError):
            return None

    def day_files(self) -> list[str]:
        return [m for m in self.members if m.count("/") == 1 and re.search(r"/\d{4}-\d{2}-\d{2}\.json$", m)]
