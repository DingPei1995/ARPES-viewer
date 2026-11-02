# Letting an AI agent process your ARPES data

This folder is the starting point for using an AI agent (Claude, GPT,
Gemini, a local model...) with ARPES viewer. The agent does the work: it
opens the files, fits the Fermi edge, converts to momentum, makes the
pictures. You check the results. **Your data never leaves your computer**:
the agent runs the program on your machine and sees only what the program
reports back to it — numbers, text and pictures you can check.

No programming is needed for route 1 below. Routes 2 and 3 are for when you
want scripts you can keep and re-run.

---

## Contents

1. [Which route?](#1-which-route)
2. [Route 1 — the MCP server (start here)](#2-route-1--the-mcp-server-start-here)
3. [Route 2 — scripts written by a coding agent](#3-route-2--scripts-written-by-a-coding-agent)
4. [Route 3 — the live viewer driven through folders](#4-route-3--the-live-viewer-driven-through-folders)
5. [Good habits](#5-good-habits)
6. [When something goes wrong](#6-when-something-goes-wrong)
7. [Words used here](#7-words-used-here)
8. [What is in this folder](#8-what-is-in-this-folder)

---

## 1. Which route?

| You want to... | Use | You need |
|---|---|---|
| Ask in plain words ("fit the Fermi edge of this cut") and get the answer | **Route 1: MCP** | An AI app that supports MCP (Claude Desktop, Claude Code, Cursor, ...) |
| Have the agent watch and drive the program's window on your screen | **Route 1 + `--agent-bridge`** | The same, with the program open |
| Get a Python script that processes a whole beamtime the same way, and can be run again | **Route 2: scripts** | A coding agent (Claude Code, or any agent that can run Python) |
| Use an agent that can only read and write files in a folder | **Route 3: live viewer** | An agent with file access to this folder |

If unsure, **take route 1**.

Before any route, install the program once (Python 3.9 or newer):

```bash
pip install arpes-viewer
```

No data at hand? Every example here can use the program's synthetic demo
data, which makes no claim about any real material:

```bash
python devtools/demo_data.py demo_data
```

(run it from a downloaded copy of the repository; the example scripts below
write it for you if no data folder is given).

---

## 2. Route 1 — the MCP server (start here)

**MCP** (Model Context Protocol) is a standard way for an AI app to call
tools on your computer. Installing ARPES viewer also installs the command
`arpes-viewer-mcp`, which offers the program's operations to the agent as
tools.

### 2.1 Connect it (once)

**Claude Desktop.** Open *Settings → Developer → Edit Config*. This opens
`claude_desktop_config.json` (on macOS in `~/Library/Application
Support/Claude/`, on Windows in `%APPDATA%\Claude\`). Put this in it and
restart Claude Desktop:

```json
{
  "mcpServers": {
    "arpes-viewer": {"command": "arpes-viewer-mcp"}
  }
}
```

**Claude Code** (in a terminal):

```bash
claude mcp add arpes-viewer -- arpes-viewer-mcp
```

**Another app** (Cursor, Windsurf, an open-source client with a local
model, ...): find "MCP servers" in its settings and add a server whose
command is `arpes-viewer-mcp`.

**If the app says it cannot find `arpes-viewer-mcp`**, give the full path
of the Python that has the program installed instead:

```json
{"mcpServers": {"arpes-viewer": {
  "command": "C:\\Users\\you\\miniconda3\\python.exe",
  "args": ["-m", "arpes_viewer.agent"]}}}
```

(`where python` on Windows, `which python` on macOS / Linux, shows the
path; with a conda environment, activate it first.)

### 2.2 Check it works

Ask the agent:

> List the ARPES viewer tools you can use, then list the datasets in the
> folder `D:/data/demo_data`.

It should answer with the tools (below) and the datasets it found.

### 2.3 What the agent can do

Without a window (always available):

| Tool | What it does |
|---|---|
| `find_files`, `list_loaders` | Which files in a folder the program can open, and what is in them |
| `open_dataset`, `describe`, `metadata`, `list_datasets`, `close_dataset` | Open a dataset; its axes, size and metadata |
| `get_profile`, `get_image` | An EDC / MDC as numbers, or a picture the agent can look at |
| `fit_fermi_edge`, `shift_energy` | Fit the Fermi edge; put the energy axis on E − E_F |
| `crop`, `convert_cut_to_k`, `convert_map_to_k` | Crop; convert a cut or a map to momentum |
| `save_datasets` | Save as `.nxs` (the program opens it) or for Igor Pro |
| `brillouin_zone`, `read_cif` | High-symmetry points of a crystal; a CIF file's structure |

With the program open on screen, started as

```bash
arpes-viewer --agent-bridge
```

the agent can also drive the window: `viewer_status`, `viewer_rows`,
`viewer_add_files`, `viewer_select`, `viewer_run_tool` (any button of the
tool panel), `viewer_screenshot`, `viewer_close_window`, and
`viewer_python` (runs Python inside the program, so only connect an agent
you trust). The bridge listens on your own computer only, and only to the
agent that can read its random key file.

### 2.4 First requests to try

Copy these into the chat, with your own folder. More in
[PROMPTS.md](PROMPTS.md).

> Open the first cut in `D:/data/demo_data`, tell me its axes, and show me
> a picture of it.

> Fit the Fermi edge of that cut at 30 K. Tell me E_F, the resolution and
> their errors, and show me the fit window you used.

> Put the cut on E − E_F and convert it to momentum. Normal emission is at
> slit angle 0°. Show me the result and save it as `cut_k.nxs` in the same
> folder.

The full description is in the user guide,
[§33](../docs/USER_GUIDE_en.md#33-driving-the-program-from-an-ai-agent-mcp).

---

## 3. Route 2 — scripts written by a coding agent

Everything the MCP tools do is plain Python, without a window:
`arpes_viewer.agent.workspace.Workspace`. A coding agent (Claude Code, for
example, opened in a copy of this repository) can write a script with it,
run it, look at the pictures it made, and improve it. You keep the script
and can run it again on the next sample.

### 3.1 The three examples

Start from these; each runs as it is, on the demo data if you give no
folder:

| Script | What it shows |
|---|---|
| [`examples/01_first_look.py`](examples/01_first_look.py) | What is in a folder; open a cut; its axes; a picture and an EDC |
| [`examples/02_cut_to_momentum.py`](examples/02_cut_to_momentum.py) | Fermi edge → E − E_F → momentum → picture and `.nxs` |
| [`examples/03_fermi_surface.py`](examples/03_fermi_surface.py) | A map: Fermi edge → (kx, ky) → constant-energy pictures |

```bash
python agentic/examples/01_first_look.py
python agentic/examples/02_cut_to_momentum.py  D:/data/my_beamtime  D:/results
```

The results go to `agentic/out/example_NN/` unless you name an output
folder. The parameters an agent cannot know (where Γ is, the temperature)
are at the top of each script: a script you ask an agent for should look
the same.

### 3.2 Asking for a script

> Read `agentic/README.md` and `agentic/examples/02_cut_to_momentum.py`.
> Then write `my_analysis.py` that does the same for every cut in
> `D:/data/my_beamtime` whose name contains `LH`, saves one picture per cut
> and one `.nxs` with all the results. Ask me for the Γ angle and the
> temperature before running it. Run it on two cuts first and show me the
> pictures.

### 3.3 Going further

The examples use the workspace; the program's full set of operations is in
`arpes_viewer/tools/` (the technical references in each folder's
`README.md` say what each does and assumes). `devtools/figure_tests.py`
builds a whole publication figure (calculated bands, notched cube, figure
composer) from the demo data and is the longest worked script.

---

## 4. Route 3 — the live viewer driven through folders

For an agent that can only read and write files (for example the Claude
desktop app linked to a folder of your computer). The program's window
runs on your screen; the agent drops small Python files into
`viewer_cmd/`, the window runs them, and the printed output and
screenshots come back in `out/` and `shots/`.

1. Copy `config.example.json` to `config.json` and set `data_dir` to your
   data folder (`patterns` selects which files are listed; `screen` which
   monitor the window opens on).
2. Run `python agentic/launch_viewer.py`. The window opens with your data
   listed; the working folders are created on first start.
3. Optional, for jobs without a window: run `agentic/agent_runner.pyw`
   (double-click on Windows); it runs the files dropped into `queue/`.
   Create a file named `STOP` here to stop it.

Inside a command file, `A` is the program (`arpes_viewer.app`), `HERE`
this folder and `DATA` the data folder. A one-line test:

```python
print(len(A.loaded_items), "datasets listed")
```

`recipes/` holds four command files from a real session (normalise, cut k
conversion with a Fermi fit, an arbitrary cut from a map, a two-peak MDC
fit). They call the program's internal functions, which can change between
versions: check each on one dataset first. The detailed guide, with a
complete session, the rules to give the agent and the pitfalls met, is
[`docs/AGENTIC_WORKFLOW_en.md`](../docs/AGENTIC_WORKFLOW_en.md).

---

## 5. Good habits

- **Give the physics yourself.** Where Γ is, the sample temperature, the
  photon energy, the inner potential: the agent should ask you, not guess.
  Say so at the start ("ask me before choosing any physical parameter").
- **Look at every picture** the agent makes before using its numbers, and
  ask for the fit window and the residual of every fit.
- **Keep the originals.** Results are new datasets or new files; say "do
  not delete or overwrite anything" if you want to be sure.
- **Small steps first.** One dataset, checked, then the rest.
- **Keep the script.** With route 2, ask for the script that made a figure,
  so it can be re-run and checked later.
- **Before publishing**, check what the agent produced as you would a
  student's analysis; for papers related to AI, see the README's terms of
  use.

---

## 6. When something goes wrong

| What you see | What to do |
|---|---|
| The app does not list the ARPES viewer tools | Restart the app after editing its config; check the JSON (commas, quotes); use the full Python path (§2.1) |
| `No module named arpes_viewer` | The app runs a different Python: give the full path of the one where you ran `pip install arpes-viewer` |
| "The viewer is not running with the agent bridge" | Start the program with `arpes-viewer --agent-bridge`, or use the tools without a window |
| A file is not found | Give full paths; on Windows, forward slashes (`D:/data/...`) avoid escaping problems |
| A fit or conversion looks wrong | Ask the agent to show the picture and the parameters it used, and give the physical parameters yourself |
| The program itself reports an error | Its log is in `~/.arpes_viewer/error_logs/`; a bug report with that file is welcome on GitHub Issues |

---

## 7. Words used here

- **Agent**: an AI model that can use tools — run programs, read files —
  not only write text.
- **MCP server**: a small program that offers tools to an agent in a
  standard way. `arpes-viewer-mcp` is ARPES viewer's.
- **Headless / without a window**: the program's computations run with no
  window on screen.
- **Workspace**: the headless part of the program that the MCP tools and
  the example scripts use (`arpes_viewer.agent.workspace`).
- **Dataset id** (`d1`, `d2`...): the short name the agent uses for a
  dataset it has opened.

---

## 8. What is in this folder

| File | For |
|---|---|
| `README.md` | This guide |
| `PROMPTS.md` | Requests to copy into the chat, from first steps to a figure |
| `examples/` | Three runnable scripts for route 2 (`_common.py` only finds the program and the demo data for them) |
| `launch_viewer.py`, `viewer_live.py` | Route 3: the window driven through `viewer_cmd/` |
| `agent_runner.pyw` | Route 3: jobs without a window, from `queue/` |
| `config.example.json` | Route 3: copy to `config.json` and edit |
| `recipes/` | Route 3: command files from a real session |

The working folders (`out/`, `shots/`, `viewer_cmd/`, ...) and
`config.json` stay on your computer: they are not part of the repository.
