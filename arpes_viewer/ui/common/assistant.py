"""
ui/common/assistant.py
======================
The *AI assistant* window: start an AI agent on your data in one step, then
watch it work and step in.

The program has no chat of its own: the person talks to their AI app (the
Claude desktop app, Claude Code, an MCP app), and the program is that
agent's tool. All this window asks for is what a person knows anyway --

* the **data folder** and the **results folder**,
* a few **options** (ask before each physical parameter, a usage log, a
  report, slides, hiding the sample's identity ...) and anything else in
  their own words,
* **how the AI app connects**: by working in folders (route 3, the default)
  or as an MCP app (route 1);

-- and **Copy the prompt and start** does the rest: it starts the command
folder or the agent
bridge, and puts on the clipboard one prompt that tells the agent where
everything is, what to read first and how to work. Pasted into the AI app,
it starts.

Below, the window **watches**: each step the agent ran, whether it failed,
what it printed; **Pause** stops the agent's commands from running while
the person works by hand, **Resume** lets them through again.
"""
from __future__ import annotations

import json
import os
import sys
import time

from arpes_viewer.ui.common.paths import native

from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog,
                             QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QPushButton, QRadioButton, QScrollArea,
                             QSplitter, QTextEdit, QVBoxLayout, QWidget)

__all__ = ["AssistantDialog", "OPTIONS", "build_prompt", "mcp_settings",
           "command_folder_of"]

#: The options, ``(key, label, on by default, what the prompt then says)``.
OPTIONS = (
    ("ask", "Ask me before choosing a physical parameter", True,
     "Ask me before choosing any physical parameter (where Γ is, the "
     "temperature, an energy window, the inner potential, a threshold). If "
     "you must guess, say so and record the guess."),
    ("steps", "Show me each step and wait for my go-ahead", True,
     "After each step give me the numbers and the picture's file, and wait "
     "for my go-ahead before the next."),
    ("usage", "Record token / plan usage per step", False,
     "Keep a usage log in {usage_log}: one line per step with the "
     "time and the step; add a token or plan-usage figure only when I give "
     "you one (you cannot see them yourself)."),
    ("hide", "Hide the sample's real identity", False,
     "Hide the sample's real identity in everything you write (reports, "
     "slides, figure titles, file names): call it \"sample A\", give lattice "
     "constants only as a, b, c, and leave out the compound, the proposal "
     "and the beamtime names."),
    ("report", "Write a report at the end", False,
     "At the end write a report in the folder {report} (Markdown, and PDF if "
     "you can): the data, each step with its parameters and where each came "
     "from, the figures, and what is uncertain."),
    ("script", "Save every step as one Python script at the end", True,
     "At the end, as a last step of its own, call the operation "
     "session_script with the path {script}: it writes every step you ran, "
     "in order, as one Python script (the record of the processing, which "
     "can be run again)."),
    ("slides", "Make slides (PPTX) of the key figures", False,
     "At the end make a slide deck {slides}: one slide "
     "per key figure with a two-line caption."),
    ("clean", "Keep the list tidy (offer to remove intermediate rows)", False,
     "At the end, list the intermediate rows and offer to remove them from "
     "the program's list, keeping the originals and the final results (the "
     "files on disk are not touched); remove nothing I have not agreed to."),
)


def command_folder_of(results: str) -> str:
    """Where the agent's command folder goes: inside the results folder,
    so one folder given to the AI app covers both."""
    return os.path.join(results, "_agent")


def mcp_settings() -> str:
    """The MCP server entry for an app's settings, with this Python."""
    python = sys.executable.replace("pythonw.exe", "python.exe")
    return json.dumps({"mcpServers": {"arpes-viewer": {
        "command": python, "args": ["-m", "arpes_viewer.agent"]}}}, indent=2)


def build_prompt(mode: str, data: str, results: str, options=(),
                 extra: str = "") -> str:
    """The prompt to paste into the AI app. ``mode`` is ``"folders"``
    (route 3) or ``"mcp"`` (route 1); ``options`` the keys of
    :data:`OPTIONS` ticked; ``extra`` the person's own requests."""
    from arpes_viewer.agent.catalog import path as reference_path
    from arpes_viewer.ui.common.paths import native
    # the system's own separators throughout: a folder from a dialog (or
    # typed) joined with a file name must not come out as D:/Data\_agent
    data = native(data) or "<the data folder>"
    results = native(results) or "<the results folder>"
    commands = command_folder_of(results)
    reference = reference_path()
    places = {"usage_log": os.path.join(results, "usage_log.md"),
              "report": os.path.join(results, "report"),
              "slides": os.path.join(results, "slides", "summary.pptx"),
              "script": os.path.join(results, "agent_steps.py")}
    chosen = [text.format(**places) for key, _label, _on, text in OPTIONS
              if key in set(options)]
    read_first = (f"Before anything else read {reference}: it lists every "
                  "operation the program has (it is part of the program's "
                  "installation; if you cannot open it, ")
    lines = ["You are helping me process ARPES data with the program ARPES "
             "viewer, which is open on my screen; I watch every step there "
             "and may step in.", ""]
    lines += ["Folders:",
              f"- Data (read only; never change anything in it): {data}",
              f"- Results (write everything here, figures and files): {results}"]
    if mode == "mcp":
        python = sys.executable.replace("pythonw.exe", "python.exe")
        lines += ["", "Connect (once): the program offers its operations as an "
                  "MCP server, and its agent bridge is already on.",
                  "- If you are Claude Code, run:  claude mcp add arpes-viewer "
                  f"-- \"{python}\" -m arpes_viewer.agent",
                  "- Otherwise tell me to add this to your MCP settings and "
                  "restart you:",
                  mcp_settings(),
                  "Then call viewer_status (it must show the program and its "
                  "rows) and viewer_api_help: it lists every operation the "
                  "program has (the same list as " + reference + "). Call them "
                  "with viewer_api(operation, args). Use these operations, not "
                  "viewer_python, wherever one exists; "
                  "viewer_api_help(\"name\") explains one. If your app loads "
                  "tool definitions on demand, load all the arpes-viewer tools "
                  "in one search.",
                  "", "Start: viewer_api(\"add_files\", "
                  + json.dumps({"paths": data}, ensure_ascii=False)
                  + "), then viewer_api(\"rows\", {\"compact\": true}); tell "
                  "me what is there and propose a plan."]
    else:
        lines += [f"- Commands: {commands}", "",
                  "How to drive the program: write one small Python file per "
                  f"step into {os.path.join(commands, 'viewer_cmd')} (named "
                  "01_..., 02_...). The program runs it and writes what it "
                  f"printed to {os.path.join(commands, 'out', 'cmd_<name>.log')}; "
                  "wait for that log before the next step. In these files `L` "
                  "is the program.",
                  read_first + "run a first command file with print(L.help()) "
                  "and read its log: the same list). Use those operations "
                  "(L.add_files, L.fermi_edge, L.kz_to_k, L.slice_series ...), "
                  "not the program's source; L.help(\"name\") explains one.",
                  "", f"Start: print(L.add_files(r\"{data}\")) and "
                  "print(L.rows(compact=True)); tell me what is there and "
                  "propose a plan.",
                  "", "If a command file stays unrun for more than a minute, I "
                  "have paused you to work by hand: wait, and ask me."]
    rules = ["Everything stays on this computer.",
             "Never delete or overwrite anything: every result is a new row "
             "in the program's list or a new file in the results folder.",
             "Check pictures and figures with the program's own operations "
             "(picture, figure_describe, figure_render), not by reading my "
             "screen.",
             "After adding the data, compare the rows with the folder and "
             "tell me what add_files left out, did not recognise or warned "
             "about. When you rename rows, say which part of each name comes "
             "from the file name and which from the recorded metadata; mark "
             "guesses, and ask me about files whose names do not say what "
             "they are.",
             "Use the operations. Before computing anything yourself, look "
             "for it in L.help(), L.tools() and L.functions(); if you compute "
             "it yourself anyway, say so. Never edit the program's internal "
             "tables: if no operation does what is needed, stop, tell me "
             "which operation is missing, and ask before working around it.",
             "Fermi level: fit the raw data, before any normalisation. Every "
             "row has its own energy axis: read it, and choose the window "
             "for that row (fermi_edge_search), never another row's. Pass "
             "picture=... so I can check each fit. Rows of the same photon "
             "and pass energy should agree within a few meV; if they do not, "
             "or two edges fit, show me and ask once, then apply the answer "
             "to the rest.",
             "Name processed rows the program's way: the source's name, then "
             "one tag in square brackets per step, oldest first, from the "
             "table of L.naming() (e.g. 'Map80eV [norm] [E-E_F] [k]'); a "
             "new_name of your own follows the same rule, so the list sorts "
             "by what was last done.",
             "Keep the list readable: do chains of steps in one call where "
             "the operation offers it (map_to_k / cut_to_k with ef= and "
             "normalise_axes=), so only final rows are listed, named clearly; "
             "remove intermediate rows only after I agree.",
             "Figures: try them in {check}; publish one final version per "
             "figure in {figures}<N>; when I ask for a change, move the old "
             "version to {superseded} rather than keeping v1/v2 files. Signed "
             "quantities (dichroism, differences) get a diverging colour map "
             "with symmetric levels.".format(
                 check=os.path.join(results, "check"),
                 figures=os.path.join(results, "figures", "Figure"),
                 superseded=os.path.join(results, "_superseded")),
             "Keep outputs small: rows(compact=True), profile(..., "
             "summary=True) or to a file; large arrays go to files. Write "
             "code files as UTF-8 and non-ASCII characters as \\u escapes. "
             "Say what you are doing before a long step."] + chosen
    lines += ["", "Rules:"] + [f"{i}. {rule}" for i, rule in enumerate(rules, 1)]
    if extra.strip():
        lines += ["", "What I want:", extra.strip()]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# The status light: the AI assistant button's colour
# ----------------------------------------------------------------------
#: ``state: (colour, hover colour, words)``
LIGHTS = {
    "idle": ("#8a8f98", "#9aa0a8", "Not running: no agent at work (not "
             "started, or nothing done for a few minutes)."),
    "running": ("#1e8e3e", "#26a34a", "Running: the agent is working."),
    "paused": ("#c99a06", "#d9aa16", "Paused: you are working by hand; the "
               "agent's next commands wait until Resume."),
    "error": ("#d93025", "#e24b40", "Error: the agent's last step failed "
              "(marked \u2717 in the AI assistant's list of steps), or its "
              "commands stopped being run."),
}

#: an agent quiet for longer than this counts as not running (s)
QUIET_AFTER = 300.0
#: a command left unrun for longer than this, while not paused, means the
#: program stopped running them (s)
STALLED_AFTER = 60.0


def agent_state(app, now: float = None):
    """``(state, words)`` of the agent working with the program ``app``:
    ``"idle"``, ``"running"``, ``"paused"`` or ``"error"`` (see
    :data:`LIGHTS`). Read from the command folder and the bridge, so it holds
    whether or not the AI assistant window is open."""
    now = time.time() if now is None else now
    folder = getattr(app, "_command_folder", None)
    bridge = getattr(app, "_agent_bridge", None)
    if folder is None and bridge is None:
        return "idle", LIGHTS["idle"][2]
    if getattr(app, "_agent_paused", False):
        return "paused", LIGHTS["paused"][2]
    last, failed, problem = 0.0, False, ""
    if folder is not None:
        if folder.error:
            problem = f"the command folder cannot be read: {folder.error}"
        elif not folder.running:
            problem = "the command folder stopped being watched"
        else:
            waiting = folder.pending_since()
            if waiting and now - waiting > STALLED_AFTER:
                problem = (f"a command has waited {now - waiting:.0f} s "
                           f"without being run")
        if folder.last_run > last:
            last, failed = folder.last_run, folder.last_failed
    history = list(getattr(bridge, "history", []) or [])
    if history and history[-1][0] > last:
        last, failed = history[-1][0], not history[-1][2]
    if problem:
        return "error", f"Error: {problem}."
    if failed:
        return "error", LIGHTS["error"][2]
    if last and now - last <= QUIET_AFTER:
        return "running", LIGHTS["running"][2]
    if folder is not None and folder.pending_since():
        return "running", LIGHTS["running"][2]
    if not last:
        return "idle", ("Ready: listening, waiting for the agent's first "
                        "command (paste the prompt into your AI app).")
    return "idle", ("Not running: listening, but the agent has done nothing "
                    "for a few minutes (finished, or waiting for you).")


def light_style(state: str) -> str:
    colour, hover, _words = LIGHTS[state]
    return ("QPushButton { text-align: center; font-weight: bold;"
            " padding: 6px 8px; color: white; border-radius: 5px;"
            f" background-color: {colour}; }}"
            f" QPushButton:hover {{ background-color: {hover}; }}")


class StatusLight:
    """Keeps the AI assistant button's colour on the agent's state, every
    second, for as long as the program runs -- the window need not be
    open."""

    TIP = ("Let an AI agent process your data in this window. The colour is "
           "the agent's state: grey not running, green running, yellow "
           "paused (you work by hand), red an error.")

    def __init__(self, app, button):
        self.app, self.button = app, button
        self.state = None
        self.timer = QTimer(button)
        self.timer.timeout.connect(self.update)
        self.timer.start(1000)
        self.update()

    def update(self):
        state, words = agent_state(self.app)
        if state != self.state:
            self.button.setStyleSheet(light_style(state))
            self.state = state
        self.button.setToolTip(f"{self.TIP}\n\nNow: {words}")
        return state


def install_status_light(app, button):
    """Start the light on ``button`` (the main window's AI assistant)."""
    light = StatusLight(app, button)
    app._status_light = light
    return light


def _settings_path() -> str:
    folder = os.environ.get("ARPES_VIEWER_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".arpes_viewer")
    return os.path.join(folder, "assistant.json")


class AssistantDialog(QDialog):
    """Two folders, a few options, one prompt; then watch and step in."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("AI assistant")
        self.setModal(False)
        self.resize(1180, 760)
        saved = self._load()

        # Two columns: setting it up on the left, watching it work on the
        # right -- always in sight, whatever the left one scrolls to.
        outer = QVBoxLayout(self)
        columns = QHBoxLayout()
        outer.addLayout(columns, stretch=1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        scroll.setMinimumWidth(520)
        columns.addWidget(scroll, stretch=5)
        layout = QVBoxLayout(body)

        intro = QLabel(
            "Let your AI app process your data in this window. Choose the "
            "folders, tick what you want, press <b>Copy the prompt and "
            "start</b>, and paste the prompt into your AI app. Then watch "
            "each step below -- and in the list and windows -- and step in "
            "whenever you like.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # -- the folders ----------------------------------------------------
        box = QGroupBox("1. Folders")
        grid = QGridLayout(box)
        self.data_edit = QLineEdit(native(saved.get("data") or self._data_folder()) or "")
        self.data_edit.setPlaceholderText("the data to process (read only)")
        self.results_edit = QLineEdit(native(saved.get("results", "")) or "")
        self.results_edit.setPlaceholderText("where figures, files and the "
                                             "report go")
        for row, (label, edit) in enumerate((("Data", self.data_edit),
                                              ("Results", self.results_edit))):
            browse = QPushButton("Folder...")
            browse.clicked.connect(lambda _=False, e=edit: self._browse(e))
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(browse, row, 2)
        layout.addWidget(box)

        # -- what is wanted ---------------------------------------------------
        box = QGroupBox("2. What you want")
        column = QVBoxLayout(box)
        self.option_boxes = {}
        chosen = saved.get("options")
        for key, label, default, _text in OPTIONS:
            check = QCheckBox(label)
            check.setChecked(key in chosen if chosen is not None else default)
            column.addWidget(check)
            self.option_boxes[key] = check
        column.addWidget(QLabel("Anything else, in your own words:"))
        self.extra_edit = QTextEdit()
        self.extra_edit.setPlaceholderText(
            "e.g. Process the LH and LV Fermi-surface maps at 80 eV; Γ is at "
            "deflector -1.5°. Make Fig. 1: constant-energy maps at E_F, -0.2, "
            "-0.4 eV with the Brillouin zone, and the cut along Γ-M.")
        self.extra_edit.setPlainText(saved.get("extra", ""))
        self.extra_edit.setFixedHeight(80)
        column.addWidget(self.extra_edit)
        layout.addWidget(box)

        # -- how the AI app connects -------------------------------------------
        box = QGroupBox("3. Your AI app")
        column = QVBoxLayout(box)
        self.mode_folders = QRadioButton("Works in folders (recommended)")
        self.mode_folders.setToolTip("The Claude desktop app, Claude Code, "
                                     "Cursor, any agent that reads and "
                                     "writes files.")
        self.mode_mcp = QRadioButton("Uses MCP tools")
        self.mode_mcp.setToolTip("Claude Desktop with MCP servers, other "
                                 "MCP apps.")
        modes = QButtonGroup(self)
        for radio in (self.mode_folders, self.mode_mcp):
            modes.addButton(radio)
            column.addWidget(radio)
        (self.mode_mcp if saved.get("mode") == "mcp"
         else self.mode_folders).setChecked(True)
        self.permissions = QLabel("")
        self.permissions.setWordWrap(True)
        self.permissions.setStyleSheet("color: rgb(110, 90, 20);")
        column.addWidget(self.permissions)
        layout.addWidget(box)

        row = QHBoxLayout()
        self.go_button = QPushButton("Copy the prompt and start")
        self.go_button.setStyleSheet("QPushButton { font-weight: bold;"
                                     " padding: 6px 14px; }")
        self.go_button.clicked.connect(self.copy_and_start)
        self.show_prompt = QPushButton("Show the prompt")
        self.show_prompt.setCheckable(True)
        row.addWidget(self.go_button, stretch=1)
        row.addWidget(self.show_prompt)
        layout.addLayout(row)
        self.prompt_view = QTextEdit()
        self.prompt_view.setReadOnly(True)
        self.prompt_view.setMinimumHeight(220)
        self.prompt_view.setVisible(False)
        self.show_prompt.toggled.connect(self.prompt_view.setVisible)
        layout.addWidget(self.prompt_view)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        about = QLabel(
            "<b>Folders or MCP?</b> <i>Folders</i>: the agent writes small "
            "Python files into the results folder's <i>_agent</i> folder and "
            "this program runs them -- any AI app that can read and write "
            "files, nothing to set up, a record of every step. <i>MCP</i>: "
            "the AI app calls the program's operations as tools through the "
            "agent bridge -- the app is configured once (the prompt tells the "
            "agent how). Both reach the same operations, and in both you see "
            "everything here.")
        about.setWordWrap(True)
        about.setStyleSheet("color: rgb(90, 90, 110);")
        layout.addWidget(about)
        layout.addStretch(1)

        # -- watching ------------------------------------------------------------
        box = QGroupBox("4. Watch and step in")
        column = QVBoxLayout(box)
        # The legend of the light on the main window's AI assistant button,
        # which keeps showing the state with this window closed.
        legend = QLabel(
            "The <b>AI assistant</b> button in the main window is a status "
            "light, also with this window closed (closing it does not stop "
            "the agent): "
            + " &nbsp; ".join(
                f"<span style='color:{LIGHTS[k][0]}'>\u25cf</span> {word}"
                for k, word in (("idle", "not running"), ("running", "running"),
                                ("paused", "paused, you work by hand"),
                                ("error", "error")))
            + ". While the agent works you can still look at the data in the "
              "main window; its own steps leave your selection alone.")
        legend.setWordWrap(True)
        column.addWidget(legend)
        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.pause_button = QPushButton("Pause the agent")
        self.pause_button.setToolTip(
            "Stop running the agent's commands, to work by hand in the "
            "program; they wait until Resume. The agent is told (in its "
            "prompt) to wait and ask when that happens.")
        self.pause_button.clicked.connect(self.toggle_pause)
        open_results = QPushButton("Open results")
        open_results.clicked.connect(self._open_results)
        self.save_button = QPushButton("Save the steps as a script...")
        self.save_button.setToolTip(
            "Write everything the agent ran, in order, as one Python file: "
            "each step's code, when it ran, whether it failed and what it "
            "printed. A record of the whole processing, and a script that "
            "does it again (copied into the command folder's viewer_cmd, "
            "the program runs it). Steps run through MCP are kept in memory "
            "only, so save them before closing the program.")
        self.save_button.clicked.connect(lambda: self.save_script())
        row.addWidget(self.status, stretch=1)
        row.addWidget(self.pause_button)
        row.addWidget(self.save_button)
        row.addWidget(open_results)
        column.addLayout(row)
        split = QSplitter(Qt.Vertical)
        self.steps = QListWidget()
        self.steps.setToolTip("The agent's steps, newest last; click one to "
                              "see what it printed.")
        self.steps.currentItemChanged.connect(self._show_step)
        self.step_log = QTextEdit()
        self.step_log.setReadOnly(True)
        self.step_log.setLineWrapMode(QTextEdit.NoWrap)
        split.addWidget(self.steps)
        split.addWidget(self.step_log)
        split.setMinimumHeight(300)
        split.setSizes([260, 400])
        column.addWidget(split, stretch=1)
        columns.addWidget(box, stretch=6)

        close = QPushButton("Close")
        close.clicked.connect(self.close)
        outer.addWidget(close, alignment=Qt.AlignRight)

        for edit in (self.data_edit, self.results_edit):
            edit.textChanged.connect(self.refresh_prompt)
            edit.editingFinished.connect(lambda e=edit: self._tidy_folder(e))
        self.extra_edit.textChanged.connect(self.refresh_prompt)
        for check in self.option_boxes.values():
            check.toggled.connect(self.refresh_prompt)
        for radio in (self.mode_folders, self.mode_mcp):
            radio.toggled.connect(self.refresh_prompt)
        # MCP: the bridge is on as soon as it is chosen, so the AI app can
        # connect while the person is still setting it up
        self.mode_mcp.toggled.connect(
            lambda on: on and (self._start_bridge(), self.refresh_status()))
        if self.mode_mcp.isChecked():
            self._start_bridge()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(1500)
        self.refresh_prompt()
        self.refresh_status()

    # -- settings --------------------------------------------------------------
    def _load(self) -> dict:
        try:
            with open(_settings_path(), encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {}

    def _save(self):
        data, results = self.folders()
        values = {"data": data, "results": results,
                  "options": self.options(), "mode": self.mode(),
                  "extra": self.extra_edit.toPlainText()}
        try:
            os.makedirs(os.path.dirname(_settings_path()), exist_ok=True)
            with open(_settings_path(), "w", encoding="utf-8") as handle:
                json.dump(values, handle, indent=1)
        except OSError:
            pass

    def _data_folder(self) -> str:
        ui = getattr(self.app, "ui", None)
        text = ui.FilePathLE.text().strip() if ui is not None else ""
        return text

    # -- what is asked for -------------------------------------------------------
    def folders(self):
        """``(data, results)`` as the system writes paths (D:\\Data on
        Windows, whichever slashes were typed or a dialog gave)."""
        return (native(self.data_edit.text().strip()) or "",
                native(self.results_edit.text().strip()) or "")

    def _tidy_folder(self, edit):
        text = edit.text().strip()
        if text and native(text) != text:
            edit.setText(native(text))

    def mode(self) -> str:
        return "mcp" if self.mode_mcp.isChecked() else "folders"

    def options(self) -> list:
        return [key for key, box in self.option_boxes.items() if box.isChecked()]

    def prompt(self) -> str:
        data, results = self.folders()
        return build_prompt(self.mode(), data, results, self.options(),
                            self.extra_edit.toPlainText())

    def refresh_prompt(self, *_):
        self.prompt_view.setPlainText(self.prompt())
        if self.mode() == "mcp":
            self.permissions.setText(
                "Your AI app will ask to add and run the MCP server, and "
                "may ask before each tool call: allow them for this session. "
                "Give it read access to the data folder and write access to "
                "the results folder only.")
        else:
            self.permissions.setText(
                "Your AI app will ask for access: give it the results folder "
                "(read and write; the commands go in its _agent folder) and "
                "the data folder (read only). Reading the program's own "
                "reference (API.md, in its installation) helps; without it "
                "the agent prints the same list with L.help().")

    # -- starting -------------------------------------------------------------------
    def copy_and_start(self):
        """Check the folders, start the command folder (route 3) or the
        bridge (MCP), copy the prompt. Returns the prompt, or None."""
        data, results = self.folders()
        if not data or not os.path.isdir(data):
            self.message.setText("<span style='color:#c00'>Choose the data "
                                 "folder first (an existing folder).</span>")
            return None
        if not results:
            self.message.setText("<span style='color:#c00'>Choose a results "
                                 "folder first.</span>")
            return None
        if os.path.abspath(results) == os.path.abspath(data):
            self.message.setText("<span style='color:#c00'>The results folder "
                                 "must not be the data folder.</span>")
            return None
        os.makedirs(results, exist_ok=True)
        if self.mode() == "mcp":
            self._start_bridge()
        else:
            self._start_folder(results, data)
        text = self.prompt()
        QApplication.clipboard().setText(text)
        self._save()
        self.message.setText(
            "<b>Copied.</b> Paste it into your AI app and send. Its steps "
            "appear below, its results in the list.")
        self.refresh_status()
        return text

    def _start_folder(self, results: str, data: str):
        from arpes_viewer.ui.common.agentfolder import CommandFolder
        folder = command_folder_of(results)
        running = getattr(self.app, "_command_folder", None)
        if running is not None and running.running and running.folder == os.path.abspath(folder):
            return running
        if running is not None:
            running.stop()
        started = CommandFolder(self.app, folder, data).start()
        self.app._command_folder = started
        return started

    def _start_bridge(self):
        from arpes_viewer.ui.common import agentbridge
        if getattr(self.app, "_agent_bridge", None) is None:
            self.app._agent_bridge = agentbridge.start(
                self.app, getattr(self.app, "win", None))
        return self.app._agent_bridge

    # -- watching -----------------------------------------------------------------------
    def toggle_pause(self):
        """Pause: the agent's commands wait (the folder is not polled, or
        the bridge refuses with "paused"); Resume lets them through."""
        folder = getattr(self.app, "_command_folder", None)
        bridge = getattr(self.app, "_agent_bridge", None)
        paused = bool(getattr(self.app, "_agent_paused", False))
        if paused:
            if folder is not None:
                folder.start()
            if bridge is not None:
                bridge.paused = False
            self.app._agent_paused = False
        else:
            if folder is not None and folder.timer is not None:
                folder.timer.stop()
            if bridge is not None:
                bridge.paused = True
            self.app._agent_paused = True
        self.refresh_status()

    def _steps(self):
        """``[(time, name, failed, log path)]`` of the commands run."""
        folder = getattr(self.app, "_command_folder", None)
        if folder is None:
            return []
        done = os.path.join(folder.folder, "viewer_done")
        out = []
        try:
            names = os.listdir(done)
        except OSError:
            return []
        for name in names:
            path = os.path.join(done, name)
            log = os.path.join(folder.folder, "out",
                               "cmd_" + os.path.splitext(name)[0] + ".log")
            failed = False
            try:
                with open(log, encoding="utf-8", errors="replace") as handle:
                    failed = "Traceback (most recent call last)" in handle.read()
            except OSError:
                pass
            out.append((os.path.getmtime(path), name, failed, log))
        return sorted(out)

    def _bridge_steps(self):
        bridge = getattr(self.app, "_agent_bridge", None)
        return list(getattr(bridge, "history", []) or [])

    def refresh_status(self):
        folder = getattr(self.app, "_command_folder", None)
        bridge = getattr(self.app, "_agent_bridge", None)
        paused = bool(getattr(self.app, "_agent_paused", False))
        state, words = agent_state(self.app)
        parts = [f"<span style='color:{LIGHTS[state][0]}; font-size: 15px'>"
                 f"\u25cf</span> {words}"]
        if folder is not None:
            parts.append(f"Commands from {os.path.basename(os.path.dirname(folder.folder)) or folder.folder}"
                         f"/_agent: {folder.ran} run.")
        if bridge is not None:
            parts.append(f"Bridge on 127.0.0.1:{bridge.serverPort()}.")
        self.status.setText("<br>".join(parts))
        light = getattr(self.app, "_status_light", None)
        if light is not None:
            light.update()
        self.pause_button.setText("Resume" if paused else "Pause the agent")
        self.pause_button.setEnabled(folder is not None or bridge is not None)

        entries = []
        for stamp, name, failed, log in self._steps():
            entries.append((f"{time.strftime('%H:%M:%S', time.localtime(stamp))}  "
                            f"{'✗' if failed else '✓'}  {name}", log, failed))
        for stamp, op, ok, detail in self._bridge_steps():
            entries.append((f"{time.strftime('%H:%M:%S', time.localtime(stamp))}  "
                            f"{'✓' if ok else '✗'}  {op}  {detail}", None, not ok))
        if len(entries) != self.steps.count():
            self.steps.clear()
            for text, log, failed in entries:
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, log)
                if failed:
                    item.setForeground(Qt.red)
                self.steps.addItem(item)
            if entries:
                self.steps.setCurrentRow(len(entries) - 1)

    def _show_step(self, item, _previous=None):
        if item is None:
            return
        log = item.data(Qt.UserRole)
        if not log:
            self.step_log.setPlainText(item.text())
            return
        try:
            with open(log, encoding="utf-8", errors="replace") as handle:
                self.step_log.setPlainText(handle.read()[-20000:])
        except OSError:
            self.step_log.setPlainText("(no output yet)")

    # -- helpers ------------------------------------------------------------------------
    def _browse(self, edit):
        path = QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                edit.text())
        if path:
            edit.setText(native(path))

    def save_script(self, path: str = ""):
        """Write the agent's steps as one Python script (asks where when
        no ``path`` is given). Returns what :func:`agentsteps.save` does,
        or None."""
        from arpes_viewer.ui.common import agentsteps
        if not agentsteps.steps(self.app):
            self.message.setText("No step has been run yet: there is "
                                 "nothing to save.")
            return None
        if not path:
            start = self.folders()[1] or os.path.expanduser("~")
            path, _ = QFileDialog.getSaveFileName(
                self, "Save the agent's steps as a script",
                os.path.join(start, agentsteps.default_name()),
                "Python (*.py)")
        if not path:
            return None
        try:
            saved = agentsteps.save(self.app, path)
        except OSError as exc:
            self.message.setText(f"<span style='color:#c00'>Could not save: "
                                 f"{exc}</span>")
            return None
        failed = (f" ({saved['failed']} failed, kept as comments)"
                  if saved["failed"] else "")
        self.message.setText(f"<b>Saved</b> {saved['steps']} step(s){failed} "
                             f"to {native(saved['path'])}")
        return saved

    def _open_results(self):
        folder = self.folders()[1]
        if folder:
            os.makedirs(folder, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def closeEvent(self, event):
        self._save()
        self.timer.stop()
        super().closeEvent(event)
