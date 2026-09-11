from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class BrainError(RuntimeError):
    pass


@dataclass
class Turn:
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)       # [{id, name, input}]
    raw: list[dict] = field(default_factory=list)              # provider content blocks to echo back
    usage: dict[str, Any] = field(default_factory=dict)        # {input_tokens, output_tokens, usd}


class Brain:
    name = "base"
    model = "—"
    is_llm = True

    def complete(self, system: str, messages: list[dict], tools: list) -> Turn:
        raise NotImplementedError

    def draft(self, playbook: dict, trigger_text: str, examples: list[dict], context: str = "") -> str:
        """Write what the playbook's owner would have written in response to trigger_text."""
        raise NotImplementedError


DRAFT_SYSTEM = """You are drafting on behalf of {actor}, a member of {org}. You are shadowing them: write EXACTLY the kind of
{kind} they would write in this situation — their tone, their length, their conventions. Do not add caveats or sign-offs they
don't use. Output only the text of the {kind}, nothing else."""


def draft_prompt(playbook: dict, trigger_text: str, examples: list[dict], context: str = "") -> str:
    ex = "\n\n".join(f"<example>\n<trigger>{e.get('trigger','')}</trigger>\n<response>{e.get('response','')}</response>\n</example>"
                     for e in examples[:5])
    return (f"Pattern: {playbook.get('name')}\n\nHow {playbook.get('actor')} has handled this before:\n{ex}\n\n"
            f"{('Context:' + chr(10) + context + chr(10) + chr(10)) if context else ''}"
            f"New trigger:\n<trigger>{trigger_text}</trigger>\n\nWrite the response now.")
