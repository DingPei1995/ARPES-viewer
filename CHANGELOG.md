# Changelog

Round-by-round history of ARPES viewer, newest first. Each entry says what
changed and, more usefully, *why*. The minor versions before the current
one are each merged into one summary (1.1, 1.0), and the forty-eight rounds
before 1.0.0 ten at a time at the end. When a new minor version starts
(1.2.x to 1.3.0, say), the previous one's entries are merged into one
summary of it.

What the program does and how to use it is in [README.md](README.md); this
file is the record of how it got that way.

---

## 1.2.4 — 2026-11-02

Tools moved to where they are looked for, a CIF that would not open,
three things that misled or failed on k-maps -- and an MCP server, so that
AI agents of any model can use the program.

- **k conversion (map) and (cut): the energy rows.** *Energy offset* was
  often read as "type E_F here", which shifts every k. It is now behind a
  tick box, off by default (the axis is used as it is); only a dataset
  already on E − E_F has it ticked and filled in, as before. Above it, a new
  row **Energy axis as E − E_F** (off by default) takes E_F where it is on
  the dataset's own axis and puts the result on E − E_F; the momenta do not
  change. The result records the E_F, so the fits start from E_F = 0.
- **3-D views of a k-map start at the first filled planes.** A converted
  cube is the box around a light cone that narrows away from E_F, so the
  notched cube's and the slices' outer k_x / k_y faces drew blank.
  `tools.processing.volume.filled_ranges` finds the planes that hold data
  (≥ 97 % of the fullest), and 3D slices, Notched cube, Stacked slices and
  Volume projection open on that range; *Change sampling → Whole range*
  shows everything.
- **Slice series figure of a map not on screen** (a k-map, typically): the
  figure was made from a contour opened off screen, which was then closed --
  and a contour closes its figures with it. The figure is now let go first.
- **Combine** takes in *Sum repeated scans* (gone from the Datasets box) as
  its third way. **Stacking cuts** no longer needs both axes identical: with
  one axis the same, the other -- energy windows a little apart, usually --
  is truncated to the range all cover and resampled onto the first cut's
  points (`stackcuts.truncation_plan`, `truncated_frames`).
- **The list**: a search box above it (every word typed must appear in the
  row's name or kind; hidden rows are deselected), and right-click **Sort by
  name** (natural order) and **Sort by data type**.
- **Crystal structure.** Typed in like the Brillouin-zone tool: the space
  group first, then the cell it allows (`ui.common.cellinput.CellInput`,
  shared with 3D BZ and the tight-binding fit). *From the Brillouin-zone
  tool* is gone; **Read a CIF file...** is a button, above the cell, that
  fills the space group, the cell and the basis (the file's symmetry
  operations kept for its own space group) and redraws.
- **CIF reading.** A FullProf CIF opens on a `data_global` block of journal
  fields and has the structure in the next block; the parser stopped at the
  second `data_` and found no cell. Every block is now read and the one with
  the cell and the atom sites used; `#` comments and `;` text fields no
  longer leak into values, and `?` is "unknown", not a name.
- **3D BZ** is the crystal window's former zone step on its own: any
  number of planes, each with its own (hkl), height, colour and opacity
  (*Add a plane in 3D BZ*), any number of paths in colours of their own
  (*Add path*), and **To figure composer**. **Any** plane can carry a
  measured constant-energy map: the k-maps selected at opening and every
  k-map of the main list (read when chosen, given back at close; *↻ Maps
  from the list* for ones added since), laid along the plane's own in-plane
  axes (`crystal.plane_basis`) -- it was a plane normal to k_z only, and
  only maps selected beforehand. The old *Brillouin zone...* is now **BZ
  overlap...**.
- **Tight-binding fit**: the 3-D crystal is typed space group first, the
  constrained parameters greyed out. **Shells are symmetry orbits**
  (`tightbinding.lattice_symmetry`): one hopping per set of neighbours the
  space group's point group (with inversion) makes equivalent -- the
  lattice's own symmetry for a 2-D layer -- so two inequivalent neighbours
  at the same distance get a hopping each; they shared one, grouped by
  length alone. Each shell is listed with a representative vector
  (⟨1 0 0⟩), and *Save parameters* writes the space group and every shell's
  vectors. Every step now says the model is **one band**.
- **Tight-binding fit: two hybridised bands** (step 1, *Bands*). Two bands
  ε_a, ε_b on one lattice and their coupling V(k) = v0 + Σ v_n S_n(k),
  fitted together to the two eigenvalues E± (`tightbinding.fit_two_band`,
  `TwoBandFit`): a search from many starting models with each point scored
  against the nearer band, then refinement with the points assigned and
  stray ones reweighted. Points can be labelled lower / upper (by clicking,
  or a `branch` column in a points file); unlabelled ones go to the nearer
  band. The result gives both bands with errors, the coupling, which band
  each point went to and the smallest gap (2|V| where the bare bands
  cross); both bands are drawn, listed as a map and saved.
- **`loader/nxs_file.py` is split** into `loader/scan.py` (`NxsScan`, the
  kinds and axis slots, the lazy arrays and file handles),
  `loader/native.py` (this program's saved format) and
  `loader/beamlines/antares.py` (the SOLEIL ANTARES reader and loader, which
  absorbs `beamlines/soleil.py`). Code that imported from `nxs_file`
  imports from these. The loaders now register on first use rather than
  when the registry is imported, which also removes an import-order trap.
- Code comments and docstrings describe each tool by what it does, without
  the comparisons with the MATLAB programs it started from.
- **The Calculation tab is now "Figure"**: the figure composer at its top
  (it was on Advanced), then Crystal structure, 3D BZ, Tight-binding fit and
  Calculated bands.
- **An MCP server for AI agents** (`arpes_viewer/agent/`;
  `arpes-viewer-mcp`, or `python -m arpes_viewer.agent`). Any agent that
  speaks the Model Context Protocol -- Claude, GPT, Gemini, a local model --
  starts it and calls its tools: headless ones that use the program's own
  loaders and algorithms (find and open files, describe, EDC/MDC profiles,
  PNG pictures, Fermi-edge fit, E − E_F shift, crop, both k conversions,
  save as .nxs / Igor, the zone's high-symmetry points, CIFs), and
  `viewer_*` ones that drive the program on screen when it was started with
  `--agent-bridge` (rows, selection, any tool-panel button, screenshots of
  its windows, Python inside it). The bridge listens on 127.0.0.1 only and
  answers only the random token it writes to `~/.arpes_viewer/
  agent_bridge.json`. The protocol is written out in `agent/protocol.py`,
  so nothing new is installed; `agent/` imports no Qt, like `loader/` and
  `tools/` (a test checks). Tested with a real subprocess speaking MCP and
  the bridge over its socket.

## 1.2.3 — 2026-10-30

The agentic workflow: an AI agent (e.g. Claude, through the desktop app
linked to your computer) processes data inside the viewer on your own
machine, so raw data and code are never uploaded.

- **`agentic/`.** `viewer_live.py` runs small Python command files that the
  agent drops into a folder, inside the live viewer's GUI process;
  `launch_viewer.py` starts the viewer with the data listed;
  `agent_runner.pyw` runs headless jobs from a queue. Results come back as
  text logs, screenshots and figures that can be checked. `recipes/` holds
  four building blocks adapted from a real session: normalise, cut k
  conversion with Fermi fit and offset, arbitrary cut from a map, and a
  two-peak MDC fit. They use the viewer's internal functions and may need
  changes after updates.
- **Documentation.** `docs/AGENTIC_WORKFLOW_en.md` is the full guide, written
  from a working deployment, with the recipes explained; two reports are in
  `Reports/`. README links to them; the user guides carry the new version.

- **The repository is now `DingPei1995/ARPES-viewer`**, matching the
  program's name and the PyPI package `arpes-viewer`; it was
  `ARPES-data-browser`. Every link -- the main window's, README, the user
  guides, `NOTICE`, `LICENSE.md`, `CITATION.cff`, the PyPI project links --
  now points at the new address. GitHub redirects the old one, so links in
  released versions and the PDF guides still work.

## 1.2.2 — 2026-10-29

The terms of use and the authorship, as published with the package, and a
reference to cite. No change to what the program does.

- **The terms agree with the licence.** Discussing an AI-related paper with
  the author first is now asked, not required: the PolyForm Noncommercial
  licence decides what is permitted, and a README cannot add conditions to
  it. 1.2.1's page on PyPI still showed the old wording, and a released
  version's files cannot be replaced there -- hence this release.
- **Authorship.** README and `NOTICE` add that some of the program's ideas
  were inspired by the data-processing programs of the Chen Group at the
  University of Oxford (<https://www.arpes.org.uk>), and that most of the
  code was written in 2026.
- **A reference to cite.** `CITATION.cff` (with the author's ORCID) gives
  the reference for GitHub's *Cite this repository* and for Zenodo, which
  archives each release from this one on; a test keeps its version and date
  with `version.py`. Zenodo's concept DOI, standing for all versions, is
  [10.5281/zenodo.23771647](https://doi.org/10.5281/zenodo.23771647); the
  README shows it and asks papers to cite it.

---

## 1.2.1 — 2026-10-29

Calculations from the theory side as they really come -- the FPLO + Wannier
tools' files, renamed or cut-up files, MATLAB grids -- and the Calculated
bands window rebuilt around what the experimentalist wants to see: E-k
dispersion, constant-energy contours on any plane, or the 3-D Fermi surface.
The step-by-step windows ask before closing and remember their settings, and
Enter in a field never presses a button.

- **A package for pip, a licence, and the authorship stated.** The code is
  now one package, `arpes_viewer/` (`loader/`, `tools/`, `ui/`,
  `version.py`, and the main window as `app.py` with a `main()`), so that
  `pip install arpes-viewer` installs it and the `arpes-viewer` command (or
  `python -m arpes_viewer`) starts it; `ARPES_viewer.py`, `ARPES viewer.pyw`
  and `ARPES viewer.app` still start a downloaded copy as before.
  `pyproject.toml` describes the package; `.github/workflows/publish.yml`
  builds it and publishes it to PyPI when a GitHub release is published
  (trusted publishing, no stored token), with the README's links made
  absolute for the PyPI page (`devtools/pypi_readme.py`). Installed with
  pip, the error logs go to `~/.arpes_viewer/error_logs/`, since the
  package's own folder is no place for them. The licence is the PolyForm
  Noncommercial License 1.0.0 (`LICENSE.md`); `NOTICE` states that this is
  Ding Pei's personal work, developed from Ding Pei's own earlier code with
  no institutional funding, with Ding Pei's testing on real experimental
  data and the feedback from it, and the implementation assisted by Claude.

- **Calculated bands: the plane, the cell, the bands' looks**
  (`tools/crystal/planecut.py`, `ui/panels/bands.py`, `ui/panels/fsview.py`).
  Contours are cut on any plane, set as the Brillouin-zone tool sets one:
  normal (hkl), k⊥ along it with *Through point* (the zone tool's
  `plane_offsets` over its `equivalent_points`), an in-plane rotation, and a
  k⊥ window integrated along the (hkl) normal (not the absolute k_z), drawn
  as grey intensity under the middle plane's contours. *Show the plane in the
  Brillouin zone* draws the zone with the plane, its window's faces and the
  points it holds, following every change. Each band's colour (shared by
  several bands to group pockets), a surface's opacity and visibility are set
  per band and kept from the contours to the 3-D view. The cell read from a
  calculation is locked, space group and *From the Brillouin-zone tool*
  included, until *Change the lattice parameters* is ticked; a cell typed
  then scales the calculation. For the 3D Fermi surface the Compare step is
  left out and saving to the main panel is greyed (it made a path cut);
  for contours it saves a calculated k-map on the plane, at a range of
  energies.
- **A shorter README, with the technical detail beside the code**
  (`README.md`, `loader/README.md`, `ui/README.md`, `tools/README.md`,
  `tools/momentum/README.md`, `tools/spectra/README.md`,
  `tools/processing/README.md`, `tools/output/README.md`, `docs/DEVELOPER.md`).
  The README repeated much of the user guide; it is now 180 lines instead of
  1480: the terms of use, a worked case -- example figure 1 of the guide,
  built from the files to the exported figure by `devtools/figure_tests.py`,
  every step plain Python an AI agent can drive -- what the program does,
  starting it, bug reports, and links. It says plainly that the figure is
  made from synthetic data: an invented toy model, no published data or
  literature used. The technical sections moved verbatim, every line
  checked, into a reference in the folder of the code they describe; the
  guides' links follow them.
- **A progress bar for every long step, and no second job on top of the
  first** (`ui/common/jobs.py`). Enter in the 3-D Fermi surface's energy
  failed with "another operation is already running" (reported from a
  user's error log, reproduced here): the progress window took the focus,
  the field's `editingFinished` fired again and started a second job inside
  the first. `one_at_a_time` makes such a call wait and run once afterwards
  with the latest values; `run_blocking` raises `JobBusy`. `busy_work` runs a
  step that cannot say how far it is off the GUI thread behind a moving bar,
  and every progress window now counts the seconds. Steps that had only a
  wait cursor or nothing now show it: reading a whole map (browsing, the
  slice figure, the 3-D views, and the k conversion, which read the cube
  before its bar), cut k conversion, the FS correction of a map, arbitrary
  cuts, data operations (their settings read first, on the GUI thread),
  stacking and joining, saving `.nxs` and Igor (per dataset), ridge
  detection to the list, the tight-binding fit, cube resampling. Rotating a
  3-D view and painting figures stay on the GUI thread (a bar would
  interrupt the drag; painting is Qt's).
- **A crash closing a viewer** (`ui/viewers/windows.py`, `ARPES_viewer.py`).
  Closing a viewer closed its child windows by asking Qt for *every* child
  widget and testing each: that handed Python wrappers of Qt's own internal
  widgets (popup containers, tooltips), which Qt deletes without telling
  Python, and touching a stale one crashed the program -- now and then (two
  full test runs in ten). Only dialogs and main windows are asked for now,
  the type test done by Qt, afresh after every close; closing the program
  touches only those kinds of top-level window too.
- **No console window to close by mistake, and errors kept in a file**
  (`ARPES viewer.pyw`, `tools/runtime/console.py`,
  `tools/runtime/errorlog.py`, `ui/common/crashguard.py`). On Windows a
  double-clicked `ARPES_viewer.py` came with a console whose close button
  closed the program. `ARPES viewer.pyw` starts it with `pythonw` (no
  console; output to `~/.arpes_viewer/launcher.log`, a message box on a
  failed start), and a `.py` double-clicked all the same hides the console
  opened for it alone (one a command prompt owns is left). What the console
  would show of an error now goes by itself to
  `error_logs/errors_<date>_<time>.txt` in the program's folder, made only
  when an error comes (a warning before it is kept as context). And an
  exception escaping a button's handler no longer aborts the program --
  PyQt5's default with no `sys.excepthook` of the program's own, checked:
  exit 134 -- it is written there, said once in a message, and the program
  carries on. The main panel's foot, that message and the README say to
  upload the file with a bug report or paste its text: **Open the error
  logs**, **Copy the newest error log**.
- **Enter in a field takes the value, everywhere** (`ui/common/enterkeys.py`).
  Typing an energy in the Fermi-surface step and pressing Enter pressed Next:
  a Qt dialog passes Enter on from a spin box or line edit to its default
  button. An application filter now stops it at the window once the field
  has taken the value, in every dialog of the program (Qt's own file,
  message, input and colour dialogs keep Enter = OK); a focused button still
  answers Enter. It first decided by where the focus was, and so missed the
  contour page's in-plane rotation: the value started a computation whose
  progress window took the focus, and Enter then pressed Next. It no longer
  looks at the focus -- Enter that reaches a dialog is always stopped -- and a
  window that redraws only on a button names that redraw (`enter_redraws`):
  the Brillouin-zone tool's Plot, a viewer's selection-box Refresh, the
  core-level zoom's Show. Every field was checked by a probe run over the
  test suite: those listening to nothing are parameters of an explicit action
  (an output name, an export size, a fit's range), where Enter just takes the
  value.
- **Calculated bands, as an experimentalist meets it** (`ui/panels/bands.py`,
  `ui/panels/bandfinder.py`, `ui/panels/fsview.py`,
  `tools/crystal/fermisurface.py`). Step 1 now starts from *what you want to
  see* -- E-k dispersion, constant-energy contours or the 3D Fermi surface --
  which sorts the file dialog, refuses a path-only file for contours with a
  plain reason, retitles step 2 and ticks the matching outputs. **Which
  file?** reads a whole folder by content and says what each file is, what it
  can show, what it lacks, whether it is a standard file renamed or one file
  split in pieces (and joins them). Files are recognised by content
  everywhere, so a renamed `_hr.dat` or `.bxsf` opens; MATLAB `Ek_3D` `.mat`
  grids (v5 and v7.3) read too. Long reads run off the GUI thread with a
  progress bar and Cancel. Step 2 is the path, the calculated contours on a
  chosen k_z plane, or a 3-D Fermi surface (marching tetrahedra, clipped
  exactly at the zone faces, drawn without OpenGL, turned with the mouse,
  also in a large window of its own) that goes to the figure composer as a
  picture. The volume viewer's 3-D projection was not reused: it shades one
  data cube at one level, where a Fermi surface is several bands, each its
  own colour, cut at the zone with its points named. *Highlight bands*
  (`41-44` or `EF`) colours chosen bands as the theory side's scripts do.
  *Calculation to list* is **Save calculation to main panel**, beside *To
  figure composer*; a spectrum along a path keeps its high-symmetry points,
  shown by the cut viewer along the top (a **High-symmetry points** box,
  ticked) and by the figure composer on the k axis.
- **Step-by-step windows ask before closing and remember**
  (`ui/common/stepper.py`, `ui/common/remember.py`). The last step's Close
  sat where Next had been, so a quick second click closed the window and lost
  everything set. Now Close, the title bar and Esc ask first ("Keep working"
  the default), Enter never presses Close, and every control is kept and put
  back the next time the window opens (**Restore defaults** to start afresh)
  -- in Calculated bands, Crystal structure, Tight-binding fit, Sum repeated
  scans and Detector corrections.
- **Calculated bands: the FPLO + Wannier tools' files, and the calculation
  alone to the output** (`tools/crystal/bandfiles.py`). A collaborator's
  LaCrGe3 calculation (FPLO, its Wannier Hamiltonian evaluated by
  `k_path.exe`/`H.exe`/`plot.exe`, plotted by MATLAB) came as `band.dat`,
  `Eigenvalue.dat` and a `KPOINTS` of its own, none of which the window
  read: the names are generic, so the reader now goes by content --
  `band.dat` along a path (with `orbital.dat`'s weight) or as a 3-D grid
  (`k1 k2 k3 E1 ...`, gigabytes: read in pieces, twice, keeping only the
  bands near E_F), `Eigenvalue.dat` (its k is 2π times fractional),
  `wannier90_hr_fplo.dat` (cell from `KPOINTS`, names and shell/spin weights
  from `wannier_name_center.txt`). Checked on the real path: `band.dat` and
  `Eigenvalue.dat` agree to 5e-7 eV and the bands crossing E_F are 41-44, as
  the MATLAB script finds. With nothing measured selected, the output now
  leaves the measured panels unticked and offers the calculated contours
  alone (a Fermi-surface slice on the step-3 k_z plane, zones drawn).

## 1.2.0 — 2026-10-28

Tools ported from the lab's MATLAB programs (`DataAnalysisPrograms_PD`),
each checked against the original and improved where it could be; a third
tab, **Calculation**; Igor Pro export; and a tidier tool panel. The windows
that take several decisions in a row lead through them as numbered steps
(*Step 2 of 4: ...*, Back / Next, Next greyed with the reason until the step
is done; `ui/common/stepper.py`).

- **Sum repeated scans** (Datasets box; replaces `add_two_value_arrays.m`,
  `tools/processing/repeats.py`, `ui/panels/repeats.py`). A fine cut or map
  taken in batches, to see an ageing sample and leave its late scans out.
  Step 1 compares the grids and the recorded conditions with the first scan
  (a slightly different grid is interpolated onto the first). Step 2
  compares each scan with the sum of the *others* using counting
  statistics -- χ²/point ≈ 1 for noise alone, a scan flagged when it stands
  well above the set's median -- with the count rate and the energy shift of
  its EDC (derivative cross-correlation against the others aligned by
  their own shifts, sub-step by a parabola, 0 when the EDCs share no
  structure). Step 3 sums the ticked scans (the changed ones start
  unticked), undoing the shifts if asked. On synthetic data a 12 meV shift
  is measured to ±1.5 meV and a broadened scan is flagged; noise-only
  repeats give χ² within 15 % of 1 and flag nothing. The MATLAB tool added
  two arrays with no check at all.
- **Ridge detection** (Advanced; from `ridge_detection.m`,
  `tools/processing/ridge.py`). Hessian ridges of the smoothed image, every
  point placed to a fraction of a pixel. Changed from the .m file: the
  smoothing is set per axis in that axis' own unit (it used one radius in
  pixels of mixed units); the derivatives are taken in units of the
  smoothing width, so the answer does not depend on the axes' units (tested:
  eV and meV give the same points); Gaussian-derivative filters instead of
  differences of a smoothed image; a sign-change test instead of an
  absolute slope tolerance that needed retuning per image; vectorised
  instead of `arrayfun`. Median error 0.2 meV on a synthetic band.
- **Detector corrections** (Basic, under Remove detector grid; from
  `StretchDitherImage.m`, `InterpRegionAlongX/Y.m`, `inpaint_nans.m`;
  `tools/processing/detector.py`, `ui/panels/detector.py`). A keystone
  (trapezoidal lit area) stretched to a rectangle as an exact inverse map,
  with each line's total counts kept -- the .m file triangulated every pixel
  (`TriScatteredInterp`) and did not conserve counts. Bad regions patched
  linearly along x or y (as the .m files did) or by a harmonic (Laplace)
  fill, factorised once for a whole map; *Find bad pixels* uses the map's
  mean detector image against its median filter and its pixel-to-pixel
  scatter, so noise is not taken for a faulty pixel. Refused, with the
  reason, on data already moved off the detector's pixels (de-gridded data
  is allowed).
- **Tight-binding fit** (Calculation; from `TB_zph_zmd`,
  `tools/crystal/tightbinding.py`, `ui/panels/tightbinding.py`). One hopping
  per shell of neighbours of any 2-D or 3-D lattice (typed, or the
  Brillouin-zone tool's last crystal), fitted to band points traced by ridge
  detection on constant-energy planes of a k-map, clicked, or read from a
  CSV. The model is linear in its parameters, so the fit is one linear
  solve with standard errors (the .m files ran a nonlinear fit from all-ones
  start values with ±1000 bounds). Robust: Tukey reweighting gives points
  traced on something else no weight. Points at one energy fix the shape
  but not the energy scale, so t1 is then held (the .m fit was undetermined
  there); a scaled condition number says when the points cannot separate
  the shells (one contour fixes about two). The azimuth can be refined by a
  scan. The model's contour is drawn over the data; its spectral function
  goes to the list as a map; parameters to JSON.
- **Crystal structure** (Calculation; from `Lattice_plot_zqs`,
  `tools/crystal/structure.py`, `ui/panels/crystal.py`). Typed in (cell,
  centering, basis), from the Brillouin-zone tool's last crystal
  (`tools/crystal/last_crystal.py`), or from a **CIF** with its symmetry
  operations applied. Per element colour, size, transparency and gloss;
  cell edges, bonds; a cleavage plane (hkl) slid along its normal or put on
  one of the listed atomic layers (each with the atoms it holds), the atoms
  above faded or hidden to show the termination. Painted with QPainter (no
  OpenGL), so it renders at any size; *To figure composer* adds it as a
  picture panel.
- **Crystal view, improved for papers.** Atoms shaded as glossy spheres
  with real transparency; grey, thin bonds; lattice constants written on
  the cell edges; the element key optional. The Brillouin zone and
  polyhedra are drawn in the same view: k axes as arrows, high-symmetry
  labels set off from their points and optionally placed at a left-hand
  equivalent (*Label on the left*), a path drawn in colour, and a measured
  k-map painted on the plane through Γ or the zone top, clipped to the
  zone's outline.
- **Calculated bands** (Calculation; `tools/crystal/bands.py`,
  `ui/panels/bands.py`). Reads a Wannier90 `_hr.dat` (and the other
  formats listed in the guide) with orbital weights; draws bands along a
  path, constant-energy contours, and compares with a measured cut or map
  -- a renormalisation Z and an energy shift fitted to the cut's bands
  apply to the contours too. A band can be *followed* through crossings by
  eigenvector overlap (diabatic), and a crossing line traced through k_z.
  *To figure composer* sends the comparison, a constant-energy series or
  the calculated guides as dashed overlays on a cut.
- **Stacked slices** (Advanced; `ui/panels/volume.py`). Constant-energy (or
  constant-k_z) slices of a volume as separated, faded layers in 3-D, with
  spread, aspect and view angle, and curves marked through the layers --
  the stacked contour plots of papers.
- **Band crossings.** The MDC fit's *Dispersion...* window reports where two
  fitted linear branches cross, with its error (`line_crossing` in
  `tools/spectra/dispersion.py`); a collapsed error no longer makes the fit
  singular (sigma floored at a tenth of the median).
- **Figure composer: own file format, `.afig`** (`tools/output/figfile.py`).
  A zip of the figure as JSON plus its arrays (no pickle); *Open figure...*
  in the composer or the launcher reopens it for editing. Saving writes
  beside it a folder *data for <name>* with one subfolder per panel letter
  holding the data as shown (`.nxs`, line CSVs, a PNG) and the original
  measurement it came from, traced back through conversions and cuts, plus
  an imported picture's own file.
- **Figure composer: arranging.** Select several panels (Ctrl-click) and
  line them up: top, bottom, left, right, distribute, same width or
  height. Panel letters line up row by row and run (a), (b), (c) in
  reading order; a letter can be nudged. Colour bars can sit below a
  panel, shorter, with high or low at either end. Curve overlays take
  symbols and error bars and break at gaps.
- **Demo data and example figures.** The demo set gains a tetragonal CIF, a
  calculated band structure that matches the demo bands, and a photon-energy
  scan with a band crossing; `devtools/figure_tests.py` builds the two
  example figures of the guide's worked example from it.
- **User guides (English, Chinese, French) reorganised** by the tool
  panel's tabs: Getting started, Basic, Advanced, Calculation, Figures and
  output, Housekeeping; each ends with a worked example making two paper
  figures in the figure composer. The French guide gains the Plot tools
  section it lacked. PDFs regenerated.
- **Terms of use** in the README gain two lines: an ARPES paper made with
  the program is asked to cite this repository; a paper related to AI that
  uses the program or its code must first be discussed with the author by
  e-mail.
- **Igor Pro export** (`tools/output/igor.py`; replaces
  `Export2ScientaData.m`). The viewers' Export → *Data (.nxs, Igor)* and the
  Datasets box's **Save** write `.itx` (all datasets in one file) or `.ibw`
  version 5 (one per dataset): scaling, units, dimension labels, metadata
  in the wave note, an unevenly spaced axis as its own wave. The `.ibw`
  round-trips through this program's own SES `.ibw` reader in the tests.
- **The tool panel**: a third tab, **Calculation** (Crystal structure,
  Tight-binding fit, Calculated bands). The Memory
  box's three buttons share one row, renamed **Free RAM**, **Close all**,
  **Autosaves** (the old names are in their tooltips). The Datasets box puts
  **Rename**, **Save** and **Remove** on one row, and gains **Sum repeated
  scans...**.

## 1.1 — 1.1.0 to 1.1.1, 2026-10-27 to 2026-10-28

Every tool put in sight, and the experiment log.

- **A tool panel beside the list**, with Basic and Advanced tabs, every
  tool grouped by the dimension of data it takes and greyed out, with the
  reason, until the selection fits. The k conversions, the Fermi-edge fit,
  Align Fermi levels, Remove detector grid and the Brillouin zone became
  tool-panel buttons; a viewer's Functions menu no longer repeats them.
  Under the list, one button per data operation (Combine, Truncate,
  Compress, Self-normalise); the right-click menu keeps only what is done
  to the rows, and a **Datasets box** gathers row actions such as
  Experiment info.
- **One window per operation**: Smooth, Second derivative, Curvature,
  Symmetrise and Background subtraction, in 2D and 3D; MDC fit and EDC fit
  as two tools with a guided fit; the 3-D view as three tools (3D slices,
  Notched cube, Volume projection) that open at a balanced sampling and
  resample on request; the multi-slice figure as *Slice series figure*.
- **The figure composer is a manuscript page**, and smoothed data is
  tagged as such.
- **The experiment log**: *Log format...* sets the columns once from a
  reference dataset's fields (renamed, reordered, saved per beamline);
  *Auto Exp. log* appends the selected datasets with no window.
- **Fixes**: Save the view and To figure composer failing on click; Diamond
  maps losing the positions that followed the scan; the tool panel
  overlapping on macOS (where a double-click now starts the program); tall
  windows now fit the screen; Close is always last in a dialog's buttons.
- Terms of use stated; user guides (en, zh, fr), PDFs and screenshots
  updated.

## 1.0 — 1.0.0 to 1.0.8, 2026-10-25 to 2026-10-26

The first numbered versions: the number and the date in the title bar and
at the foot of the main window, with a link for bug reports, so a user can
tell which build they have.

- **New beamlines**: ALS MAESTRO (1.0.3); ALBA LOREA, Diamond I05 and
  I05-1 (1.0.4); MAX IV Bloch (1.0.5); Elettra APE and ASTRID2 SGM4, after
  the readers in peaks and untested on real files (1.0.6); BESSY One Cube /
  One Square and SOLARIS URANOS (1.0.7); swept-mode kz maps from CASSIOPEE
  (1.0.1).
- **Combine datasets**: stack cuts into a map or join pieces of any kind
  end to end.
- **Plot tools on every viewer**, and names that say what they do.
- **k conversion**: a converted map stored in float16 by default (half the
  memory; its steps far below the counting noise); a grid coarser than the
  measurement averages instead of picking samples; the map conversion keeps
  the measured resolution; greyed-out inputs show what is actually used.
- **Better starting values**: self-normalisation on the usual choice; the
  3-D smoothing effective when applied at once; symmetrisation mirrors k,
  not energy; the Fermi cut-off starts at an E_F on the axis; joining
  starts on the axis the pieces differ along.
- The real reason is shown when a text file fails to load; the code is
  grouped into subpackages; user guides updated.

## Before 1.0.0

Forty-eight rounds of work, from the first reader of SOLEIL ANTARES
nano-ARPES files to the program that became 1.0.0, merged ten rounds at a
time (newest first). The detail of each round is in the git history.

### Rounds 41–48 and the run-up to 1.0.0 (to 2026-10-25)

Rounds 46–48 were saved together as the version of 12 October 2026.

- **Combining and comparing.** Cuts measured with the same settings
  (a temperature, gate or photon-energy series) can be stacked into a map;
  the new axis gets a role, a name, a unit and a step, and a photon-energy
  series becomes a kz map. Level min/max now hold while a slice moves, and
  pop-out snapshots keep the panel's colour scale.
- **Core-level check** (right-click a cut). Names the peaks of a wide
  core-level EDC against the X-ray Data Booklet's Table 1-1: Fermi edge
  fitted or hν − W, spin-orbit partners, solid-state values for gaseous
  elements, second- and third-order light, Auger lines, charging shifts,
  levels expected but missing. Weak lines are found beside a strong one
  (*Min height*, *Log counts*, peaks by hand), with a peak table and a zoom
  window showing −d²I/dE² / I.
- **Loaders.** ANTARES photon-energy (PhD) files open as one kz map, each
  frame referred to E_F by its own hν. A CASSIOPEE folder adds one row,
  named with its photon energy and polarisation. ANTARES spatial scans are
  titled and oriented from their real actuator names (coarse ST/SZ in mm,
  piezo PIX/PIY in µm), and open the way the beamline draws them.
- **Brillouin zone.** High-symmetry points marked in 3-D and on the
  contour, with a *Through point* list of offsets that put the cut plane
  through one of them (a static table per Bravais lattice, after Setyawan &
  Curtarolo); the zone on a k_z map is right for any surface, not only
  (001); tiling works for a plane far from Γ; the last crystal is
  remembered.
- **Speed and memory.** A map's sliders slice memory, not the file (one
  contour from a file in energy-fastest order reads every page: 55–130 ms a
  tick before); a memory box on the main panel; autosaved working copies
  written uncompressed (gzip cost 1.6 s per 100 MB) and deleted at a
  confirmed normal close, kept only after a crash; old session folders
  swept.
- **The main panel.** *Clear list* asks and offers to save what is
  unsaved; the right-click menu fits the selection and greys out the rest
  (and now looks greyed out); tooltips without the lag; a decimal point in
  every number box whatever the system language.
- **User guides** in English, Chinese and French, with reproducible
  screenshots from synthetic demo data, and PDF editions; running every
  window for them turned up a failed cut conversion on E − E_F data, a
  slower-than-needed map conversion and several layout faults, all fixed.

### Rounds 31–40

- **kz maps calibrated against their own Fermi edges** (31): fit the edge
  in every spectrum, shift each onto it, crop to the common range,
  normalise -- so absolute energies no longer rest on nominal photon
  energies and a work-function table.
- **k_z conversion** (32): the photon-energy map inverted in closed form
  rather than projected and re-gridded (which took 200 s on a real cube),
  with the in-plane component of a tilted manipulator taken out of k_z
  (0.26 Å⁻¹ at 20°), points without a real k_z left blank, an inner-
  potential scan, and which lattice planes a measured k_z period could
  come from.
- **Set rotation from contour** (33): two picked points make a line, so
  click order and side no longer flip the answer by 180°.
- **Cut arithmetic** (34): LH − LV, circular dichroism, division by a
  reference, differences, ratios and sums of two cuts, with uncertainties
  and a check that the two cuts are on one grid.
- **The spin end station and 1-D data** (35): a reader for MBS A-1 `.krx`
  and `.txt`; EDCs, MDCs and spin EDCs as kinds of their own with a curve
  viewer, curve fitting and spin analysis (polarisation, spin-resolved
  spectra, Sherman function 0.2 by default).
- **De-grid** (36): the MCP hexagon or Scienta mesh removed from a cut or a
  whole map with no reference measurement, its Fourier peaks found
  automatically and only those removed; settings chosen by measurement on
  real grids.
- **Crashes on closing windows** (37, 39): reads from a closed HDF5 file
  and a segmentation fault after closing a map with its cut open, traced to
  how file handles and child windows were released; closing a map now
  closes its cut windows.
- **A leaner viewer** (38–40): one row of view controls and a *Functions*
  menu; one readout cursor shared by a map and its cuts, while each window
  keeps its own integration widths; *Functions* in the curve viewer; slit
  and deflector cuts from the main list's menu.

### Rounds 21–30

- **One export** (21): from each panel's right-click menu -- the data as
  `.nxs`, an image at a chosen size, or vector axes as `.eps` -- in place
  of two toolbar buttons that wrote whatever the window held.
- **The plot box takes the data's shape** (22): an equal-aspect image no
  longer widens the view past the data (a deflector axis to ±40° for data
  ending at 12°).
- **k conversion for a single cut** (23): where normal emission is (it
  sets the k scale) kept apart from where Γ is (a translation), Γ taken
  from a converted map, the file's geometry or typed; one interpolation per
  energy row.
- **The figure composer** (24): one model and one painter for screen, PNG,
  PDF and vector axes; panels that share scales and labels; a page of
  slices from a cube.
- **Processing, 2-D and 3-D** (25): smoothing, Savitzky–Golay derivatives,
  dimensionless curvature, symmetrisation that says how much it invented,
  backgrounds, despiking, a notched cube and orthogonal slices; every
  operation makes a new dataset and records its steps.
- **MDC / EDC fitting** (26): bands as objects seeded at a few energies,
  variable projection, the Fermi cut-off in the model, errors on the fitted
  axis, and v_F, m* and the self-energy read off the band; image
  orientation fixed (axes exchanged, upside down, squashed).
- **Brillouin-zone overlay** (27): conventional, irreducible and moiré
  zones on a converted contour, space group first, with a 3-D view of the
  cut plane.
- **Nothing is lost** (28): long work off the GUI thread, every derived
  dataset written to a session folder the moment it exists, maps kept on
  disk, a loader window and one reader per beamline.
- **ARPES viewer** (29): the program renamed and its modules arranged in
  packages; an import check added after the rename shipped a bug; a session
  log; one table for which axes each kind has.
- **CASSIOPEE** (30): Scienta text spectra from both SES versions, a folder
  of numbered spectra read as one map or kz map, the stepped quantity
  worked out and declared, and the folder read without freezing the window.

### Rounds 11–20

- **Large files open instantly** (11): a 1.5 GB spatial scan is no longer
  read whole -- the cube stays on disk and the overview comes from the
  file's own reduced preview.
- **Several measurements in one file** (12): each entry its own row,
  classified by content.
- **Angle → momentum for maps** (13–14): the origin picked on the
  constant-energy contour, the output grid chosen, a non-blocking dialog, named results that cannot collide,
  a right-click menu in the list, and the program's own saved format.
- **The view controls** (15–16): out of pyqtgraph's right-click menu into a
  visible row; *Smooth* that interpolates on screen instead of blurring on
  the data grid; slice positions typed as a value or an index.
- **Intensity and cuts** (17): gamma and min/max as a percentage of the
  image; arbitrary cuts along a path through the contour; Fermi-surface
  correction from a feature that should be flat.
- **The launcher operates on data** (18–19): sample rotation picked off the
  contour; the output grid by resolution or count; truncate, self-normalise
  and compress; spatial axes called X and Y; a separate information window.
- **Fermi-level fitting** (20): a resolution-convolved Fermi function with
  a sloped background, Poisson weights and errors, the temperature held by
  default, an energy offset or division by the cut-off, and a
  channel-by-channel fit for a gold reference.

### Rounds 1–10

- **The first reader** (1–2): SOLEIL ANTARES `.nxs` files read by matching
  each raw axis to its axis vector by length, entries classified by content
  rather than by name, calibration scalars that arrive as arrays, and
  several entries in one file.
- **Viewing** (3–7): 32 colormaps, a readout cursor with EDC and MDC in the
  standard ARPES arrangement, rectangle selection with two-way
  integration, axis labels with units, a slim level bar, pop-out windows for
  comparison, and the full metadata.
- **The program's shape** (8–10): a launcher with a separate window per
  dataset, the data kind shown in the list, a colormap per window, and
  frames that hug the data.
