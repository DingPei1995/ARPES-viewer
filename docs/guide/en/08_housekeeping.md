# Part 8 — Housekeeping

Autosave and recovery, saving your work, error logs, versions, and what to do when something goes wrong.

## 8.1 Autosave, memory and recovery

- **Autosave.** Every computed dataset (a k-map, a processed cut, a fit
  result…) is written, uncompressed, to this session's folder in
  `~/.arpes_viewer/sessions/` the moment it exists. Real-space scans are not
  (they are the measurement itself, and large).
- **A normal close deletes the autosaved copies.** When you close the main
  window and confirm (everything you want is saved, or *Close anyway*), the
  open viewers are closed and the session folder is deleted straight away.
  A dataset's copy also goes as soon as you save it to a file of your own.
- **Recovery after a crash.** Only if the program did not close normally (a
  crash, a kill) is the session folder kept: the next start offers its
  datasets back, and it is deleted after three days.
- **Operations log.** `~/.arpes_viewer/sessions/operations.log`, one line per
  store / save / discard — how to find what was where.
- **Memory box** (bottom of the tool panel). This program's memory, the system's, how many viewers and
  HDF5 files are open, and how much computed data is held. **Free RAM**
  drops cached copies of computed data (they are re-read from their autosaved
  file when needed); **Close all** closes every window and then frees
  memory.
- **Autosaves** (in the Memory box) shows the session folders
  in the system's file browser, to delete old working copies by hand. The
  folder of the session now running (named in the status bar) is in use.
- **Long operations** (reading a big map, converting, de-gridding, assembling
  a folder) run off the GUI thread with a progress bar and a working Cancel.
- **Closing** with unsaved computed data asks first, and names the datasets:
  **Save to a file...**, **Close anyway** (the autosaved copies are deleted)
  or **Cancel** (nothing happens).

## 8.2 Saving and reopening work

- **Datasets.** Select rows → Datasets box → **Save**: one `.nxs` file in the
  program's own format (several datasets per file, with their metadata and
  processing history), which **Load data...** opens again; or Igor Pro text
  (`.itx`). A viewer's panel exports what it shows
  ([§3.8](#38-exporting-a-panel-and-saving-data)).
- **Figures.** In the figure composer, **Save** writes an `.afig` file that
  opens again for editing, with the data of every panel beside it ("data for
  <name>"), so it opens even where the original files are not. Leave that
  folder out of anything you share. **Export** writes PNG, PDF, SVG or TIFF.
- **The experiment log** and the **session log** record what was measured
  and what was done ([§2.3](#23-the-experiment-log)).
- Nothing is overwritten without asking: a save to an existing file asks
  first.

## 8.3 Error logs and bug reports

When something goes wrong, the program **keeps running** and saves the error
and its traceback in **`error_logs/errors_<date>_<time>.txt` in the program's
folder** (in `~/.arpes_viewer/error_logs/` if that folder cannot be
written), one file per session in which an error happened. A message says
so.

To report a bug, open an issue at
<https://github.com/DingPei1995/ARPES-viewer/issues> with:

- the error log: **upload the file** (drag it into the text box) **or paste
  its text**. The main panel's last line has **Copy the newest error log**
  and **Open the error logs**;
- the version, from the title bar;
- what you did just before, and if possible the kind of file
  (beamline, cut or map).

If the program does not start at all, the launcher's log
`~/.arpes_viewer/launcher.log` holds the reason.

## 8.4 Versions and updates

The title bar and the main panel's last line show the version and its date
(`ARPES viewer v1.3.3 (updated 2026-11-10)`). What changed in each version,
and why, is in the [CHANGELOG](../../../CHANGELOG.md).

To update a pip installation:

```bash
pip install --upgrade arpes-viewer
```

For the latest unreleased version, `pip install
git+https://github.com/DingPei1995/ARPES-viewer`; a downloaded copy is
updated by downloading it again. Datasets and figures saved by an earlier
version open in later ones.

## 8.5 Tips and troubleshooting

- **A greyed tool button** — hover over it: the tooltip says why (e.g. the
  MDC fit needs a cut already in Å⁻¹, cut arithmetic two cuts). Select the
  right rows in the list and it lights up.
- **A tool is not in a viewer's Functions menu** — it is in the tool panel
  (see *Where things are now* in [§2.1](#21-the-main-window-at-a-glance)); check all three tabs (Basic, Advanced, Figure).
- **A window is taller than the screen** — it opens no taller than the
  screen, and its contents scroll; the Apply / Close buttons stay at the
  bottom. Every window can be resized.
- **A k conversion is not offered** — the first axis of the map is not an
  angle (a photon energy, temperature…). Check *First axis of a map is* in
  the loader.
- **Cut k conversion of an E − E_F cut** — the energy offset is filled in for
  you from the Fermi fit; if you shifted the axis some other way, type the
  kinetic energy of E_F (photon energy − work function) into *Energy offset*.
- **A file is misread** — choose the reader explicitly in the loader, and see
  *Assumptions worth knowing about* in the
  [reading-data reference](../../../arpes_viewer/loader/README.md#assumptions-worth-knowing-about)
  (axis order in SOLEIL files).
- **Dragging the cursor on a big map is sluggish** — a map read lazily from
  its file re-slices in about 0.1 s per window, so the other windows wait for
  the mouse to pause. Once the map has been read into memory it follows live.
- **Typing numbers** — every number box takes a decimal point (`0.05`),
  whatever the system language; a comma is not accepted.
- **The machine is paging** — watch the Memory bar (amber past a third of the
  RAM, red past a half); use **Free RAM** or **Close all**.
