"""Claude via the official SDK. Native tool use; adaptive thinking on Opus/Sonnet 5."""
from __future__ import annotations

import anthropic

from .base import Brain, BrainError, Turn, DRAFT_SYSTEM, draft_prompt, parse_json

PRICE = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0)}


class AnthropicBrain(Brain):
    name = "anthropic"

    def __init__(self, model: str = "claude-opus-5", effort: str = "medium", api_key: str | None = None):
        self.model, self.effort = model, effort
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def _usage(self, resp) -> dict:
        u = resp.usage
        i, o = PRICE.get(self.model, (5.0, 25.0))
        usd = (u.input_tokens * i + u.output_tokens * o) / 1e6
        return {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "usd": round(usd, 6), "model": self.model}

    def _kwargs(self, system: str, messages: list[dict], max_tokens: int = 16000) -> dict:
        kw = dict(model=self.model, max_tokens=max_tokens, system=system, messages=messages)
        if any(k in self.model for k in ("opus", "sonnet-5", "fable")):
            kw["thinking"] = {"type": "adaptive"}
            kw["output_config"] = {"effort": self.effort}
        return kw

    def complete(self, system: str, messages: list[dict], tools: list) -> Turn:
        kw = self._kwargs(system, messages)
        if tools:
            kw["tools"] = [t.spec() for t in tools]
        try:
            resp = self.client.messages.create(**kw)
        except anthropic.RateLimitError as e:
            raise BrainError(f"rate limited: {e.message}")
        except anthropic.APIStatusError as e:
            raise BrainError(f"anthropic {e.status_code}: {e.message}")
        except anthropic.APIConnectionError:
            raise BrainError("could not reach the Anthropic API")
        if resp.stop_reason == "refusal":
            return Turn(text="I can't help with that request.", usage=self._usage(resp))
        turn = Turn(usage=self._usage(resp))
        for b in resp.content:
            if b.type == "text":
                turn.text += b.text
                turn.raw.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                turn.tool_calls.append({"id": b.id, "name": b.name, "input": dict(b.input)})
                turn.raw.append({"type": "tool_use", "id": b.id, "name": b.name, "input": dict(b.input)})
            elif b.type == "thinking":
                turn.raw.append({"type": "thinking", "thinking": b.thinking, "signature": getattr(b, "signature", "")})
        return turn

    def draft(self, playbook: dict, trigger_text: str, examples: list[dict], context: str = "", memory: str = "") -> str:
        system = DRAFT_SYSTEM.format(actor=playbook.get("actor"), org=playbook.get("org", "the team"),
                                     kind=playbook.get("response", {}).get("kind", "reply"))
        kw = self._kwargs(system, [{"role": "user", "content": draft_prompt(playbook, trigger_text, examples, context, memory)}], max_tokens=1500)
        resp = self.client.messages.create(**kw)
        if resp.stop_reason == "refusal":
            return ""
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def json_call(self, system: str, prompt: str, max_tokens: int = 1500):
        kw = self._kwargs(system, [{"role": "user", "content": prompt}], max_tokens=max_tokens)
        kw["output_config"] = {**kw.get("output_config", {}), "effort": "low"}     # structured, cheap, no deliberation needed
        try:
            resp = self.client.messages.create(**kw)
        except anthropic.APIStatusError:
            return None
        return parse_json("".join(b.text for b in resp.content if b.type == "text"))

