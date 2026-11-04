"""
ui/common/assistant.py
======================
The *AI assistant* window: where a user learns whom to talk to, and gets
the program ready to be driven.

The program has no chat of its own. The person talks to their AI app (the
Claude desktop app, Claude Code, any agent that can read and write files);
the program is that agent's tool. This window says so, and does the three
things that otherwise take a README:

1. **Route 3, recommended**: start the command folder -- the program then
   runs the Python files an agent drops into ``<folder>/viewer_cmd`` (with
   ``L``, the documented operations) -- and write the operations' reference,
   ``API.md``, into that folder, so the agent reads one file instead of the
   source.
2. **A first message** to paste into the AI app, with the data folder and
   the command folder filled in and the working rules written out.
3. **Route 1, optional**: start the agent bridge and copy the MCP settings,
   for an app that speaks MCP.
"""
from __future__ import annotations

import json
import os
import sys

from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QScrollArea, QTextEdit, QVBoxLayout, QWidget)

__all__ = ["AssistantDialog", "starter_prompt", "mcp_settings"]


def starter_prompt(command_folder: str, data_folder: str = "") -> str:
    """The first message to give the AI app."""
    data = data_folder or "<the folder of today's data>"
    return f"""\
You are helping me analyse ARPES data with the program ARPES viewer, which is \
open on my screen.

How to drive it: write small Python files into {os.path.join(command_folder, "viewer_cmd")} \
(one step each, named 01_..., 02_...). The program runs each one and writes what \
it printed to {os.path.join(command_folder, "out")}/cmd_<name>.log; wait for that \
log before the next step. In these files `L` is the program.

First read {os.path.join(command_folder, "API.md")}: it lists every operation the \
program has (L.rows(), L.fermi_edge(...), L.cut_to_k(...), L.kz_to_k(...), \
L.slice_series(...) ...). Use those operations; do not read the program's source \
or press its buttons by their text. `L.help("name")` explains one operation.

Today's data are in {data}. Start with L.add_files("{data}") and L.rows(), tell me \
what is there, and ask me what to do first.

Rules:
1. Everything stays on my computer.
2. Ask me before choosing any physical parameter (where Gamma is, the \
temperature, an energy window, the inner potential ...). If you must guess, say so.
3. Never delete or overwrite anything; every result is a new row or a new file.
4. Check pictures and figures with L.picture, L.figure_describe and \
L.figure_render -- not by reading my screen.
5. After each step, give me the numbers (and the picture's file), and wait for me.
6. If you compute something yourself rather than with an operation, say so.
"""


def mcp_settings() -> str:
    """The MCP server entry for an app's settings, with this Python."""
    python = sys.executable.replace("pythonw.exe", "python.exe")
    return json.dumps({"mcpServers": {"arpes-viewer": {
        "command": python, "args": ["-m", "arpes_viewer.agent"]}}}, indent=2)


class AssistantDialog(QDialog):
    """Get the program ready for an AI agent, and say how to talk to it."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("AI assistant")
        self.setModal(False)
        self.resize(760, 860)
        outer = QVBoxLayout(self)
        # In a scroll area: the explanations wrap, and on a small screen the
        # window must not squeeze them under one another.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)
        layout = QVBoxLayout(body)

        intro = QLabel(
            "<b>Whom to talk to.</b> Talk to your AI app (the Claude desktop "
            "app, Claude Code, any agent that can read and write files) in "
            "plain words: “today I process the kz maps in this folder, "
            "let's start”. This program is the agent's tool: it runs on "
            "your computer, the agent drives it, you see every step here and "
            "can take over at any time.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # -- 1. route 3: the command folder ---------------------------------
        box = QGroupBox("1. Let the agent drive this window (recommended)")
        column = QVBoxLayout(box)
        note = QLabel(
            "Start the command folder, then give your AI app access to it "
            "(Claude desktop app: add the folder to the conversation or the "
            "project). The agent writes small Python files into "
            "<i>viewer_cmd</i>; this window runs them. The folder also gets "
            "<i>API.md</i>, the list of everything the program can do, so "
            "the agent does not have to read the source.")
        note.setWordWrap(True)
        column.addWidget(note)
        row = QHBoxLayout()
        from arpes_viewer.ui.common.agentfolder import default_folder
        current = getattr(app, "_agent_folder", "") or default_folder()
        self.folder_edit = QLineEdit(current)
        browse = QPushButton("Folder...")
        browse.clicked.connect(self._browse)
        row.addWidget(QLabel("Command folder"))
        row.addWidget(self.folder_edit, stretch=1)
        row.addWidget(browse)
        column.addLayout(row)
        row = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.toggle_folder)
        self.open_button = QPushButton("Open the folder")
        self.open_button.clicked.connect(self._open_folder)
        self.folder_status = QLabel("")
        self.folder_status.setWordWrap(True)
        row.addWidget(self.start_button)
        row.addWidget(self.open_button)
        row.addWidget(self.folder_status, stretch=1)
        column.addLayout(row)
        layout.addWidget(box)

        # -- 2. the first message ---------------------------------------------
        box = QGroupBox("2. Paste this into your AI app to start")
        column = QVBoxLayout(box)
        row = QHBoxLayout()
        self.data_edit = QLineEdit(self._data_folder())
        self.data_edit.setPlaceholderText("Today's data folder")
        self.data_edit.textChanged.connect(self.refresh_prompt)
        data_browse = QPushButton("Folder...")
        data_browse.clicked.connect(self._browse_data)
        row.addWidget(QLabel("Data folder"))
        row.addWidget(self.data_edit, stretch=1)
        row.addWidget(data_browse)
        column.addLayout(row)
        self.prompt = QTextEdit()
        self.prompt.setReadOnly(False)
        self.prompt.setMinimumHeight(260)
        column.addWidget(self.prompt, stretch=1)
        copy = QPushButton("Copy the message")
        copy.clicked.connect(lambda: self._copy(self.prompt.toPlainText(),
                                                "The message is on the clipboard."))
        column.addWidget(copy)
        layout.addWidget(box)

        # -- 3. route 1: MCP ----------------------------------------------------
        box = QGroupBox("3. Or, for an app that speaks MCP (optional)")
        column = QVBoxLayout(box)
        note = QLabel(
            "Add the ARPES viewer to the app's MCP servers with these "
            "settings (Claude Desktop: Settings → Developer → Edit "
            "Config), and start the bridge so the app can drive this window "
            "too (tools viewer_api_help, viewer_api).")
        note.setWordWrap(True)
        column.addWidget(note)
        row = QHBoxLayout()
        copy_mcp = QPushButton("Copy the MCP settings")
        copy_mcp.clicked.connect(lambda: self._copy(mcp_settings(),
                                                    "The MCP settings are on the clipboard."))
        self.bridge_button = QPushButton("Start the bridge")
        self.bridge_button.clicked.connect(self.toggle_bridge)
        self.bridge_status = QLabel("")
        row.addWidget(copy_mcp)
        row.addWidget(self.bridge_button)
        row.addWidget(self.bridge_status, stretch=1)
        column.addLayout(row)
        layout.addWidget(box)

        self.message = QLabel("")
        outer.addWidget(self.message)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        outer.addWidget(close, alignment=Qt.AlignRight)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(1500)
        self.refresh_prompt()
        self.refresh_status()

    # -- the folders --------------------------------------------------------
    def _data_folder(self) -> str:
        ui = getattr(self.app, "ui", None)
        text = ui.FilePathLE.text().strip() if ui is not None else ""
        if text:
            return text
        paths = [r.get("path") for r in getattr(self.app, "loaded_items", {}).values()
                 if r.get("path")]
        if paths:
            try:
                return os.path.commonpath([os.path.dirname(p) for p in paths])
            except ValueError:
                return os.path.dirname(paths[0])
        return ""

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Command folder",
                                                self.folder_edit.text())
        if path:
            self.folder_edit.setText(path)
            self.refresh_prompt()

    def _browse_data(self):
        path = QFileDialog.getExistingDirectory(self, "Data folder",
                                                self.data_edit.text())
        if path:
            self.data_edit.setText(path)

    def _open_folder(self):
        folder = self.folder_edit.text().strip()
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _copy(self, text: str, said: str):
        QApplication.clipboard().setText(text)
        self.message.setText(said)

    # -- route 3 --------------------------------------------------------------
    def command_folder(self):
        return getattr(self.app, "_command_folder", None)

    def toggle_folder(self):
        """Start the command folder (writing API.md into it), or stop it."""
        running = self.command_folder()
        if running is not None and running.running:
            running.stop()
            self.app._command_folder = None
        else:
            from arpes_viewer.agent.catalog import build
            from arpes_viewer.ui.common.agentfolder import CommandFolder
            folder = self.folder_edit.text().strip()
            started = CommandFolder(self.app, folder,
                                    self.data_edit.text().strip()).start()
            reference = os.path.join(started.folder, "API.md")
            try:
                text = build()
                with open(reference, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(text)
            except Exception as exc:                        # noqa: BLE001
                self.message.setText(f"API.md not written: {exc}")
            self.app._command_folder = started
        self.refresh_prompt()
        self.refresh_status()

    # -- route 1 --------------------------------------------------------------
    def toggle_bridge(self):
        from arpes_viewer.ui.common import agentbridge
        bridge = getattr(self.app, "_agent_bridge", None)
        if bridge is not None:
            bridge.stop()
            self.app._agent_bridge = None
        else:
            self.app._agent_bridge = agentbridge.start(self.app,
                                                       getattr(self.app, "win", None))
            if self.app._agent_bridge is None:
                self.message.setText("The bridge could not listen.")
        self.refresh_status()

    # -- showing ----------------------------------------------------------------
    def refresh_prompt(self, *_):
        folder = self.folder_edit.text().strip()
        self.prompt.setPlainText(starter_prompt(folder, self.data_edit.text().strip()))

    def refresh_status(self):
        running = self.command_folder()
        if running is not None and running.running:
            self.start_button.setText("Stop")
            self.folder_edit.setEnabled(False)
            self.folder_status.setText(
                f"<span style='color:#14532d'>Listening</span> in "
                f"{running.folder}; {running.ran} command(s) run.")
        else:
            self.start_button.setText("Start")
            self.folder_edit.setEnabled(True)
            self.folder_status.setText("Not listening.")
        bridge = getattr(self.app, "_agent_bridge", None)
        if bridge is not None:
            self.bridge_button.setText("Stop the bridge")
            self.bridge_status.setText(
                f"<span style='color:#14532d'>On</span>, 127.0.0.1:{bridge.serverPort()}")
        else:
            self.bridge_button.setText("Start the bridge")
            self.bridge_status.setText("Off.")

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)
