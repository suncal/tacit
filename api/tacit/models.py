"""Domain model. Every table is inspectable with plain SQL — that's a feature."""
from __future__ import annotations

import time
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> float:
    return time.time()


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="admin")          # admin | member
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    last_used_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Event(Base):
    """One thing that happened in a connected system. Human or Tacit. The raw material for everything."""
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    system: Mapped[str] = mapped_column(String(30), index=True)             # github | slack | linear | email | webhook
    kind: Mapped[str] = mapped_column(String(40), index=True)               # message | comment | issue.opened | review | ...
    actor: Mapped[str] = mapped_column(String(120), index=True)             # human handle or "tacit"
    actor_type: Mapped[str] = mapped_column(String(10), default="human")    # human | tacit
    target: Mapped[str] = mapped_column(String(200), default="")            # channel / repo / team
    thread_key: Mapped[str] = mapped_column(String(200), index=True)        # conversation identity across events
    text: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ts: Mapped[float] = mapped_column(Float, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(200), unique=True, nullable=True)

    __table_args__ = (Index("ix_events_thread_ts", "thread_key", "ts"),)


class Playbook(Base):
    """A recurring, delegable pattern mined from events. Lives through stages: shadow → propose → auto."""
    __tablename__ = "playbooks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    system: Mapped[str] = mapped_column(String(30))
    actor: Mapped[str] = mapped_column(String(120))                         # the human whose job this is
    stage: Mapped[str] = mapped_column(String(20), default="candidate", index=True)  # candidate | shadow | propose | auto | retired
    trigger: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)     # {kind, keywords, target, cadence}
    response: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)    # {kind, target, template, tool}
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    consistency: Mapped[float] = mapped_column(Float, default=0.0)          # mean intra-cluster similarity
    median_latency_s: Mapped[float] = mapped_column(Float, default=0.0)     # how fast the human usually responds
    examples: Mapped[list[Any]] = mapped_column(JSON, default=list)         # [{trigger, response, ts}]
    drafts_total: Mapped[int] = mapped_column(Integer, default=0)
    drafts_scored: Mapped[int] = mapped_column(Integer, default=0)
    drafts_hit: Mapped[int] = mapped_column(Integer, default=0)             # score >= threshold
    score_sum: Mapped[float] = mapped_column(Float, default=0.0)
    approvals: Mapped[int] = mapped_column(Integer, default=0)
    rejections: Mapped[int] = mapped_column(Integer, default=0)
    executions: Mapped[int] = mapped_column(Integer, default=0)
    undos: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    stage_changed_at: Mapped[float] = mapped_column(Float, default=now)
    stage_history: Mapped[list[Any]] = mapped_column(JSON, default=list)


class Draft(Base):
    """What Tacit would have done (shadow) or proposed/did (propose/auto) in response to a trigger event."""
    __tablename__ = "drafts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    playbook_id: Mapped[str] = mapped_column(String(40), ForeignKey("playbooks.id", ondelete="CASCADE"), index=True)
    trigger_event_id: Mapped[str] = mapped_column(String(40), ForeignKey("events.id", ondelete="CASCADE"))
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)     # {text, target, tool, args}
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending | scored | expired | proposed | executed | rejected
    mode: Mapped[str] = mapped_column(String(10), default="live")           # live | backtest
    actual_event_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    human_grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # +1 / -1 override
    run_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now, index=True)
    resolved_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    playbook: Mapped[Playbook] = relationship()
    trigger_event: Mapped[Event] = relationship(foreign_keys=[trigger_event_id])


class Lesson(Base):
    """Tacit missed; the owner explains the rule. Lessons condition every future draft of the playbook."""
    __tablename__ = "lessons"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    playbook_id: Mapped[str] = mapped_column(String(40), ForeignKey("playbooks.id", ondelete="CASCADE"), index=True)
    draft_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    trigger_text: Mapped[str] = mapped_column(Text, default="")
    draft_text: Mapped[str] = mapped_column(Text, default="")
    actual_text: Mapped[str] = mapped_column(Text, default="")
    question: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # the rule, in the owner's words
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open | answered | dismissed
    created_at: Mapped[float] = mapped_column(Float, default=now)
    answered_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    answered_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)


class Cover(Base):
    """Someone is out. Their proven jobs are temporarily promoted so the team isn't stuck."""
    __tablename__ = "covers"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), index=True)
    backup: Mapped[str] = mapped_column(String(120), default="")
    until: Mapped[float] = mapped_column(Float)
    promoted: Mapped[list[Any]] = mapped_column(JSON, default=list)       # [{playbook_id, from}] to restore
    status: Mapped[str] = mapped_column(String(20), default="active")      # active | ended
    created_at: Mapped[float] = mapped_column(Float, default=now)
    created_by: Mapped[str] = mapped_column(String(120), default="")


class Run(Base):
    """One invocation of the agent. Its writes form a transaction that can be undone as a unit."""
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    channel: Mapped[str] = mapped_column(String(120))
    principal: Mapped[str] = mapped_column(String(120), index=True)
    input: Mapped[str] = mapped_column(Text)
    output: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)  # running | waiting | done | error
    steps: Mapped[list[Any]] = mapped_column(JSON, default=list)
    messages: Mapped[list[Any]] = mapped_column(JSON, default=list)
    tx_status: Mapped[str] = mapped_column(String(20), default="open")     # open | committed | undone | partial
    playbook_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    draft_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    replay_of: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)      # tokens, usd, model
    created_at: Mapped[float] = mapped_column(Float, default=now, index=True)
    finished_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    actions: Mapped[list[Action]] = relationship(back_populates="run", cascade="all, delete-orphan", order_by="Action.ts")


class Action(Base):
    """A write that happened, with the recipe to reverse it."""
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40), ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    tool: Mapped[str] = mapped_column(String(80))
    args: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    undo: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)   # {tool, args} or null if irreversible
    status: Mapped[str] = mapped_column(String(20), default="done")         # done | undone | undo_failed
    preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ts: Mapped[float] = mapped_column(Float, default=now)
    undone_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    run: Mapped[Run] = relationship(back_populates="actions")


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40), ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    call_id: Mapped[str] = mapped_column(String(80))
    tool: Mapped[str] = mapped_column(String(80))
    args: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    principal: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(String(300), default="")
    playbook_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending | approved | denied
    created_at: Mapped[float] = mapped_column(Float, default=now)
    decided_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="fact")
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now, index=True)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    assignee: Mapped[str] = mapped_column(String(120), default="")
    source: Mapped[str] = mapped_column(String(120), default="")
    due: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    done_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Automation(Base):
    __tablename__ = "automations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    trigger: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prompt: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    next_run_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Meeting(Base):
    __tablename__ = "meetings"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    transcript: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    action_items: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    principal: Mapped[str] = mapped_column(String(120), default="*")
    tool: Mapped[str] = mapped_column(String(80), default="*")
    decision: Mapped[str] = mapped_column(String(10))                       # allow | ask | deny
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Budget(Base):
    """Hard caps. scope matches principals (fnmatch): 'automation:*', 'playbook:*', 'slack:*'."""
    __tablename__ = "budgets"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    scope: Mapped[str] = mapped_column(String(120))
    max_writes_per_hour: Mapped[int] = mapped_column(Integer, default=20)
    max_usd_per_day: Mapped[float] = mapped_column(Float, default=5.0)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)


class AuditEvent(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, default=now, index=True)
    actor: Mapped[str] = mapped_column(String(120), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Seen(Base):
    __tablename__ = "seen"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    ts: Mapped[float] = mapped_column(Float, default=now)
