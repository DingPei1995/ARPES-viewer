# Part 1 — Getting started

What the program is, how to install and start it, the demo data that every screenshot is made from, the files it reads, how to connect an AI agent, and where things are in the code and on disk.

## 1.1 What ARPES viewer is

ARPES viewer is a Python/PyQt5 program for angle-resolved photoemission
data. It browses the measurements of a beamtime, opens each in its own
window, converts to momentum, cuts, fits and processes, compares with
band-structure calculations, and lays the results out as a publication
figure. Every step is also plain Python that a script or an AI agent can
run.

It is free for **non-commercial use** (academic research and teaching), under
the PolyForm Noncommercial License 1.0.0. If you use it for a paper, please
cite it: Ding Pei, *ARPES viewer*, Zenodo,
<https://doi.org/10.5281/zenodo.23771647>.

It is not an acquisition program and does not change your data files: every
result is a new dataset in the list or a new file you choose.

## 1.2 Installing and starting

You need Python 3.9 or newer and five packages:

```bash
pip install PyQt5 pyqtgraph numpy h5py scipy
```

Then, from the `ARPES_viewer` folder:

```bash
python ARPES_viewer.py
```

**On Windows, double-click `ARPES viewer.pyw`** in the program's folder,
not `ARPES_viewer.py`: Windows runs a `.pyw` with `pythonw`, which opens no
black console window -- closing that window by mistake used to close the
program with it. (A `.py` double-clicked all the same now hides the console
it was given; one started from a command prompt keeps its console.) The
program's messages go to `~/.arpes_viewer/launcher.log`; if it stops with an
error, a message box shows the end of that log.

**Errors are kept as a text file.** Whatever the console would show when
something goes wrong -- the error and its traceback -- is saved by itself in
**`error_logs/errors_<date>_<time>.txt` in the program's folder** (in
`~/.arpes_viewer/error_logs` if that folder cannot be written), only when an
error happens. A message says so, and the program **keeps running** instead
of closing. With a bug report, **upload that file** (on GitHub Issues: drag
it into the text box) **or paste its text** — the main panel's foot has
**Copy the newest error log** (its text to the clipboard) and **Open the
error logs** (the folder).

**Long operations show a progress bar.** Anything that can take more than a
moment on a big dataset or a slow computer — reading a whole map, k
conversion, FS correction, arbitrary cuts, data operations, joining
datasets, saving, ridge detection, the fits, and in Calculated bands reading
a calculation, the plane's bands and the 3-D Fermi surface — shows a
progress window after 0.4 s: a bar that moves, the seconds taken, and Cancel
where the step can stop. The program is working, not frozen.

**On a Mac you do not need Terminal to start it:** double-click
**`ARPES viewer.app`** in the program's folder (drag it to the Dock to keep
it there). It finds the Python that has the packages above -- the same one
as `python3` in Terminal, conda environments included -- and remembers it.
If no Python has them, a dialog gives the `pip install` command (already
copied to the clipboard: paste it into Terminal once) or lets you choose
a Python yourself.

- If macOS says the app *cannot be opened because it is from an unidentified
  developer* (the program was downloaded as a ZIP): open **System Settings →
  Privacy & Security** and click **Open Anyway** (older macOS: right-click
  the app → **Open**). Only the first time.
- A copy of the app moved out of the program's folder (to Applications, say)
  asks once where the folder is.
- If the program stops with an error, the dialog shows the end of
  `~/.arpes_viewer/launcher.log`; please send that file with a bug report.

The files it reads are listed in [§1.4](#14-facilities-and-file-formats).

## 1.3 Trying it with demo data

```bash
python devtools/demo_data.py            # writes ./demo_data/
```

This writes synthetic data that opens exactly like measured data:

- the original set -- a Fermi-surface map, a pair of cuts in LH and LV
  polarisation, a photon-energy scan, a spin-resolved EDC, a small
  real-space scan and a map with a detector mesh printed on it -- from a toy
  band structure (a hexagonal electron pocket and a hole band at Γ, hole
  pockets at K);
- **a layered crystal in three dimensions** (`demo_bulk_bands.nxs`): maps at
  the photon energies of the Γ plane (59.3 eV) and of the zone top (77 eV),
  cuts along Γ-M (LH and LV) and Γ-K, and a photon-energy scan along Γ-M
  through a whole period of k_z. Two of its bands cross along a line through
  the zone, whose energy changes with k_z;
- **a calculation of that crystal**, as a theory group would send it: a
  Wannier90 Hamiltonian (`demo_calc_hr.dat` with `demo_calc.win`) and the
  same bands on a grid (`demo_calc.bxsf`). It is the crystal before
  renormalisation -- its bands 1/0.8 times wider and 50 meV higher -- which is
  what fitting it to the data recovers ([§6.5](#65-calculated-bands));
- two crystal structures as CIF files (`demo_crystal.cif`, a 1T layered
  hexagonal crystal; `demo_tetragonal_crystal.cif`, a ZrSiS-type one) and an
  EDS spectrum (`demo_eds.nxs`).

All come with a Fermi cut-off, the analyser resolution and Poisson noise.

To re-take every screenshot in this guide after changing a window:

```bash
python devtools/guide_screenshots.py    # writes docs/images/*.png
```

The two example figures of [§6.7](#67-worked-example-two-figures-in-the-figure-composer)
are rebuilt, from the demo data and with the program's own windows, by

```bash
python devtools/figure_tests.py docs/images [folder for the .afig files]
```

## 1.4 Facilities and file formats

The reader for a file is detected automatically ([§2.2](#22-loading-data)).

| Facility / beamline | Files | Data |
|---|---|---|
| SOLEIL **ANTARES** | NeXus `*.nxs` | cuts, deflector maps, photon-energy (PhD) scans, spatial scans |
| SOLEIL **CASSIOPEE** | Scienta text `*.txt` | single spectra; numbered folders assembled into a map or a photon-energy scan |
| CASSIOPEE **spin end station** (MBS A-1) | `*.krx`, `*.txt` | cuts, deflector maps, spin-resolved EDCs |
| ALS **MAESTRO** | `*.h5`, `*.hdf5` | cuts, maps, photon-energy and spatial scans |
| ALBA **LOREA** | `*.nxs` | cuts, maps |
| Diamond **I05** (HR-ARPES) and **I05-1** (nano-ARPES) | `*.nxs` | cuts, maps, photon-energy scans, spatial scans |
| MAX IV **Bloch** (and any Scienta SES file no other reader claims) | `*.ibw`, `*.zip`, `*.txt` | cuts, deflector maps, photon-energy and manipulator scans |
| Elettra **APE**, BESSY **One Cube / One Square**, SOLARIS **URANOS** | `*.ibw`, `*.zip`, `*.txt` | as SES writes them |
| ASTRID2 **SGM4** | `*.h5`, `*.hdf5` | cuts, maps, knife-edge scans |
| This program | its own `*.nxs` | anything it saved, several datasets per file |

Datasets are written back as the program's own `.nxs` (which it opens again)
or as Igor Pro text (`.itx`). How each facility's files are read, and the
assumptions their formats force, is in
[the loaders' reference](../../../arpes_viewer/loader/README.md); adding a
beamline is explained there too.

## 1.5 Data kinds

| Kind | Axes | What it is |
|---|---|---|
| `cut` | angle (or k) × E | one spectrum |
| `map` | angle × angle × E | a deflector or polar-angle scan |
| `k_map` | kx × ky × E | a map converted to momentum |
| `kz_map` | hν × angle × E | a photon-energy scan |
| `kz_map_k` | k_z × k∥ × E | that scan converted to momentum |
| `spem_4d`, `spem_1d` | x (× y) × angle × E | real-space scans |
| `edc`, `mdc`, `spin_edc` | E (or k) × channels | curves, with optional σ channels |

## 1.6 Setting up an AI agent

An AI agent can drive the program for you ([Part 7](#part-7--ai-agents)).
There is nothing extra to install for the usual route:

1. Have an AI app that can read and write files on your computer: the
   Claude desktop app, Claude Code, or a similar agent.
2. In ARPES viewer, press **AI assistant...** at the top of the tool panel,
   choose the data and results folders, and press **Copy the prompt and
   start** ([§7.3](#73-starting-from-the-ai-assistant-panel)).
3. Paste the prompt into the AI app and allow it to read the data folder
   and to read and write the results folder.

An app that uses MCP tools instead needs the program's MCP server added once;
the prompt says how ([§7.5](#75-other-ways-to-start)). Before you start,
read what leaves your computer ([§7.1](#71-how-it-works-and-what-leaves-your-computer)).

## 1.7 How the code is organised

| Folder | What is in it |
|---|---|
| `arpes_viewer/loader/` | the readers: one per facility (`beamlines/`), shared formats (`formats/`), the program's own `.nxs`, the session's autosave |
| `arpes_viewer/tools/` | the computations, without any window: spectra (Fermi edge, fits, core levels, spin), momentum (k and kz conversion), processing (smoothing, derivatives, cut arithmetic ...), crystal (lattices, Brillouin zones, calculated bands), output (figures, export) |
| `arpes_viewer/ui/` | the windows: the main panel (`launcher/`), the viewers (`viewers/`), the tool windows (`panels/`), shared pieces (`common/`), including the agent's operations `L` (`common/live.py`) |
| `arpes_viewer/agent/` | the MCP server, the agent bridge, and `API.md`, the agent's reference generated from the program |
| `agentic/` | examples and recipes for agents and scripts |
| `devtools/` | the demo data, the screenshots, the figure tests, the guide's build |
| `test/` | the tests (`python -m pytest`) |

Because the computations in `tools/` need no window, a script can call them
directly, for example `arpes_viewer.tools.momentum.kspace.convert_map(...)`.
Each folder has a README with the formulas and tests behind it; the layout
and conventions are in [the developer notes](../../DEVELOPER.md).

## 1.8 Where the program keeps its files

| Where | What |
|---|---|
| `~/.arpes_viewer/` | settings remembered between sessions, the launcher's log, the agent bridge's token while it runs, the AI assistant's last folders |
| `~/.arpes_viewer/sessions/` | the autosaved copies of computed datasets, one folder per session, and `operations.log` ([§8.1](#81-autosave-memory-and-recovery)) |
| `error_logs/` in the program's folder (else `~/.arpes_viewer/error_logs/`) | one text file per session in which an error happened ([§8.3](#83-error-logs-and-bug-reports)) |
| `<results>/_agent/` | an agent's command files, their output and pictures, when started from the AI assistant ([§7.3](#73-starting-from-the-ai-assistant-panel)) |

Your data folders are only read; the program writes into them only when you
save a file there yourself.
