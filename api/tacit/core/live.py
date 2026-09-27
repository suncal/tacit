"""Live updates. Every audited fact is broadcast to open consoles, so the product moves on its own.

Thread-safe by construction: publishers append to per-subscriber queues from whatever thread they're on
(pollers, the scheduler, request handlers) and the SSE endpoint drains them.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any

MAX_BACKLOG = 400

# Only these reach the browser. The audit log records everything; the stream is for things a person
# would want to see happen without refreshing.
INTERESTING = {
    "tool.ask", "approval.approved", "approval.denied", "approval.unread", "run.done", "run.error",
    "draft.created", "draft.scored", "draft.escalated", "lesson.asked", "lesson.answered",
    "playbook.stage", "playbooks.mine", "agent.action", "agent.reworked", "cover.start", "cover.end",
    "backtest.run", "pilot.report", "automation.create",
}


class Live:
    def __init__(self) -> None:
        self._subs: set[queue.Queue] = set()
        self._lock = threading.Lock()
        self.seq = 0

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=MAX_BACKLOG)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    def publish(self, kind: str, data: dict[str, Any] | None = None) -> None:
        with self._lock:
            self.seq += 1
            event = {"seq": self.seq, "kind": kind, "ts": time.time(), **(data or {})}
            dead = []
            for q in self._subs:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._subs.discard(q)

    @property
    def listeners(self) -> int:
        with self._lock:
            return len(self._subs)


live = Live()
