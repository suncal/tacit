"""Tools are functions with a schema, a risk class, and — if they write — a recipe to undo themselves."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ToolResult:
    data: dict[str, Any]
    undo: Optional[dict[str, Any]] = None      # {"tool": name, "args": {...}}; None = irreversible/no-op
    preview: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., Any]                     # fn(ctx, **args) -> dict | ToolResult
    risk: str = "read"                         # read | write | exec
    source: str = "builtin"
    system: str = "tacit"                      # for change previews: github / slack / files / memory ...
    previewer: Optional[Callable[..., dict]] = None   # previewer(ctx, **args) -> {summary, kind, diff?}

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}

    def public(self) -> dict:
        return {"name": self.name, "description": self.description, "risk": self.risk, "source": self.source,
                "system": self.system, "params": list(self.schema.get("properties", {}).keys()), "reversible": self.risk == "read" or self.previewer is not None}


class Registry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def tool(self, name, description, schema=None, risk="read", source="builtin", system="tacit", previewer=None):
        def deco(fn):
            self.add(Tool(name, description, schema or {"type": "object", "properties": {}}, fn, risk, source, system, previewer))
            return fn
        return deco


def obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}
