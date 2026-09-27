from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional


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

    # ---- a provider implements json_call once and gets both of these ----
    def json_call(self, system: str, prompt: str, max_tokens: int = 1500, model: Optional[str] = None) -> Optional[dict]:
        """Ask for one JSON object. Return None when this brain can't (the callers degrade quietly)."""
        return None

    def judge(self, playbook: dict, trigger: str, drafted: str, actual: str) -> Optional[dict]:
        """Would this draft have done the job, compared with what the person actually wrote?
        {"score": 0..1, "equivalent": bool, "why": str} — or None when this brain can't tell."""
        return judge_impl(self, playbook, trigger, drafted, actual)

    def describe(self, jobs: list[dict]) -> dict[str, dict]:
        """{job_id: {"name": str, "summary": str}} — name the mined jobs the way the team would."""
        return describe_impl(self, jobs)

    def hypothesise(self, playbook: dict, trigger: str, drafted: str, actual: str) -> dict:
        """Guess why a draft missed: {"question": str, "suggestion": str}. Empty when it can't tell."""
        return hypothesise_impl(self, playbook, trigger, drafted, actual)


def parse_json(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text or "", flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


DESCRIBE_SYSTEM = """You name recurring pieces of work the way the team that does them would. Terse, concrete,
no marketing tone. A name is a short verb phrase a colleague would recognise on a board."""

DESCRIBE_PROMPT = """Here are recurring jobs Tacit mined from a team's activity. For each, give a better name and a
one-sentence summary of what the job actually is and when it happens.

Return ONLY JSON: {"jobs": [{"id": "...", "name": "...", "summary": "..."}]}
Rules: name <= 60 characters, no quotes around it, no trailing period. Summary is one sentence, <= 160 characters,
and must mention who does it and what triggers it.

%s"""

HYPOTHESIS_SYSTEM = """You work out why an assistant's draft did not match what a person actually wrote, and propose
the underlying rule in the person's own voice. Be concrete and short. If you cannot see a general rule — if it looks
like a one-off — say so."""

HYPOTHESIS_PROMPT = """Job: %s (owner: %s)

Trigger:
%s

What the assistant drafted:
%s

What %s actually wrote:
%s

Return ONLY JSON: {"question": "...", "suggestion": "...", "one_off": true|false}
"question" is what you'd ask %s to confirm the rule, in one sentence, naming the specific difference you spotted.
"suggestion" is the rule itself, <= 200 characters, phrased as an instruction the assistant could follow next time.
Set one_off true when the difference looks situational rather than a rule."""


DRAFT_SYSTEM = """You are drafting on behalf of {actor}, a member of {org}. You are shadowing them: write EXACTLY the kind of
{kind} they would write in this situation — their tone, their length, their conventions. Do not add caveats or sign-offs they
don't use. Output only the text of the {kind}, nothing else."""


def draft_prompt(playbook: dict, trigger_text: str, examples: list[dict], context: str = "", memory: str = "") -> str:
    ex = "\n\n".join(f"<example>\n<trigger>{e.get('trigger','')}</trigger>\n<response>{e.get('response','')}</response>\n</example>"
                     for e in examples[:8])
    rules = "\n".join(f"- {r}" for r in (playbook.get("rules") or []))
    rules = f"Rules {playbook.get('actor')} has taught you (these override the examples):\n{rules}\n\n" if rules else ""
    mem = f"What the company knows (use it, don't repeat it verbatim):\n{memory}\n\n" if memory else ""
    return (f"Pattern: {playbook.get('name')}\n\n{rules}{mem}How {playbook.get('actor')} has handled this before:\n{ex}\n\n"
            f"{('Conversation so far:' + chr(10) + context + chr(10) + chr(10)) if context else ''}"
            f"New trigger:\n<trigger>{trigger_text}</trigger>\n\nWrite the response now. Output only the text of the {playbook.get('response', {}).get('kind', 'reply')}.")


def describe_impl(brain, jobs: list[dict]) -> dict[str, dict]:
    """Shared implementation: any brain that can return JSON can name jobs."""
    if not jobs:
        return {}
    blocks = []
    for j in jobs:
        ex = "\n".join(f"  trigger: {e.get('trigger','(scheduled)')[:200]}\n  response: {e.get('response','')[:260]}" for e in (j.get("examples") or [])[:3])
        blocks.append(f"<job id=\"{j['id']}\">\n  owner: {j.get('actor')}\n  system: {j.get('system')}\n  seen: {j.get('evidence_count')} times\n"
                      f"  trigger signature: {j.get('trigger')}\n{ex}\n</job>")
    data = brain.json_call(DESCRIBE_SYSTEM, DESCRIBE_PROMPT % "\n\n".join(blocks), max_tokens=2000)
    out: dict[str, dict] = {}
    for row in (data or {}).get("jobs", []):
        if row.get("id") and row.get("name"):
            out[row["id"]] = {"name": str(row["name"])[:120].strip().strip('"'), "summary": str(row.get("summary", ""))[:300].strip()}
    return out


def hypothesise_impl(brain, playbook: dict, trigger: str, drafted: str, actual: str) -> dict:
    actor = playbook.get("actor", "the owner")
    data = brain.json_call(HYPOTHESIS_SYSTEM, HYPOTHESIS_PROMPT % (
        playbook.get("name"), actor, trigger[:2000], drafted[:2000], actor, actual[:2000], actor), max_tokens=700)
    if not data or not data.get("question"):
        return {}
    return {"question": str(data["question"])[:400], "suggestion": "" if data.get("one_off") else str(data.get("suggestion", ""))[:400]}


JUDGE_SYSTEM = """You decide whether an assistant's draft would have done the same job as what a person actually
wrote. You are judging substance, not wording. Rephrasing, different length, a warmer or terser tone, or naming a
customer the original left implicit are all fine — what matters is whether the recipient would end up equally well
served and equally correctly informed.

Mark it down when the draft: states something factually different, omits a step or condition the person included,
adds a commitment or instruction the person did not make, sends the recipient somewhere else, or would require a
colleague to step in and correct it."""

JUDGE_PROMPT = """Job: %s
The person who normally does it: %s

What they were responding to:
%s

What %s actually wrote:
%s

What the assistant drafted:
%s

Return ONLY JSON: {"score": 0.0-1.0, "equivalent": true|false, "why": "..."}
score 1.0 = would serve the recipient just as well; 0.5 = partly right but a colleague would want to add something;
0.0 = wrong, misleading, or would have to be redone. "equivalent" is true when you would have been happy for the
assistant to send this instead. "why" is one short sentence naming the specific difference that decided it."""


def judge_impl(brain, playbook: dict, trigger: str, drafted: str, actual: str) -> Optional[dict]:
    if not (drafted or "").strip() or not (actual or "").strip():
        return None
    actor = playbook.get("actor", "the owner")
    data = brain.json_call(JUDGE_SYSTEM, JUDGE_PROMPT % (
        playbook.get("name", "this job"), actor, (trigger or "(scheduled)")[:2000], actor, actual[:2500], drafted[:2500]),
        max_tokens=400, model=playbook.get("judge_model"))
    if not data or "score" not in data:
        return None
    try:
        score = max(0.0, min(1.0, float(data["score"])))
    except (TypeError, ValueError):
        return None
    return {"score": round(score, 4), "equivalent": bool(data.get("equivalent", score >= 0.6)), "why": str(data.get("why", ""))[:400]}
