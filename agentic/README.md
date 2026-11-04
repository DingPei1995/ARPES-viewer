# Letting an AI agent process your ARPES data

This folder is the starting point for using an AI agent (Claude, GPT,
Gemini, a local model...) with ARPES viewer. The agent does the work: it
opens the files, fits the Fermi edge, converts to momentum, makes the
figures. You check the results. **Your data never leaves your computer**:
the program runs on your machine, the agent drives it, and you see every
step in the program's own window.

---

## Contents

0. [Whom do I talk to?](#0-whom-do-i-talk-to)
1. [Which route?](#1-which-route)
2. [Route 3 — the agent drives the program on your screen (recommended)](#2-route-3--the-agent-drives-the-program-on-your-screen-recommended)
3. [How the agent knows what the program can do](#3-how-the-agent-knows-what-the-program-can-do)
4. [Route 1 — an MCP app](#4-route-1--an-mcp-app)
5. [Route 2 — scripts written by a coding agent](#5-route-2--scripts-written-by-a-coding-agent)
6. [Good habits](#6-good-habits)
7. [When something goes wrong](#7-when-something-goes-wrong)
8. [Words used here](#8-words-used-here)
9. [What is in this folder](#9-what-is-in-this-folder)

---

## 0. Whom do I talk to?

**To your AI app** — the Claude desktop app, Claude Code, or any agent that
can read and write files — in plain words:

> Today I process the kz maps in `D:/data/beamtime_2026/sampleA`. Let's
> start.

The program has no chat of its own. It is the agent's **tool**: the agent
sends it commands, the program carries them out in its window, and you can
look, check, and take over at any moment.

The quickest way in: start ARPES viewer, press **AI assistant...** (top of
the main window). That window starts everything the agent needs and gives
you a first message to paste into your AI app (§2.1).

---

## 1. Which route?

| Your situation | Route |
|---|---|
| You use an AI app that can read and write a folder on your computer (Claude desktop app, Claude Code, Cursor...) — **most people** | **Route 3** (§2), recommended: the agent drives the program on your screen |
| Your app speaks MCP and you prefer tools to files | Route 1 (§4), with the program open (`--agent-bridge`) it can do the same as route 3 |
| You want a Python script that processes a whole beamtime the same way, to keep and re-run | Route 2 (§5), a coding agent writes it |

If unsure, **take route 3**. All three reach the same documented operations
(§3); they differ only in how the agent's commands travel.

Install the program once (Python 3.9 or newer):

```bash
pip install arpes-viewer
```

No data at hand? `python devtools/demo_data.py demo_data` (from a
downloaded copy of the repository) writes synthetic demo data, which makes
no claim about any real material.

---

## 2. Route 3 — the agent drives the program on your screen (recommended)

The program watches a **command folder**. The agent writes a small Python
file into its `viewer_cmd/` sub-folder; the program runs it in its window,
writes what it printed to `out/cmd_<name>.log`, and moves the file to
`viewer_done/` — a record of every step.

Why this route:

- **Everything the program does is reachable**, not a subset.
- **You and the agent work in the same window**, on the same list of data:
  you see each result appear, and can open, check or correct anything by
  hand.
- **No configuration**: any agent that can read and write files works.
- **A record**: `viewer_done/` and `out/` hold every command and its output.

### 2.1 Start it (from the program — the easy way)

1. Start ARPES viewer (`arpes-viewer`) and press **AI assistant...**.
2. **1. Let the agent drive this window**: choose the command folder (by
   default `agentic/` of the repository, or `~/arpes_agent`) and press
   **Start**. The program writes `API.md` into it — the list of everything
   it can do — and says *Listening*.
3. Give your AI app access to that folder (Claude desktop app: add the
   folder to the conversation or project).
4. **2. Paste this into your AI app**: set today's data folder, press **Copy
   the message**, paste it into your AI app, and send. The message tells the
   agent where to write, to read `API.md` first, and the working rules.

### 2.2 Start it from a script (unattended, or on a second screen)

1. Copy `config.example.json` to `config.json` and set `data_dir` to your
   data folder (`patterns` selects which files are listed; `screen` which
   monitor the window opens on).
2. Run `python agentic/launch_viewer.py`. The window opens with your data
   listed and the command folder (this folder) listening.
3. Optional, for jobs without a window: `agentic/agent_runner.pyw` runs the
   files dropped into `queue/` (a file named `STOP` stops it).

### 2.3 What a command file looks like

```python
# viewer_cmd/03_fermi_and_k.py
fit = L.fermi_edge("FS_cut_LH", energy_window=(-0.15, 0.10), temperature=30)
print(fit["values"]["ef"], fit["errors"]["ef"], fit["reduced_chi2"])
cut = L.shift_energy("FS_cut_LH", ef=fit["values"]["ef"])
k = L.cut_to_k(cut, gamma_slit_deg=0.8)      # Γ: asked of the person, never guessed
print(L.picture(k, 0, 1, path=HERE + "/shots/03_cut_k.png"))
```

`L` is the program (§3). Also there: `HERE` (the command folder), `DATA`
(the data folder, when started from a script), `A` (the program's module,
for what `L` does not cover), `QtCore`, `QtWidgets`, `np`.

A command never hangs the program: a modal dialog it would open raises
`ModalDialogBlocked`, a warning is printed into the log instead.

### 2.4 Its limits

- The agent waits for each log (a second or so per command); a long
  conversion is one command.
- Python runs inside the program: connect only an agent you trust.
- `recipes/` holds command files from real sessions. They were written
  before `L` existed and reach into the program's internals, which can
  change between versions: read them as examples of a session, and prefer
  the operations of §3 for new work.

The detailed guide, with a complete session, the rules to give the agent
and the pitfalls met, is
[`docs/AGENTIC_WORKFLOW_en.md`](../docs/AGENTIC_WORKFLOW_en.md).

---

## 3. How the agent knows what the program can do

Not by reading the source or by pressing buttons by their text — that is
slow, costs many tokens and breaks when a window changes. The program
describes itself:

| Where | What |
|---|---|
| **[`API.md`](API.md)** (here, and written into every command folder) | Everything, in one file: about 50 operations `L.<name>(...)` with their parameters and what they return, a table of which operation for which step, the tool-panel windows, the MCP tools, and the program's computations |
| `L.help()` | The same operations, one line each, inside the program; `L.help("kz_to_k")` one in full; `L.help("Figures")` one group |
| `L.tools()` | The tool windows, for what has no operation (MDC/EDC fits, core levels, tight-binding, calculated bands, 3-D views): `L.run_tool("mdcfit", "cut1")` opens one |
| `L.functions("spectra.peaks")` | The program's own computations in a module, for a calculation of the agent's own on `L.data(row)`; the result goes back to the list with `L.add(...)` |

The operations keep a few rules, so the agent cannot quietly do harm:
rows are named, never guessed; each result is a **new** row with its
history recorded; files are never overwritten; nothing waits for a click.

`API.md` is generated from the program (`python -m
arpes_viewer.agent.catalog --write`) and a test fails when it falls behind,
so it always matches the version you run.

---

## 4. Route 1 — an MCP app

**MCP** (Model Context Protocol) is a standard way for an AI app to call
tools. Installing ARPES viewer installs the command `arpes-viewer-mcp`.

### 4.1 Connect it (once)

The **AI assistant** window's **Copy the MCP settings** gives the entry with
the right Python. Or by hand:

**Claude Desktop.** *Settings → Developer → Edit Config* opens
`claude_desktop_config.json`; put this in it and restart:

```json
{"mcpServers": {"arpes-viewer": {"command": "arpes-viewer-mcp"}}}
```

**Claude Code**: `claude mcp add arpes-viewer -- arpes-viewer-mcp`.
**Another app**: add an MCP server whose command is `arpes-viewer-mcp`.
If the app cannot find it, give the full Python path with `"args": ["-m",
"arpes_viewer.agent"]` (`where python` / `which python` shows it).

### 4.2 With the program on screen (recommended for this route)

Start the program with `arpes-viewer --agent-bridge` (or **Start the
bridge** in the AI assistant window). The app then has
`viewer_api_help` (the operations of §3) and `viewer_api` (call one: the
same `L` as route 3), plus `viewer_figure`, `viewer_render_figure`,
`viewer_screenshot`, `viewer_python` and the list tools. The bridge listens
on your computer only, to the agent that can read its key file.

### 4.3 Without the program on screen

About twenty headless tools: `find_files`, `open_dataset`, `describe`,
`metadata`, `get_profile`, `get_image`, `fit_fermi_edge`, `shift_energy`,
`crop`, `convert_cut_to_k`, `convert_map_to_k`, `save_datasets`,
`brillouin_zone`, `read_cif` (all listed in `API.md`, section 3). Enough for
a first look, a Fermi edge and a momentum conversion; for kz conversion, BZ
overlays and figures, use the program on screen.

---

## 5. Route 2 — scripts written by a coding agent

For a script to keep: the same steps on every dataset of a beamtime, re-run
on the next sample. A coding agent (Claude Code in a copy of this
repository) writes it with the headless workspace
(`arpes_viewer.agent.workspace.Workspace`) and the program's computations
(`API.md`, section 4), runs it, looks at the pictures, and improves it.

| Script | What it shows |
|---|---|
| [`examples/01_first_look.py`](examples/01_first_look.py) | What is in a folder; open a cut; its axes; a picture and an EDC |
| [`examples/02_cut_to_momentum.py`](examples/02_cut_to_momentum.py) | Fermi edge → E − E_F → momentum → picture and `.nxs` |
| [`examples/03_fermi_surface.py`](examples/03_fermi_surface.py) | A map: Fermi edge → (kx, ky) → constant-energy pictures |

```bash
python agentic/examples/02_cut_to_momentum.py  D:/data/my_beamtime  D:/results
```

> Read `agentic/README.md`, `agentic/API.md` and
> `agentic/examples/02_cut_to_momentum.py`. Then write `my_analysis.py`
> that does the same for every cut in `D:/data/my_beamtime` whose name
> contains `LH`. Ask me for the Γ angle and the temperature before running
> it. Run it on two cuts first and show me the pictures.

---

## 6. Good habits

- **Give the physics yourself.** Where Γ is, the sample temperature, the
  photon energy, the inner potential: the agent should ask you, not guess.
- **One figure first.** Agree on one figure (panel sizes, text size, colour
  scale) before the agent makes a family of them.
- **Numbers, not screenshots.** Ask for `L.figure_describe` and
  `L.figure_render`, the fit window and the residual of every fit.
- **Keep the originals.** Results are new rows or new files; say "do not
  delete or overwrite anything" to be sure.
- **Small steps.** One dataset, checked, then the rest.
- **Same symbol, same frame.** The 3D BZ window's k_a, k_b, k_c are the
  crystal's axes; the data's kx, ky, kz are the sample's.
- **Before publishing**, check what the agent produced as you would a
  student's analysis; for papers related to AI, see the README's terms of
  use.

---

## 7. When something goes wrong

| What you see | What to do |
|---|---|
| Nothing appears in `out/` | The command folder is not listening: AI assistant window → *Start* (or `launch_viewer.py`); `heartbeat.txt` in the folder shows the last poll |
| `ModalDialogBlocked` in a log | The command opened a dialog that would wait for a click: use the operation instead (`L.help()`) |
| `KeyError: ... matches several rows` | Give the row's whole name (`L.rows()`) |
| `FileExistsError` | Results are never written over: give a new file name |
| "no Fermi edge found" | The data were normalised, or the window misses the edge: fit the raw data around E_F |
| The MCP app does not list the tools | Restart the app after editing its config; check the JSON; use the full Python path (§4.1) |
| `No module named arpes_viewer` | The app runs another Python: give the one where you ran `pip install arpes-viewer` |
| The program reports an error | Its log is in `~/.arpes_viewer/error_logs/`; a bug report with it is welcome on GitHub Issues |

---

## 8. Words used here

- **Agent**: an AI model that can use tools — write files, run programs —
  not only write text.
- **Command folder**: the folder the program watches for the agent's
  commands (route 3).
- **`L`**: the program, as the agent sees it: its documented operations.
- **MCP server**: a small program that offers tools to an agent in a
  standard way; `arpes-viewer-mcp` is ARPES viewer's.
- **Headless**: computing with no window on screen.
- **Row**: one dataset in the program's main list, named.

---

## 9. What is in this folder

| File | For |
|---|---|
| `README.md` | This guide |
| `API.md` | The agent's reference: every operation (generated from the program) |
| `PROMPTS.md` | Requests to copy into the chat, from the first message to a figure |
| `launch_viewer.py`, `viewer_live.py` | Route 3 from a script: the window, with this folder listening |
| `config.example.json` | Route 3 from a script: copy to `config.json` and edit |
| `agent_runner.pyw` | Route 3: jobs without a window, from `queue/` |
| `recipes/` | Route 3: command files from real sessions |
| `examples/` | Route 2: three runnable scripts |

The working folders (`out/`, `shots/`, `viewer_cmd/`, ...) and your
`config.json` stay on your computer: they are not part of the repository.
