"""
agent/bridge.py
===============
Talking to the program that is open on screen, from another process: the
MCP server's ``viewer_*`` tools.

The running program listens -- only when started with ``--agent-bridge``
(or ``ARPES_VIEWER_AGENT_BRIDGE=1``), see :mod:`ui.common.agentbridge` --
on a port of the local machine (127.0.0.1) and writes the port and a
random token to ``agent_bridge.json`` in the settings folder
(``~/.arpes_viewer``, or ``ARPES_VIEWER_CONFIG_DIR``). A request is one
line of JSON ``{"token", "op", "args"}``; the reply is one line of JSON
``{"ok": true, "result": ...}`` or ``{"ok": false, "error": "..."}``.

Only someone who can read that file can drive the program, and the port
does not listen beyond this machine. Nothing here imports Qt.
"""
from __future__ import annotations

import json
import os
import secrets
import socket

__all__ = ["config_path", "write_config", "read_config", "request",
           "BridgeUnavailable"]

FILE_NAME = "agent_bridge.json"


class BridgeUnavailable(RuntimeError):
    """No program is listening: it is not running, or was not started with
    the bridge on."""


def config_path() -> str:
    folder = os.environ.get("ARPES_VIEWER_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".arpes_viewer")
    return os.path.join(folder, FILE_NAME)


def write_config(port: int, pid: int = None) -> dict:
    """Write the port and a new token, readable by this user only."""
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    values = {"port": int(port), "token": secrets.token_hex(16),
              "pid": int(pid or os.getpid())}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(values, handle)
    try:
        os.chmod(path, 0o600)
    except OSError:                                         # pragma: no cover
        pass
    return values


def read_config() -> dict:
    try:
        with open(config_path(), encoding="utf-8") as handle:
            values = json.load(handle)
    except (OSError, ValueError):
        raise BridgeUnavailable(
            "The viewer is not running with the agent bridge. Start it with "
            "`arpes-viewer --agent-bridge` (or `python -m arpes_viewer "
            "--agent-bridge`), or use the headless tools.") from None
    return values


def request(op: str, timeout: float = 120.0, **args):
    """Send one request to the running program; its result, or raise."""
    values = read_config()
    payload = json.dumps({"token": values.get("token"), "op": op,
                          "args": args}) + "\n"
    try:
        with socket.create_connection(("127.0.0.1", int(values["port"])),
                                      timeout=timeout) as sock:
            sock.sendall(payload.encode("utf-8"))
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if chunk.endswith(b"\n"):
                    break
    except OSError as exc:
        raise BridgeUnavailable(
            f"Could not reach the viewer on port {values.get('port')} ({exc}). "
            f"Is it still running with --agent-bridge?") from None
    try:
        reply = json.loads(b"".join(chunks).decode("utf-8"))
    except ValueError:
        raise RuntimeError("the viewer sent an unreadable reply") from None
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error") or "the viewer refused the request")
    return reply.get("result")
