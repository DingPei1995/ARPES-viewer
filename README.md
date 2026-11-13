# ARPES viewer

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23771647.svg)](https://doi.org/10.5281/zenodo.23771647)
[![PyPI version](https://img.shields.io/pypi/v/arpes-viewer.svg)](https://pypi.org/project/arpes-viewer/)
[![User Guide](https://img.shields.io/badge/📖_User_Guide-English-blue?style=flat-square)](https://github.com/DingPei1995/ARPES-viewer/blob/main/docs/USER_GUIDE_en.md)
[![Local Agent Settings](https://img.shields.io/badge/🤖_Local_Agent_Settings-blue?style=flat-square)](https://github.com/DingPei1995/ARPES-viewer/blob/main/docs/AGENTIC_WORKFLOW_en.md)

**Version 1.3.4** (last modified 13 November 2026) -- what changed is in
[CHANGELOG.md](CHANGELOG.md). For non-commercial use only; see the
[terms of use](#terms-of-use-citation-and-licence).

A Python/PyQt5 program for ARPES data: browse the measurements of a
beamtime, open them in their own windows, convert to momentum, cut, fit,
process, compare with a band-structure calculation, and lay the results out
as a publication figure.

> **A note from the author on AI agents.** Talking with beamline users, I
> heard two concerns again and again: running an AI agent on local data
> is unfamiliar, and the data might end up with an AI company and be used
> for training. The **AI assistant** panel (top of the tool panel) is my
> answer to the first. Choose the data folder and the results folder,
> tick a few options, and it writes the prompt to paste into your AI app.
> No configuration and no manual to read first. Every step the agent runs
> is listed with its code and output, a status light shows its state, and
> **Pause** hands the controls back to you at any time
> ([how it works](#starting-and-watching-an-agent-from-the-ai-assistant-panel)).
> On the second concern: the raw data files stay on your computer and are
> processed there. What the agent *reads* is sent to the AI provider as
> part of the conversation: printed results, fitted values, and the
> pictures it inspects to judge a step. Whether that is used for training
> depends on your provider and your account settings, so check them.
> Keep private code out of any folder the agent can reach. In my view, AI
> in ARPES experiments and analysis is here to stay. An experiment update
> prepared by the agent, which you check step by step, is a low-risk way
> to get familiar with it.

---

## What it does

- **Reads** SOLEIL ANTARES and CASSIOPEE, ALS MAESTRO, ALBA LOREA, Diamond I05 and I05-1, MAX IV
  Bloch, Elettra APE, BESSY One Cube / One Square, SOLARIS URANOS, ASTRID2
  SGM4, and its own saved format ([loading data](docs/USER_GUIDE_en.md#22-loading-data)).
- **Shows** cuts, Fermi-surface maps, photon-energy scans, spatially resolved
  scans and spin-resolved curves, each in its own window with linked cursors
  ([the viewers](docs/USER_GUIDE_en.md#31-what-the-viewers-have-in-common)).
- **Converts** maps and cuts to momentum, photon-energy scans to k_z, with the
  Brillouin zone drawn over them
  ([§4.9](docs/USER_GUIDE_en.md#49-converting-a-map-to-momentum),
  [§4.10–4.11](docs/USER_GUIDE_en.md#410-aligning-the-fermi-levels-of-a-kz-map),
  [§4.12](docs/USER_GUIDE_en.md#412-brillouin-zone)).
- **Analyses**: Fermi-edge fits, Fermi-surface correction, MDC / EDC fits
  and the self-energy, ridge detection, curvature, second derivatives and
  the minimum gradient, dichroism, core levels, spin, de-gridding, detector
  corrections, and the Fermi pockets of quasi-two-dimensional samples
  (under test)
  ([Parts 3–5](docs/USER_GUIDE_en.md#part-3--the-data-viewers)).
- **Compares with theory**: crystal structures, tight-binding fits, and
  calculated bands from Wien2k, VASP, Quantum ESPRESSO, Wannier90 and the
  FPLO + Wannier tools -- along a path, as constant-energy contours on any
  (hkl) plane, or as a 3-D Fermi surface
  ([§6.2–6.5](docs/USER_GUIDE_en.md#65-calculated-bands)).
- **Makes figures**: the figure composer, laid out like a manuscript page,
  exported as PNG, PDF or SVG, and saved with its data
  ([§6.1, 6.6](docs/USER_GUIDE_en.md#61-the-figure-composer)).
- **Loses nothing**: every derived dataset is autosaved, a crash is recovered
  from, and long steps show a progress bar
  ([§8.1](docs/USER_GUIDE_en.md#81-autosave-memory-and-recovery)).

---

## Installing and starting

Needs Python 3.9+. With pip, which installs PyQt5, pyqtgraph, numpy,
h5py and scipy with it:

```
pip install arpes-viewer
arpes-viewer
```

(`python -m arpes_viewer` does the same; for the latest, unreleased
version: `pip install git+https://github.com/DingPei1995/ARPES-viewer`.)

From a downloaded copy of this repository, with those packages installed:

```
python ARPES_viewer.py
```

- **Windows:** double-click **`ARPES viewer.pyw`** in this folder: no
  console window to close by mistake (the output goes to
  `~/.arpes_viewer/launcher.log`).
- **macOS:** double-click **`ARPES viewer.app`** in this folder. It finds a
  Python that has the packages (conda included), remembers it, and says what
  to install if none has. The first time, if macOS calls it an app from an
  unidentified developer: **System Settings → Privacy & Security → Open
  Anyway**.
- **No beamtime at hand?** `python devtools/demo_data.py` writes the
  synthetic demo data of the example figures below to `demo_data/`
  ([trying it with demo data](docs/USER_GUIDE_en.md#13-trying-it-with-demo-data)).

---

## From raw data to a publication figure

![Example figure 1: a notched cube, measured and calculated constant-energy contours, stacked contours](docs/images/example_figure_1.png)

> **These are not real experimental data.** Every panel above is made from
> the program's **synthetic demo data** (`devtools/demo_data.py`): an
> invented tight-binding toy model -- a triangular lattice, a = 3.3 Å,
> stacked with c = 6 Å, a few bands with orbital labels and a k_z
> dispersion -- turned into spectra with a Fermi-Dirac cut-off, the
> analyser resolution and Poisson counting noise, and written as beamline
> files. The "calculation" in panel (b) is the same toy Hamiltonian made
> deliberately 1/0.8 times wider and 50 meV higher, so that comparing it
> with the "measurement" has something to find. **No published data or
> literature were used to generate them**: the model and its parameters are
> invented, and names such as "Se-pxy" or "1T-TiSe₂-like" are labels for the
> toy, not a description of a real material. (The only tabulated values in
> the demo set are the X-ray line energies of its synthetic EDS spectrum,
> standard emission energies as listed in the X-ray Data Booklet; that
> spectrum is not part of this figure.)

<p align="center">
  <img src="docs/images/composer_colour_bar.png" width="96%"
       alt="Example figure 1 in the figure composer, its colour bar being set">
</p>
<p align="center">
  <img src="docs/images/main_window_advanced.png" width="50%"
       alt="The main panel: the beamtime's datasets and the tools for the selected ones">
  <img src="docs/images/map_k_contour.png" width="47%"
       alt="A Fermi-surface map converted to momentum, in its viewer">
</p>
<p align="center"><sub>Example figure 1 in the figure composer (top); the
main panel and a Fermi-surface map in momentum, in its viewer (bottom) --
also on the synthetic demo data.</sub></p>

Every step from the files to the finished figure is the program's own,
and every step is plain Python that a script -- or an **AI agent** -- can
run, without a screen:

| Step | In the program | In code |
|---|---|---|
| 1. Raw data | the beamline files, as the main panel lists them | `arpes_viewer.loader.registry.load(path, entry)` |
| 2. To momentum | the Γ-plane Fermi-surface map → k-map | `arpes_viewer.tools.momentum.kspace.convert_map(...)` |
| 3. The calculation | **Calculated bands**: a Wannier Hamiltonian; Z and the shift fitted on a cut | `BandsDialog.open_file(...)`, `.fit_alignment()` |
| 4. Measured vs calculated | constant-energy maps over the calculated contours, coloured by orbital weight (b) | `BandsDialog.series_panels(...)` |
| 5. 3-D views | the notched cube (a), the stacked contours (c) | `VolumeWindow(...).figure_panel()` |
| 6. The figure | the **figure composer**: arranged, lettered, exported as PNG / PDF, saved as `.afig` with the data and the files it came from | `FigureWindow(...)`, `.arrange(...)`, `.write(...)` |

`devtools/figure_tests.py` is exactly this script -- it writes the demo
files, reads them back, and builds this figure (and its companion, example
figure 2) in under a minute:

```
python devtools/figure_tests.py out_png/ out_afig/
```

In the step 3 fit it recovers what was built into the demo calculation
(Z = 0.798 ± 0.001 and a shift of −49.8 ± 0.4 meV, against 0.8 and −50 meV).

---

## An AI agent can drive it

Talk to your AI app (the Claude desktop app, Claude Code, any agent that can
read and write files) in plain words -- *"today I process the kz maps in
this folder: align the Fermi levels, convert to momentum with Γ at 80 eV,
draw the zone, and make a slice-series figure"* -- and it drives the program
on your screen, step by step, while you watch and can take over. Data stay
on your computer.

- **Start**: press **AI assistant...** (top of the tool panel), choose the
  data and results folders, tick what you want (step by step, a usage log,
  a report, slides, hiding the sample's identity ...), and press **Copy the
  prompt and start**; paste the prompt into your AI app. The window then
  lists each step the agent runs, and **Pause** hands you the controls. The
  agent reads `arpes_viewer/agent/API.md`, the program's ~50 documented operations
  (`L.fermi_edge`, `L.kz_to_k`, `L.bz_overlay`, `L.slice_series`,
  `L.figure_render` ...), instead of the source.
- **Other routes**: an MCP app (`arpes-viewer-mcp`; with the program
  started as `arpes-viewer --agent-bridge` it calls the same operations), or
  a coding agent writing a script to keep, on the headless workspace and the
  Qt-free computations in `arpes_viewer/tools/`.

### Starting and watching an agent from the AI assistant panel

<p align="center">
  <img src="docs/images/assistant_button.png" width="80%"
       alt="The AI assistant button at the top of the tool panel, lit green while an agent works">
</p>

1. **Open it.** Press **AI assistant...** at the top of the main panel's
   tool column (above). The button is also the agent's **status light**,
   whether the window is open or not: grey not running, green running,
   yellow paused (you work by hand), red a failed step.

<p align="center">
  <img src="docs/images/assistant_setup.png" width="96%"
       alt="The AI assistant window before starting: the folders, the options, the request in one's own words">
</p>

2. **Set it up** (left column):
   - **1. Folders**: the **data** folder (read only for the agent) and a
     **results** folder (everything it writes goes there; its commands go
     in `<results>/_agent`).
   - **2. What you want**: ask before each physical parameter (Γ, an
     energy window, V0 ...), step by step with your go-ahead, a usage log,
     a report, slides, hiding the sample's identity, a tidy list -- and
     your request in your own words.
   - **3. Your AI app**: *works in folders* (the Claude desktop app, Claude
     Code, any agent that reads and writes files -- nothing to install) or
     *uses MCP tools*.
3. **Start.** Press **Copy the prompt and start** and paste the prompt
   into your AI app. The prompt tells the agent where the folders are,
   where the program's reference (`arpes_viewer/agent/API.md`) is, and the
   working rules (fit E_F on raw data per row, report files left out,
   ask before going around an operation, keep the list tidy ...);
   **Show the prompt** shows it in full.

<p align="center">
  <img src="docs/images/assistant_running.png" width="96%"
       alt="The AI assistant window while the agent works: its steps, each with what it printed">
</p>

4. **Watch and step in** (right column). Each step the agent runs appears
   in the list with ✓ or ✗ (red); click one to see what it printed -- here
   the Fermi-edge search and fit of a map. Its results appear as new rows
   in the main list (never overwriting anything), its pictures and figures
   in the results folder. **Pause the agent** holds its next commands while
   you work by hand (the light turns yellow); **Resume** lets them through.
   Closing the window does not stop the agent.
5. **Your screens stay yours.** Windows the agent opens only to drive them
   (a conversion dialog, a temporary slice series) never appear; the ones
   it leaves open -- a finished figure, a viewer, a tool waiting for your
   input -- open on the screen of the main panel, not on the screen you
   are working on.

The step-by-step guide is [`agentic/README.md`](agentic/README.md), with
requests to copy in [`agentic/PROMPTS.md`](agentic/PROMPTS.md); a real session
by Sonnet 5.5 is in [`Reports/`](Reports).

As with any analysis, check what an agent produced before you publish it.

---

## Bug reports

The program saves what went wrong by itself, in
`error_logs/errors_<date>_<time>.txt` in its folder (in `~/.arpes_viewer/`
when installed with pip), and keeps running. With a bug report on
[GitHub Issues](https://github.com/DingPei1995/ARPES-viewer/issues),
**upload that file** (drag it into the text box) **or paste its text** --
the main panel's foot has **Copy the newest error log** and **Open the
error logs** -- and give the version number, shown in the main window's
title bar.

---

## Documentation

- **User guide**, with screenshots: [English](docs/USER_GUIDE_en.md) ·
  [中文](docs/USER_GUIDE_zh.md) · [Français](docs/USER_GUIDE_fr.md); as PDF:
  [English](docs/pdf/ARPES_viewer_user_guide_en.pdf) ·
  [中文](docs/pdf/ARPES_viewer_user_guide_zh.pdf) ·
  [Français](docs/pdf/ARPES_viewer_user_guide_fr.pdf).
- **AI agents**: start with the beginner's guide [`agentic/README.md`](agentic/README.md) -- connecting an agent step by step, runnable examples and [requests to copy](agentic/PROMPTS.md); then the MCP server ([user guide, Part 7](docs/USER_GUIDE_en.md#part-7--ai-agents)) and the file-based [agentic workflow](docs/AGENTIC_WORKFLOW_en.md).
- **What changed, and why**: [CHANGELOG.md](CHANGELOG.md).
- **Technical references**, beside the code they describe -- the formulas,
  the file layouts, the assumptions and the tests behind each step:
  - [Reading data](arpes_viewer/loader/README.md) -- every facility's files, the data
    kinds, adding a beamline, the assumptions the formats force;
  - [The windows](arpes_viewer/ui/README.md) -- the main panel, the viewers, autosave
    and recovery, long operations;
  - [Analysis](arpes_viewer/tools/README.md) -- what each tool does and what it assumes;
  - [Momentum conversion](arpes_viewer/tools/momentum/README.md) -- k conversion, k_z
    maps;
  - [Spectra](arpes_viewer/tools/spectra/README.md) -- core levels, curves, curve fits,
    spin;
  - [Processing](arpes_viewer/tools/processing/README.md) -- de-gridding, cut
    arithmetic;
  - [Figures, export and the experiment log](arpes_viewer/tools/output/README.md);
  - [For developers](docs/DEVELOPER.md) -- the layout of the code, and the
    tests (`python -m pytest`).

---

## Terms of use, citation and licence

**Terms of use.** This program is for **non-commercial use only**
(academic research and teaching); any commercial use is not permitted.
New and updated loaders cover data from **public large-scale facilities**
(synchrotrons and similar user facilities), formats of individual
laboratories' own set-ups can be added by the user him/herself. If you use this program for
a paper on ARPES experiments, please cite it in its references:
Ding Pei, *ARPES viewer*, Zenodo, <https://doi.org/10.5281/zenodo.23771647>
(GitHub's *Cite this repository* gives the reference in other formats).
If you write a paper related to AI that uses this program or its code,
please discuss it with the author by e-mail first. For collaborations, or
questions about the details, contact
[ding.pei@synchrotron-soleil.fr](mailto:ding.pei@synchrotron-soleil.fr).

**Licence and authorship.** Copyright (c) 2026 Ding Pei. Licensed under
the [PolyForm Noncommercial License 1.0.0](LICENSE.md); see also
[NOTICE](NOTICE). This is the author's personal work, developed from the
author's own earlier code; no institution funded it. Some of its ideas
were inspired by the ARPES data-processing programs of the author's
former group, the [Chen Group at the University of Oxford](https://www.arpes.org.uk).
The requirements, design decisions, trade-offs, physics, the testing on
real experimental data and the feedback from it (drawing on
[Phys. Rev. B 103, 245121 (2021)](https://doi.org/10.1103/PhysRevB.103.245121)
and [Phys. Rev. B 95, 125126 (2017)](https://doi.org/10.1103/PhysRevB.95.125126)),
and the review and acceptance of every change are Ding Pei's; the
implementation was assisted by Claude (Anthropic), credited as co-author
in the commits.
