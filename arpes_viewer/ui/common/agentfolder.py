"""
ui/common/agentfolder.py
========================
Route 3: the running program takes commands from a folder.

An agent that can only read and write files (the Claude desktop app linked
to a folder, for one) drives the program by dropping small Python files
into ``<folder>/viewer_cmd/``. The program runs each between events, as a
click, with ``L`` (:class:`ui.common.live.Live`, the documented operations) in
reach, writes what it printed to ``<folder>/out/cmd_<name>.log`` and moves
the file to ``<folder>/viewer_done/`` -- which leaves a record of every step.
``<folder>/heartbeat.txt`` says the program is listening. The operations'
reference, ``API.md``, is read where the program is installed
(:func:`agent.catalog.path`), not copied here.

Started from the program's *AI assistant* window (Help menu), or by
``agentic/launch_viewer.py``. A modal dialog asked for by a command raises
``ModalDialogBlocked`` instead of freezing the folder (see
:func:`ui.common.agentbridge.modal_guard`).
"""
from __future__ import annotations

import contextlib
import io
import os
import time
import traceback

from arpes_viewer.ui.common.paths import native

__all__ = ["CommandFolder", "FOLDERS", "default_folder"]

#: the working folders made inside the command folder
FOLDERS = ("viewer_cmd", "viewer_done", "out", "shots", "figures")


def default_folder() -> str:
    """Where the command folder goes when none is chosen: the repository's
    ``agentic/`` if the program runs from one, else ``~/arpes_agent``."""
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    agentic = os.path.join(here, "agentic")
    if os.path.isdir(agentic):
        return agentic
    return os.path.join(os.path.expanduser("~"), "arpes_agent")


class CommandFolder:
    """Poll ``folder/viewer_cmd`` for ``*.py`` files and run them."""

    def __init__(self, app, folder: str, data_dir: str = "", interval_ms: int = 700):
        from arpes_viewer.ui.common.live import Live
        self.app = app
        self.folder = os.path.abspath(native(folder))
        self.data_dir = native(data_dir) or ""
        self.interval_ms = int(interval_ms)
        self.live = Live(app)
        self.timer = None
        self.ran = 0
        #: when the last command ran, and whether it failed (a traceback in
        #: what it printed) -- what the status light shows
        self.last_run = 0.0
        self.last_failed = False
        #: an error of the polling itself (the folder unreadable ...)
        self.error = ""
        for name in FOLDERS:
            os.makedirs(os.path.join(self.folder, name), exist_ok=True)

    # -- running ------------------------------------------------------------
    def start(self):
        from PyQt5 import QtCore
        if self.timer is None:
            self.timer = QtCore.QTimer(getattr(self.app, "win", None))
            self.timer.timeout.connect(self.poll)
        self.timer.start(self.interval_ms)
        self.app._agent_folder = self.folder
        self._heartbeat()
        return self

    def stop(self):
        if self.timer is not None:
            self.timer.stop()
        if getattr(self.app, "_agent_folder", "") == self.folder:
            self.app._agent_folder = ""
        try:
            os.remove(os.path.join(self.folder, "heartbeat.txt"))
        except OSError:
            pass

    @property
    def running(self) -> bool:
        return self.timer is not None and self.timer.isActive()

    def scope(self) -> dict:
        """What a command file sees (``inspect``, ``os``, ``re`` and
        ``json`` already imported, as most steps want one of them)."""
        import inspect
        import json
        import re
        import numpy as np
        from PyQt5 import QtCore, QtWidgets
        return {"A": self.app, "L": self.live, "HERE": self.folder,
                "DATA": self.data_dir, "QtCore": QtCore,
                "QtWidgets": QtWidgets, "np": np, "os": os, "re": re,
                "inspect": inspect, "json": json}

    def run_file(self, path: str) -> str:
        """Run one command file; returns what it printed."""
        from arpes_viewer.ui.common.agentbridge import mojibake_warning, modal_guard
        from arpes_viewer.ui.common.quietwindows import agent_windows
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            try:
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                warning = mojibake_warning(text)
                if warning:
                    print(warning)
                code = compile(text, path, "exec")
                with modal_guard(), agent_windows():
                    exec(code, self.scope())
            except Exception:                               # noqa: BLE001
                traceback.print_exc()
        return buffer.getvalue()

    def pending_since(self) -> float:
        """When the oldest command still waiting was written; 0 if none."""
        queue = os.path.join(self.folder, "viewer_cmd")
        try:
            times = [os.path.getmtime(os.path.join(queue, n))
                     for n in os.listdir(queue) if n.endswith(".py")]
        except OSError:
            return 0.0
        return min(times) if times else 0.0

    def poll(self):
        """Run every waiting command file, oldest name first. Never inside
        itself: a command that waits on a progress window pumps events, and
        this timer must not start the next command (or the same one again,
        not yet moved to viewer_done) in the middle of it."""
        if getattr(self, "_polling", False):
            return
        self._polling = True
        try:
            self._poll()
            self.error = ""
        except Exception as exc:                            # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self._polling = False

    def _poll(self):
        queue = os.path.join(self.folder, "viewer_cmd")
        done = os.path.join(self.folder, "viewer_done")
        try:
            names = sorted(n for n in os.listdir(queue) if n.endswith(".py"))
        except OSError:
            return
        for name in names:
            source = os.path.join(queue, name)
            time.sleep(0.2)                     # let the writer finish
            output = self.run_file(source)
            log = os.path.join(self.folder, "out", "cmd_" + name[:-3] + ".log")
            with open(log, "w", encoding="utf-8") as handle:
                handle.write(output)
            target = os.path.join(done, name)
            if os.path.exists(target):
                stem, ext = os.path.splitext(name)
                target = os.path.join(done, f"{stem}_{int(time.time())}{ext}")
            os.replace(source, target)
            self.ran += 1
            self.last_run = time.time()
            self.last_failed = "Traceback (most recent call last)" in output
        self._heartbeat()

    def _heartbeat(self):
        try:
            with open(os.path.join(self.folder, "heartbeat.txt"), "w",
                      encoding="utf-8") as handle:
                handle.write(time.strftime("%Y-%m-%d %H:%M:%S")
                             + f"  listening; {self.ran} command(s) run\n")
        except OSError:
            pass
