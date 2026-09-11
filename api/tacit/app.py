"""The application object: one process, every subsystem wired, nothing global except the DB engine."""
from __future__ import annotations

import logging

from sqlalchemy import select

from . import models as M
from .core.agent import Agent
from .core.brains import make_brain
from .core.policy import Policy
from .core.scheduler import Bus, Scheduler
from .core.shadow import Shadow
from .core.tools import Registry
from .core.tools.builtin import register_builtins
from .connectors.github import GitHub
from .connectors.linear import Linear
from .connectors.mcp import register_servers
from .connectors.slack import Slack
from .db import session
from .settings import Settings, get_settings

log = logging.getLogger("tacit.app")


class TacitApp:
    def __init__(self, settings: Settings | None = None, brain=None):
        self.settings = settings or get_settings()
        self.registry = Registry()
        self.policy = Policy(self.settings)
        self.brain = brain or make_brain(self.settings)
        self.agent = Agent(self)
        self.bus = Bus(self)
        self.shadow = Shadow(self)
        register_builtins(self.registry, self.settings)
        self.github, self.slack, self.linear = GitHub(self), Slack(self), Linear(self)
        for c in (self.github, self.slack, self.linear):
            if c.ok():
                c.register(self.registry)
        self.mcp = register_servers(self.registry, self.settings)
        self.scheduler: Scheduler | None = None

    def start_background(self):
        self.scheduler = Scheduler(self, self.settings.scheduler_tick)
        self.scheduler.start()
        for c in (self.github, self.slack, self.linear):
            c.start()
        log.info("background started: scheduler + %s", [c.__class__.__name__ for c in (self.github, self.slack, self.linear) if c.ok()])

    def stop_background(self):
        if self.scheduler:
            self.scheduler.stop.set()

    # settings kv
    def get_setting(self, key, default=None):
        with session() as db:
            s = db.get(M.Setting, key)
            return s.value if s else default

    def set_setting(self, key, value):
        with session() as db:
            s = db.get(M.Setting, key)
            if s:
                s.value = value
            else:
                db.add(M.Setting(key=key, value=value))

    def integrations(self) -> list[dict]:
        s = self.settings
        return [
            {"key": "github", "name": "GitHub", "connected": self.github.ok(), "detail": ", ".join(self.github.repos) or "set TACIT_GITHUB_REPOS", "how": "TACIT_GITHUB_TOKEN or `gh auth login`", "mode": "poll + webhook"},
            {"key": "slack", "name": "Slack", "connected": self.slack.ok(), "detail": ", ".join(self.slack.channels) or "set TACIT_SLACK_CHANNELS", "how": "TACIT_SLACK_BOT_TOKEN (xoxb-…)", "mode": "poll + events API"},
            {"key": "linear", "name": "Linear", "connected": self.linear.ok(), "detail": "polls comments", "how": "TACIT_LINEAR_API_KEY", "mode": "poll"},
            {"key": "mcp", "name": "MCP servers", "connected": bool(self.mcp), "detail": ", ".join(x.name for x in self.mcp) or "set TACIT_MCP_SERVERS", "how": "any stdio MCP server", "mode": "stdio"},
            {"key": "webhooks", "name": "Webhooks", "connected": True, "detail": "POST /api/v1/webhooks/<name>", "how": "built in", "mode": "push"},
            {"key": "events", "name": "Event API", "connected": True, "detail": "POST /api/v1/events", "how": "built in — feed any system", "mode": "push"},
        ]

    def brain_info(self) -> dict:
        return {"provider": self.brain.name, "model": getattr(self.brain, "model", "—"), "llm": self.brain.is_llm}
