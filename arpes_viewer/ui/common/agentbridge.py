"""
ui/common/agentbridge.py
========================
The running program, open to an AI agent on the same machine: the other
half of :mod:`agent.bridge`.

Off unless the program is started with ``--agent-bridge`` (or the
environment variable ``ARPES_VIEWER_AGENT_BRIDGE=1``). Then it listens on
127.0.0.1 only, on a free port (or ``ARPES_VIEWER_AGENT_PORT``), and writes
the port and a fresh random token to ``agent_bridge.json`` in the settings
folder; a request without that token is refused. The MCP server
(``arpes-viewer-mcp``) reads the file and forwards its ``viewer_*`` tools
here, so an agent of any model can list data, open tools, take screenshots
of the windows and run Python inside the program -- the same things the
person at the screen can do.

Everything runs on the GUI thread, between events, like a click. A tool that
opens a window is started after the reply has gone (so a dialog waiting for
an answer does not hold the agent up); the agent then looks at it with a
screenshot.
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import traceback

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QTimer
from PyQt5.QtNetwork import QHostAddress, QTcpServer
from PyQt5.QtWidgets import QApplication

__all__ = ["wanted", "start", "AgentBridge"]

ENV = "ARPES_VIEWER_AGENT_BRIDGE"
FLAG = "--agent-bridge"


def wanted(argv=()) -> bool:
    """Whether the bridge was asked for: the flag, or the variable."""
    return FLAG in list(argv) or os.environ.get(ENV, "").strip() in ("1", "true", "yes")


def start(app_module, parent=None):
    """Start listening for ``app_module`` (:mod:`arpes_viewer.app`);
    the bridge, or None if it could not listen."""
    bridge = AgentBridge(app_module, parent)
    return bridge if bridge.listen_local() else None


class AgentBridge(QTcpServer):
    def __init__(self, app_module, parent=None):
        super().__init__(parent)
        self.app = app_module
        self.token = ""
        self.newConnection.connect(self._connected)
        self._buffers = {}

    def listen_local(self) -> bool:
        from arpes_viewer.agent import bridge as config
        port = int(os.environ.get("ARPES_VIEWER_AGENT_PORT", "0") or 0)
        if not self.listen(QHostAddress.LocalHost, port):
            return False
        self.token = config.write_config(self.serverPort())["token"]
        return True

    def stop(self):
        from arpes_viewer.agent import bridge as config
        self.close()
        try:
            with open(config.config_path(), encoding="utf-8") as handle:
                if json.load(handle).get("token") == self.token:
                    os.remove(config.config_path())
        except (OSError, ValueError):
            pass

    # -- the connection ------------------------------------------------------
    def _connected(self):
        while self.hasPendingConnections():
            sock = self.nextPendingConnection()
            self._buffers[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(lambda s=sock: self._forget(s))

    def _forget(self, sock):
        self._buffers.pop(sock, None)
        sock.deleteLater()

    def _read(self, sock):
        self._buffers[sock] = self._buffers.get(sock, b"") + bytes(sock.readAll())
        if not self._buffers[sock].endswith(b"\n"):
            return
        line = self._buffers.pop(sock).decode("utf-8", errors="replace")
        reply, after = self.answer(line)
        sock.write((json.dumps(reply, default=str) + "\n").encode("utf-8"))
        sock.flush()
        sock.disconnectFromHost()
        if after is not None:
            QTimer.singleShot(50, after)

    def answer(self, line: str):
        """``(reply, then)``: the reply to one request line, and what to run
        once it has been sent (or None)."""
        try:
            request = json.loads(line)
        except ValueError:
            return {"ok": False, "error": "not JSON"}, None
        if not self.token or request.get("token") != self.token:
            return {"ok": False, "error": "wrong token"}, None
        op = str(request.get("op", ""))
        handler = getattr(self, f"op_{op}", None)
        if handler is None:
            return {"ok": False, "error": f"no operation {op!r}"}, None
        try:
            result = handler(**(request.get("args") or {}))
        except Exception as exc:                            # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, None
        if isinstance(result, tuple) and len(result) == 2 and callable(result[1]):
            return {"ok": True, "result": result[0]}, result[1]
        return {"ok": True, "result": result}, None

    # -- the operations ------------------------------------------------------
    def _rows(self):
        A = self.app
        widget = A.ui.FilePathListWidget
        rows = []
        for i in range(widget.count()):
            item = widget.item(i)
            key = item.data(0x0100)
            record = A.loaded_items.get(key, {})
            rows.append({"row": i, "name": record.get("name", item.text()),
                         "kind": record.get("kind", ""),
                         "path": record.get("path", ""),
                         "selected": item.isSelected(),
                         "hidden": item.isHidden()})
        return rows

    def op_status(self):
        from arpes_viewer.version import VERSION
        return {"version": VERSION, "rows": len(self.app.loaded_items),
                "windows": self.op_windows()}

    def op_rows(self):
        return self._rows()

    def op_windows(self):
        return [{"title": w.windowTitle(), "class": type(w).__name__}
                for w in QApplication.topLevelWidgets()
                if w.isVisible() and w.windowTitle()]

    def op_add_files(self, paths):
        before = len(self.app.loaded_items)
        self.app.add_files([os.path.expanduser(p) for p in paths], background=False)
        return {"added": len(self.app.loaded_items) - before,
                "rows": len(self.app.loaded_items)}

    def op_select(self, names=(), rows=(), exact: bool = False):
        """Select the rows by name (whole or part) or by number."""
        widget = self.app.ui.FilePathListWidget
        widget.clearSelection()
        chosen = []
        wanted_names = [str(n).lower() for n in names]
        for row in self._rows():
            name = str(row["name"]).lower()
            hit = row["row"] in set(int(r) for r in rows) or any(
                (name == n) if exact else (n in name) for n in wanted_names)
            if hit:
                widget.item(row["row"]).setSelected(True)
                chosen.append(row["name"])
        return {"selected": chosen}

    def op_run_tool(self, action: str):
        """A tool-panel button, list button or right-click entry, on the
        selection -- started after the reply."""
        from arpes_viewer.ui.launcher.list_actions import RULES
        if action not in RULES and action not in ("open", "slit_cut", "deflector_cut"):
            raise ValueError(f"no action {action!r}; actions: {sorted(RULES)}")
        return ({"started": action, "selection":
                 [r["name"] for r in self._rows() if r["selected"]]},
                lambda: self.app.run_list_action(action))

    def _window(self, title: str = ""):
        if not title or title.lower() in ("main", "main window"):
            return self.app.win
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and title.lower() in widget.windowTitle().lower():
                return widget
        raise ValueError(f"no open window titled like {title!r}")

    def op_screenshot(self, window: str = "", path: str = ""):
        widget = self._window(window)
        QApplication.processEvents()
        image = widget.grab()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        if path:
            image.save(os.path.expanduser(path), "PNG")
        return {"title": widget.windowTitle(), "width": image.width(),
                "height": image.height(),
                "png": base64.b64encode(bytes(data)).decode("ascii")}

    def op_close_window(self, window: str):
        widget = self._window(window)
        if widget is self.app.win:
            raise ValueError("the main window is not closed from here")
        title = widget.windowTitle()
        widget.close()
        return {"closed": title}

    def op_python(self, code: str):
        """Run ``code`` in the program, with ``A`` (the app module),
        ``QtCore``, ``QtWidgets`` and ``np``; what it prints comes back."""
        import numpy as np
        from PyQt5 import QtCore, QtWidgets
        buffer = io.StringIO()
        scope = {"A": self.app, "QtCore": QtCore, "QtWidgets": QtWidgets, "np": np}
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            try:
                exec(compile(code, "<agent>", "exec"), scope)
            except Exception:                               # noqa: BLE001
                traceback.print_exc()
        QApplication.processEvents()
        return {"output": buffer.getvalue()[-20000:]}
