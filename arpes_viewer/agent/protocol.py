"""
agent/protocol.py
=================
The Model Context Protocol (MCP) over stdio, written out: JSON-RPC 2.0
messages, one per line, on stdin and stdout.

Only what a tool server needs: ``initialize``, ``ping``, ``tools/list`` and
``tools/call`` (and the notifications, which need no answer). Written here
rather than taken from the ``mcp`` package so that the server runs on the
program's own dependencies, on any Python the program runs on.

A tool is a :class:`Tool`: a name, a description, a JSON-Schema of its
arguments and a function taking them as keywords. The function returns a
string, a dict (sent as JSON text), an :class:`Image`, or a list of those;
an exception becomes a tool error (``isError``) whose text says what went
wrong, which a model can read and act on -- a protocol error is kept for
what is wrong with the request itself.
"""
from __future__ import annotations

import base64
import json
import sys
import traceback
from dataclasses import dataclass, field

__all__ = ["Tool", "Image", "Server", "PROTOCOL_VERSIONS"]

#: The protocol versions understood; the client's is echoed when it is one.
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


@dataclass
class Tool:
    name: str
    description: str
    function: object
    properties: dict = field(default_factory=dict)
    required: tuple = ()
    #: True for a tool that only reads (MCP's ``readOnlyHint``)
    read_only: bool = False

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description,
                "inputSchema": {"type": "object",
                                "properties": self.properties,
                                "required": list(self.required)},
                "annotations": {"readOnlyHint": bool(self.read_only)}}


@dataclass
class Image:
    """A picture to hand back: PNG bytes, and a line saying what it is."""
    png: bytes
    caption: str = ""


def _content(result) -> list:
    """A tool's return value as MCP content blocks."""
    items = result if isinstance(result, list) else [result]
    blocks = []
    for item in items:
        if isinstance(item, Image):
            if item.caption:
                blocks.append({"type": "text", "text": item.caption})
            blocks.append({"type": "image", "mimeType": "image/png",
                           "data": base64.b64encode(item.png).decode("ascii")})
        elif isinstance(item, str):
            blocks.append({"type": "text", "text": item})
        else:
            blocks.append({"type": "text",
                           "text": json.dumps(item, indent=1, default=_plain)})
    return blocks or [{"type": "text", "text": "done"}]


def _plain(value):
    """What json cannot write by itself: numpy numbers and arrays."""
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except ImportError:                                    # pragma: no cover
        pass
    return str(value)


class Server:
    """A set of tools, answering requests one line at a time."""

    def __init__(self, name: str, version: str, tools, instructions: str = ""):
        self.name, self.version = name, version
        self.tools = {tool.name: tool for tool in tools}
        self.instructions = instructions

    # -- one message ---------------------------------------------------------
    def handle(self, message: dict):
        """The reply to one JSON-RPC message, or None for a notification."""
        method = message.get("method")
        ident = message.get("id")
        if ident is None:                     # a notification: no reply
            return None
        try:
            result = self._dispatch(method, message.get("params") or {})
        except _ProtocolError as exc:
            return {"jsonrpc": "2.0", "id": ident,
                    "error": {"code": exc.code, "message": str(exc)}}
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def _dispatch(self, method, params):
        if method == "initialize":
            asked = params.get("protocolVersion")
            version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            result = {"protocolVersion": version,
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": self.name, "version": self.version}}
            if self.instructions:
                result["instructions"] = self.instructions
            return result
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [tool.spec() for tool in self.tools.values()]}
        if method == "tools/call":
            return self.call(params.get("name"), params.get("arguments") or {})
        raise _ProtocolError(-32601, f"method not found: {method}")

    def call(self, name, arguments: dict) -> dict:
        """Run one tool: its content, or its error as text (``isError``)."""
        tool = self.tools.get(name)
        if tool is None:
            raise _ProtocolError(-32602, f"no tool called {name!r}")
        try:
            return {"content": _content(tool.function(**arguments)),
                    "isError": False}
        except TypeError as exc:
            # the arguments did not fit: say which ones it takes
            return {"content": [{"type": "text", "text":
                                 f"{exc}. {name} takes: "
                                 f"{', '.join(tool.properties) or 'nothing'}"}],
                    "isError": True}
        except Exception as exc:                           # noqa: BLE001
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            return {"content": [{"type": "text", "text": detail}],
                    "isError": True}

    # -- the loop ------------------------------------------------------------
    def serve(self, stdin=None, stdout=None):
        """Answer requests from ``stdin`` until it closes."""
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                self._write(stdout, {"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32700,
                                               "message": f"parse error: {exc}"}})
                continue
            batch = message if isinstance(message, list) else [message]
            replies = [r for r in (self.handle(m) for m in batch
                                   if isinstance(m, dict)) if r is not None]
            if not replies:
                continue
            self._write(stdout, replies if isinstance(message, list) else replies[0])

    @staticmethod
    def _write(stdout, payload):
        stdout.write(json.dumps(payload, default=_plain) + "\n")
        stdout.flush()


class _ProtocolError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
