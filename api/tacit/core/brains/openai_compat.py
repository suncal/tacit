"""Any OpenAI-style /chat/completions endpoint (Groq, OpenRouter, vLLM, ...). Escape hatch, not the default."""
from __future__ import annotations

import json
import os

import httpx

from .base import Brain, BrainError, Turn, DRAFT_SYSTEM, draft_prompt, parse_json
from ..ids import new_id


class OpenAICompatBrain(Brain):
    name = "openai-compatible"

    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        if not base_url:
            raise BrainError("TACIT_BRAIN_BASE_URL is required for the openai-compatible brain")
        self.base_url, self.model = base_url.rstrip("/"), model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("TACIT_BRAIN_API_KEY", "")

    def _post(self, body: dict) -> dict:
        r = httpx.post(self.base_url + "/chat/completions", json=body, timeout=120,
                       headers={"Authorization": f"Bearer {self.api_key}"})
        if r.status_code >= 400:
            raise BrainError(f"{self.base_url} {r.status_code}: {r.text[:300]}")
        return r.json()

    def complete(self, system: str, messages: list[dict], tools: list) -> Turn:
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            c = m["content"]
            if isinstance(c, str):
                msgs.append({"role": m["role"], "content": c}); continue
            if m["role"] == "assistant":
                text = "".join(b.get("text", "") for b in c if b.get("type") == "text")
                calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b["input"])}} for b in c if b.get("type") == "tool_use"]
                e = {"role": "assistant", "content": text or None}
                if calls:
                    e["tool_calls"] = calls
                msgs.append(e)
            else:
                for b in c:
                    if b.get("type") == "tool_result":
                        msgs.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"] if isinstance(b["content"], str) else json.dumps(b["content"])})
                    elif b.get("type") == "text":
                        msgs.append({"role": "user", "content": b["text"]})
        body = {"model": self.model, "messages": msgs}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.schema}} for t in tools]
        data = self._post(body)
        msg = data["choices"][0]["message"]
        calls = []
        for c in msg.get("tool_calls") or []:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except Exception:
                args = {}
            calls.append({"id": c.get("id") or new_id("call"), "name": c["function"]["name"], "input": args})
        u = data.get("usage") or {}
        return Turn(text=msg.get("content") or "", tool_calls=calls, usage={"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0), "usd": 0, "model": self.model})

    def draft(self, playbook: dict, trigger_text: str, examples: list[dict], context: str = "", memory: str = "") -> str:
        system = DRAFT_SYSTEM.format(actor=playbook.get("actor"), org=playbook.get("org", "the team"), kind=playbook.get("response", {}).get("kind", "reply"))
        data = self._post({"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": draft_prompt(playbook, trigger_text, examples, context, memory)}]})
        return (data["choices"][0]["message"].get("content") or "").strip()

    def json_call(self, system: str, prompt: str, max_tokens: int = 1500):
        try:
            data = self._post({"model": self.model, "max_tokens": max_tokens, "response_format": {"type": "json_object"},
                               "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        except BrainError:
            return None
        return parse_json(data["choices"][0]["message"].get("content") or "")

