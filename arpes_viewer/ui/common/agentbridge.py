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

__all__ = ["wanted", "start", "AgentBridge", "ModalDialogBlocked",
           "modal_guard"]


class ModalDialogBlocked(RuntimeError):
    """Code run for an agent asked for a modal dialog, which would wait for
    a click nobody makes and stop everything behind it."""


#: what UTF-8 text looks like after being read as Windows-1252 once: "−"
#: becomes "âˆ’", "°" "Â°", "Γ" "Î“", "Å" "Ã…"
_MOJIBAKE = ("\u00e2\u02c6", "\u00e2\u20ac", "\u00c2\u00b0", "\u00c2\u00b5",
             "\u00ce\u201c", "\u00c3\u2026", "\u00c3\u00a9", "\u00e2\u0080")


def mojibake_warning(text: str) -> str:
    """A warning when ``text`` (an agent's code) holds characters garbled by
    a wrong encoding on the way -- "âˆ’0.2" for "−0.2" -- which would end
    up as such in titles and figure notes; "" if none."""
    found = [m for m in _MOJIBAKE if m in (text or "")]
    if not found:
        return ""
    return ("WARNING: this code holds garbled characters (" + ", ".join(
        repr(m) for m in found) + "): it was written or read in the wrong "
        "encoding (UTF-8 read as Windows-1252). Write files as UTF-8 (in "
        "PowerShell: -Encoding utf8), or write non-ASCII characters as "
        "escapes in the code, e.g. \"\\u2212\" for the minus sign.")


#: How many agent steps are running now (nested modal_guard blocks).
_AGENT_DEPTH = 0


def agent_running() -> bool:
    """Whether code an agent sent is running now. A read in the program
    then stays on the GUI thread (app._acquire): pumping events while it
    waits would let the agent's next command start inside this one."""
    return _AGENT_DEPTH > 0


@contextlib.contextmanager
def modal_guard(log=print):
    """Inside this, a modal dialog raises :class:`ModalDialogBlocked`
    instead of waiting; a plain warning or note is printed (``log``) and
    answered with OK.

    Code an agent runs in the program (the bridge's ``python``, the live
    viewer's command files) runs between events like a click. A dialog
    opened modally from it waits for an answer that never comes, and the
    agent's channel waits with it -- the one way the program used to hang
    for an agent. The error names the dialog and the way round it: the
    tool's programmatic entry (``ContourWindow.slice_figure`` ...), or
    filling and pressing it from ``QTimer.singleShot``.
    """
    from PyQt5.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

    def refuse(what):
        raise ModalDialogBlocked(
            f"{what} would open a modal dialog and wait for a click. Use the "
            f"tool's own function instead (e.g. ContourWindow.slice_figure(...), "
            f"FigureWindow.render(...), save_file(path, ...)), or open the "
            f"dialog with QtCore.QTimer.singleShot(...) and fill it there.")

    def blocked_exec(self, *args, **kwargs):
        title = self.windowTitle() or type(self).__name__
        self.deleteLater()
        refuse(f"“{title}”")

    def note(kind):
        def answer(parent, title, text, *args, **kwargs):
            log(f"[{kind}] {title}: {text}")
            return QMessageBox.Ok
        return staticmethod(answer)

    def refuse_static(name):
        def answer(*args, **kwargs):
            refuse(name)
        return staticmethod(answer)

    patched = [(QDialog, "exec_"), (QDialog, "exec"), (QMessageBox, "exec_"),
               (QMessageBox, "exec"), (QMessageBox, "warning"),
               (QMessageBox, "information"), (QMessageBox, "critical"),
               (QMessageBox, "question"), (QFileDialog, "getOpenFileName"),
               (QFileDialog, "getOpenFileNames"), (QFileDialog, "getSaveFileName"),
               (QFileDialog, "getExistingDirectory"), (QInputDialog, "getText"),
               (QInputDialog, "getDouble"), (QInputDialog, "getInt"),
               (QInputDialog, "getItem")]
    saved = [(owner, name, owner.__dict__.get(name)) for owner, name in patched]
    global _AGENT_DEPTH
    _AGENT_DEPTH += 1
    try:
        QDialog.exec_ = QDialog.exec = blocked_exec
        QMessageBox.exec_ = QMessageBox.exec = blocked_exec
        QMessageBox.warning = note("warning")
        QMessageBox.information = note("note")
        QMessageBox.critical = note("error")
        QMessageBox.question = refuse_static("A question box")
        for owner, name in patched[8:]:
            setattr(owner, name, refuse_static(f"{owner.__name__}.{name}"))
        yield
    finally:
        _AGENT_DEPTH -= 1
        for owner, name, original in saved:
            if original is None:
                try:
                    delattr(owner, name)
                except AttributeError:
                    pass
            else:
                setattr(owner, name, original)

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
        #: set by the AI assistant window's Pause: requests that act are
        #: refused (the agent is told to wait) while the person works by hand
        self.paused = False
        #: ``[(time, op, ok, detail)]`` of the requests answered, newest
        #: last, for the AI assistant window to show
        self.history = []
        #: the same requests in full -- ``{"time", "op", "args", "ok",
        #: "result"}`` -- so the steps can be saved as a script
        #: (:mod:`ui.common.agentsteps`); kept in memory only
        self.record = []

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
        args = request.get("args") or {}
        if self.paused and op not in self.READ_ONLY:
            return {"ok": False, "error": "paused: the person is working in the "
                    "program by hand. Wait, and ask them before going on."}, None
        detail = str(args.get("operation", "")) if op == "api" else ""
        try:
            result = handler(**args)
        except Exception as exc:                            # noqa: BLE001
            self._note(op, False, detail or str(exc)[:80], args,
                       f"{type(exc).__name__}: {exc}")
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, None
        self._note(op, True, detail, args, result)
        if isinstance(result, tuple) and len(result) == 2 and callable(result[1]):
            return {"ok": True, "result": result[0]}, result[1]
        return {"ok": True, "result": result}, None

    #: requests that only look, answered even while paused, and not listed
    READ_ONLY = ("status", "rows", "windows", "screenshot", "figure",
                 "api_help")

    def _note(self, op, ok, detail="", args=None, result=None):
        import time as _time
        if op in self.READ_ONLY:
            return
        now = _time.time()
        self.history.append((now, op, bool(ok), detail))
        del self.history[:-200]
        if isinstance(result, tuple) and len(result) == 2 and callable(result[1]):
            result = result[0]
        if isinstance(result, dict):
            # a picture sent back with a reply is not part of the record
            result = {key: value for key, value in result.items()
                      if key not in ("png", "png_data")}
            if set(result) == {"output"}:
                result = result["output"]
        self.record.append({"time": now, "op": op, "args": dict(args or {}),
                            "ok": bool(ok),
                            "result": "" if result is None else str(result)[:4000]})
        del self.record[:-5000]

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

    def live(self):
        """The documented operations (:class:`ui.common.live.Live`)."""
        if getattr(self, "_live", None) is None:
            from arpes_viewer.ui.common.live import Live
            self._live = Live(self.app)
        return self._live

    def op_api(self, operation: str, args: dict = None):
        """Call one documented operation, ``L.<operation>(**args)``."""
        from arpes_viewer.ui.common.live import _plain, operations
        names = {name for _group, name, _m in operations()}
        if operation not in names:
            raise ValueError(f"no operation {operation!r}; see viewer_api_help")
        args = dict(args or {})
        positional = args.pop("_args", [])
        with modal_guard():
            result = getattr(self.live(), operation)(*positional, **args)
        if hasattr(result, "values") and hasattr(result, "axes"):
            result = {"name": result.name, "kind": result.kind,
                      "labels": result.labels,
                      "shape": list(getattr(result.values, "shape", ()))}
        return _plain(result)

    def op_api_help(self, topic: str = ""):
        """The operations' reference (all, a group, or one in full)."""
        from arpes_viewer.agent.catalog import live_reference
        return {"reference": live_reference(topic)}

    def _figure_window(self, window: str = ""):
        from arpes_viewer.ui.panels.figure import FigureWindow
        figures = [w for w in QApplication.topLevelWidgets()
                   if isinstance(w, FigureWindow) and w.isVisible()]
        if window:
            figures = [w for w in figures
                       if window.lower() in w.windowTitle().lower()]
        if not figures:
            raise ValueError("no figure window open" + (
                f" titled like {window!r}" if window else ""))
        return figures[-1]

    def op_figure(self, window: str = ""):
        """A figure window in numbers: page, frames, titles, levels, text
        sizes (FigureWindow.describe)."""
        return self._figure_window(window).describe()

    def op_render_figure(self, path: str, window: str = "", dpi: int = 0):
        """Write a figure window as a PNG, as it will be printed, and say
        what is in it (FigureWindow.render); the PNG comes back too."""
        figure = self._figure_window(window)
        result = figure.render(os.path.expanduser(path), dpi=int(dpi) or None)
        with open(result["png"], "rb") as handle:
            result["png_data"] = base64.b64encode(handle.read()).decode("ascii")
        return result

    def op_close_window(self, window: str):
        widget = self._window(window)
        if widget is self.app.win:
            raise ValueError("the main window is not closed from here")
        title = widget.windowTitle()
        widget.close()
        return {"closed": title}

    def op_python(self, code: str):
        """Run ``code`` in the program, with ``A`` (the app module), ``L``,
        ``QtCore``, ``QtWidgets``, ``np``, ``os``, ``re``, ``inspect`` and
        ``json``; what it prints comes back."""
        import inspect
        import json as _json
        import re
        import numpy as np
        from PyQt5 import QtCore, QtWidgets
        from arpes_viewer.ui.common.quietwindows import agent_windows
        buffer = io.StringIO()
        scope = {"A": self.app, "L": self.live(), "QtCore": QtCore,
                 "QtWidgets": QtWidgets, "np": np, "os": os, "re": re,
                 "inspect": inspect, "json": _json}
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            try:
                warning = mojibake_warning(code)
                if warning:
                    print(warning)
                with modal_guard(), agent_windows():
                    exec(compile(code, "<agent>", "exec"), scope)
            except Exception:                               # noqa: BLE001
                traceback.print_exc()
        QApplication.processEvents()
        return {"output": buffer.getvalue()[-20000:]}
