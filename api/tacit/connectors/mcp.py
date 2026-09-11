"""MCP client over stdio. Any MCP server's tools become Tacit tools (with the same permission gates)."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading

from ..core.tools.registry import Tool

log = logging.getLogger("tacit.mcp")
READ_RX = re.compile(r"^(get|list|read|search|query|fetch|find|describe|show|stat)", re.I)


class MCPServer:
    def __init__(self, name, command, env=None):
        self.name, self.command, self.env = name, command, env
        self.proc, self._id, self._lock, self.tools = None, 0, threading.Lock(), []

    def start(self):
        env = dict(os.environ); env.update(self.env or {})
        self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env, bufsize=1)
        self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "tacit", "version": "0.1"}})
        self.notify("notifications/initialized")
        self.tools = self.rpc("tools/list", {}).get("tools", [])
        return self.tools

    def notify(self, method, params=None):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}) + "\n"); self.proc.stdin.flush()

    def rpc(self, method, params):
        with self._lock:
            self._id += 1
            mid = self._id
            self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params}) + "\n"); self.proc.stdin.flush()
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    raise RuntimeError(f"MCP server {self.name} closed")
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                if msg.get("id") == mid:
                    if "error" in msg:
                        raise RuntimeError(f"MCP {self.name}: {msg['error']}")
                    return msg.get("result", {})

    def call(self, tool, args):
        res = self.rpc("tools/call", {"name": tool, "arguments": args})
        parts = [c["text"] if c.get("type") == "text" else f"[{c.get('type')}]" for c in res.get("content", [])]
        return {"content": "\n".join(parts)[:60000], "is_error": bool(res.get("isError"))}


def register_servers(reg, settings) -> list[MCPServer]:
    servers = []
    try:
        specs = json.loads(settings.mcp_servers) if settings.mcp_servers else []
    except Exception as e:
        log.warning("TACIT_MCP_SERVERS is not valid JSON: %s", e)
        return servers
    for s in specs:
        srv = MCPServer(s["name"], s["command"], s.get("env"))
        try:
            tools = srv.start()
        except Exception as e:
            log.warning("mcp %s failed to start: %s", s["name"], e)
            continue
        servers.append(srv)
        for t in tools:
            def fn(ctx, _srv=srv, _t=t["name"], **kw):
                out = _srv.call(_t, kw)
                if out["is_error"]:
                    raise RuntimeError(out["content"][:500])
                return {"content": out["content"]}
            reg.add(Tool(f"{srv.name}__{t['name']}", t.get("description", ""), t.get("inputSchema") or {"type": "object", "properties": {}}, fn,
                         "read" if READ_RX.match(t["name"]) else "write", f"mcp:{srv.name}", srv.name))
    return servers
