"""Uses the `claude` CLI you already pay for. JSON protocol over -p; no API key needed."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from .base import Brain, BrainError, Turn, DRAFT_SYSTEM, draft_prompt, parse_json
from ..ids import new_id

_PROTO = """You are operating inside Tacit, a tool-using agent harness. Answer with ONE JSON object and nothing else:
{"reply": "<what to say, markdown ok>", "tool_calls": [{"name": "<tool>", "input": {...}}]}
Tools (name, description, input schema):
%s
Return tool_calls when you need results first; return an empty tool_calls list with the final reply when done."""


def _flatten(messages: list[dict]) -> str:
    out = []
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            out.append(f"{m['role'].upper()}: {c}"); continue
        for b in c:
            t = b.get("type")
            if t == "text":
                out.append(f"{m['role'].upper()}: {b['text']}")
            elif t == "tool_use":
                out.append(f"ASSISTANT called {b['name']}({json.dumps(b['input'])})")
            elif t == "tool_result":
                out.append(f"TOOL RESULT: {b['content'] if isinstance(b['content'], str) else json.dumps(b['content'])}")
    return "\n".join(out)


class ClaudeCLIBrain(Brain):
    name = "claude-cli"

    def __init__(self, model: str = "opus"):
        if not shutil.which("claude"):
            raise BrainError("`claude` CLI not on PATH")
        self.model = model

    def _run(self, system: str, prompt: str) -> str:
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
        p = subprocess.run(["claude", "-p", prompt, "--output-format", "json", "--model", self.model,
                            "--system-prompt", system, "--max-turns", "1"], capture_output=True, text=True, timeout=300, env=env)
        if p.returncode != 0:
            raise BrainError(f"claude CLI failed: {(p.stderr or p.stdout)[-400:]}")
        obj = json.loads(p.stdout)
        if obj.get("is_error"):
            raise BrainError(f"claude CLI: {obj.get('result')}")
        return obj.get("result", "")

    def complete(self, system: str, messages: list[dict], tools: list) -> Turn:
        proto = _PROTO % json.dumps([t.spec() for t in tools])
        text = self._run(system + "\n\n" + proto, _flatten(messages) + "\n\nRespond now with the JSON object.")
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            return Turn(text=text.strip())
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return Turn(text=text.strip())
        calls = [{"id": new_id("call"), "name": c["name"], "input": c.get("input") or {}} for c in obj.get("tool_calls") or [] if c.get("name")]
        return Turn(text=obj.get("reply", ""), tool_calls=calls)

    def draft(self, playbook: dict, trigger_text: str, examples: list[dict], context: str = "", memory: str = "") -> str:
        system = DRAFT_SYSTEM.format(actor=playbook.get("actor"), org=playbook.get("org", "the team"),
                                     kind=playbook.get("response", {}).get("kind", "reply"))
        return self._run(system, draft_prompt(playbook, trigger_text, examples, context, memory)).strip()

    def json_call(self, system: str, prompt: str, max_tokens: int = 1500):
        try:
            return parse_json(self._run(system + "\n\nReply with one JSON object and nothing else.", prompt))
        except BrainError:
            return None

