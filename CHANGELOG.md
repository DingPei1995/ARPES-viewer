# Changelog

History of ARPES viewer, newest first. Each entry says what changed and,
more usefully, *why* -- the measurement that settled a format choice, the
bug that a check now prevents, the assumption that turned out not to hold
on real data. The forty-eight rounds before 1.0.0 are summarised ten at a
time at the end.

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

## 1.1.1 — 2026-10-28

The experiment log, and a Datasets box for what is done to the rows. (A
small change, so only the last number moves.)

- **The experiment log**, two buttons side by side in the tool panel's
  Datasets box (`tools/output/explog.py`, `ui/panels/explog.py`):
  - **Log format...** sets the log up, once: folder, file name, separator,
    decimal mark and columns. The columns are chosen by ticking the fields
    of a reference dataset from the main list (its metadata and motors,
    plus fields worked out from the data: file name, data type, start
    time, the scanned axes, the energy window, the points), renamed and put
    in any order; an empty column takes notes by hand. The settings are
    remembered between sessions; a format can be saved per beamline.
  - **Auto Exp. log** adds the selected datasets to the log in that format,
    after its last record, with no window (the first click asks for the
    format). Files already in the log are skipped. *Keep recording* logs
    every file added to the list from then on.
  - **The format belongs to the log.** Pointing *Log format* at an existing
    log shows that log's own format, to adjust; saving a changed format
    rewrites the log under the new header, each record moved with its
    columns (followed through renames and moves), after saying which
    columns' contents would go. The header is only ever the first row.
  - **Excel opens it in columns.** Excel splits a CSV at the computer's
    list separator, which is `;` wherever the decimal mark is a comma --
    so a comma-separated log opened with everything in the first column on
    such a Windows. The separator and decimal mark are now by default
    Excel's on this computer (read from the Windows settings; from the
    decimal mark on macOS and Linux), numbers are written with that decimal
    mark (and so are not turned into dates), and an existing log keeps its
    own separator wherever it is continued. Logs start with a byte-order
    mark so that Excel reads hν and Δ.
  - What a position column says follows the measurement: a cut's fixed
    position; a SPEM scan's stage as `start/stop/step`; a manipulator
    map's angle as `start/stop/step`, and a sample position corrected
    along with the angle as `first..last`; a kz map's photon-energy range.
    Each column has an *If scanned* rule (auto, never, SPEM X / Y, map
    angle, kz photon energy); auto recognises the scanned motor by name,
    and a moving position by its values.
- **Diamond maps keep the positions that followed the scan.** A motor that
  moved along a scanned dimension without being its axis -- the sample
  position I05 corrects as the manipulator turns -- is now listed among the
  dataset's motors as `<name> range`, so the log can say where the sample
  was (`Layout.followers`).
- **The tool panel has a Datasets box**, between the tools and the Memory
  box: **Experiment info**, **Log format...** | **Auto Exp. log**,
  **Rename...**, **Save datasets...**, **Remove from list**, **Session
  log...** -- the right-click menu's entries other than the three ways of
  opening a row, which are all that menu holds now. They grey out with the
  selection like the tools.
- **Show information is Experiment info**, and its window is titled so.
- **Combining is the Combine... button under the list only**; the
  right-click entry for it is gone.
- **macOS: double-click to start.** `ARPES viewer.app`, in the program's
  folder, starts the main panel without Terminal. Finder gives an app no
  conda or Homebrew on its PATH, so the app looks for a Python with the
  packages itself -- what `python3` is in a login shell (conda included),
  then the usual Anaconda / Miniforge / Homebrew / python.org / pyenv places
  -- and remembers the one that works. Without one, it says what to install
  (command copied to the clipboard) or lets the user choose a Python; Apple's
  `/usr/bin/python3` stub is skipped without the developer tools, so it
  never pops up their installer. A copy moved elsewhere asks once for the
  program's folder; an error exit shows the end of
  `~/.arpes_viewer/launcher.log`. The icon is the author's own drawing of
  a hemispherical analyser (`devtools/icon_drawing.png`), set on a macOS
  tile by `devtools/make_mac_icon.py`.
- **Terms of use** in the README: non-commercial use only; new readers are
  for public large-scale facilities, not individual laboratories.

## 1.1.0 — 2026-10-27

A large rework of where things are: every tool is a button in sight, one
window per tool. (The version number stays 1.1.0; later changes are added
here.)

- **macOS: the tool panel no longer overlaps.** macOS's native widget style
  draws a push button as a fixed-height Aqua bezel with wide outer margins
  and ignores the style sheet's padding, so in the tool panel (buttons two
  pixels apart) the buttons overlapped each other and the headings, and
  the Memory box's buttons covered its labels; its progress bars drew no
  text either. On macOS the program now uses Qt's Fusion style, which lays
  buttons out from the style sheet as Windows does
  (`ui/common/platform_style.py`). Other macOS/Windows differences evened
  out at the same time: the interface font is the first installed of
  Lucida Sans Unicode (Windows), Lucida Grande (macOS), Segoe UI, ... rather
  than a Windows-only font Qt had to search aliases for at start-up; the
  tool panel widens to fit its longest button when the system font is
  wider, instead of cutting labels short; hints that say "Ctrl" say "⌘" on
  macOS, where Qt reads Command as Control; and pixmaps are drawn sharp on
  Retina screens.
- **The figure composer is a manuscript page.** With nothing selected it
  opens a blank page of four empty panels (a)–(d); each panel is a frame on
  the page (`Panel.frame`, mm) that is dragged and resized with the mouse,
  snapping to the other panels' edges and a 0.5 mm grid. A panel is filled
  from the main list or with a picture from a file (`PanelData` kinds
  `empty` and `picture`). A *Zoom-in inset* tool drags out a region of a
  panel and puts a magnified copy in its corner (`role="inset"`,
  `zoom_of`), with the region outlined; any panel drawn inside another is an
  inset. Arrows, lines, boxes, ellipses and text are drawn on the page
  (`Figure.shapes`, in mm) from a tool column on the left and edited when
  selected; the figure tools sit beside the page instead of in a dialog,
  with the selected panel's position, size, label edges and font size.
  Undo/Redo cover all of it. Figures opened with panels (slice series, 3-D
  views, stack plots) start as the automatic grid as before and become a
  hand-made page at the first drag (`Figure.freeze`). Empty slots are never
  exported. Panels now compare by identity (`eq=False`): comparing by value
  compared their arrays.
- **Guided MDC / EDC fit.** *Guided fit (step by step)* at the top of the
  fit panel walks a first-time user through the fit in eight steps beside
  the controls -- what the fit does, line shape, range, bands, seeds (the
  guide moves the line to five places and arms the seed click), a test
  line, the series, the result -- outlining the widgets each step uses;
  *Next* waits until a step has what the fit needs.
- **The fit panel's controls stay in sight.** Pictures and controls are in
  a vertical splitter, so the plots no longer push the settings below the
  window; the wheel over a plot scrolls the window when it scrolls
  (`screen.wheel_scrolls_window`), and Ctrl + wheel zooms.
- **Smoothed data is tagged.** A smooth step marks its result
  (`proc.tag = smoothed`, and `process.is_smoothed` also reads it off the
  history, so files saved earlier and every result made from smoothed data
  count). The row shows ‹smoothed› in the list, and the second-derivative
  and curvature panels drop their smooth-first tip and start with no
  pre-smoothing on it.

- **Multi-slice figure is the Advanced tool "Slice series figure"**
  (*3D only — maps*, beside the 3-D views), instead of an entry of a map
  viewer's Functions menu. The new name says what it makes -- a page of
  flat 2-D slices at a series of energies or angles, one figure for a paper
  -- and keeps it apart from *3D slices*, whose tooltip now points to it.
  From the list it slices a hidden contour of the map, closed again once
  the figure is made.
- **The tool panel's text is the main panel's**: its buttons, tabs and
  title use the window's own font and size, like the list buttons beside
  them (a larger size, tried first, looked out of place); only the group
  headings stand apart, in grey italics. A test checks the sizes match.
- **Tall windows fit the screen.** The Brillouin-zone dialog needed 958 px
  and could not be made shorter; other tool windows (k conversions, kz
  conversion, Fermi fit, de-grid, kz alignment, the filters, the loader,
  curve fit, spin analysis, plot tools, cut arithmetic, the fit panel) had
  the same problem on a laptop screen. `ui/common/screen.py`'s
  `fits_screen` puts a window's contents in a scroll area, keeps its
  trailing button row (Apply / Close) outside it, and opens the window no
  larger than the available screen; every one of them can now be resized
  freely. A test opens each and checks its minimum height.
- **User guides (en, zh, fr), their PDFs and screenshots updated** for
  everything in 1.1.0: the tool panel and its tabs, the list buttons and
  right-click menu, a table of where each tool moved, the Fermi fit per cut
  of a map, the Γ line of the cut conversion, the remembered settings, the
  Brillouin zone as a property, the separate filter windows, the three 3-D
  views and the slice series figure.
- **The tool panel has two tabs, Basic and Advanced**, and opens on
  Basic; switching to Advanced shows only the advanced tools. Each tab is
  grouped by the dimension of data as before. *Basic* holds the steps
  nearly every dataset goes through: Fermi edge fit, Remove detector grid,
  Background subtraction, the three k conversions, Core-level check, Align
  Fermi levels (kz), Brillouin zone. *Advanced* holds the analysis after
  them: the figure composer, the filters, the stack plot, the MDC and EDC
  fits, cut arithmetic, the 3-D views. A tab scrolls when the window is too
  short for it; the memory box stays at the bottom.
- **Brillouin zone is a Basic tool**, for a map in momentum (a k-map or a
  converted kz map), instead of an entry of the contour's Functions menu.
  It opens like the k conversion: the contour on its own, showing only its
  picture, tied to the dialog.
  - **A plotted zone becomes a property of the dataset**: the zone as drawn
    (every layer's polygons and the labelled points, as JSON in
    `scan.info["bz.overlay"]`) and its settings (`bz.*`) are kept with the
    row in the launcher (`_set_row_properties`), put back on the dataset
    every time it is loaded, and written into the file it is saved to.
    *Clear overlay* forgets it again.
  - A map's viewer then has a **Brillouin zone** tick box beside its cut
    buttons, shown only when the dataset has a zone, to draw or hide it.
  - **Export draws it too**: the Export dialog's Image tab has *Include the
    Brillouin zone*, and its Axes (.eps) tab *Draw the Brillouin zone in the
    box* -- the axes and the zone, with its labelled points, as vectors in
    one file (`export.axes_eps(paths=, points=)`). Both appear only when a
    zone is drawn on the panel.
- **The k conversions are tool-panel buttons** -- *k conversion (map)*,
  *k conversion (cut)*, *kz conversion* -- and no longer entries of the
  viewers' Functions menus.
  - The map and the cut open in a window of their own that shows only the
    picture and how it is displayed -- no Functions menu, plot tools or cut
    buttons (`ViewerWindow.show_picture_only`) -- and close together with the
    conversion dialog, after the conversion it started has finished.
  - **Each conversion starts from the last one of data the same size**
    (`tools/runtime/remembered.py`, kept in `remembered.json` beside the
    config): a beamtime converts map after map of one sample, one per photon
    energy or polarisation, with the same Γ and grid. Carried over: for a
    map, Γ's angles, the rotation, the output grid and the precision (the
    readout cursor starts on the remembered Γ); for a cut, Γ's slit angle,
    the Advanced choice and angles, and the output; for a kz map, V0, m*,
    the normal-emission angle, the grid and the lattice. Not carried over:
    the energy offset, the deflector angle, the work function and the
    manipulator theta, which each file has of its own.
  - **The cut conversion picks Γ with a vertical line on the cut** by
    default: Γ is taken to lie on the cut at that slit angle, so its
    deflector angle is the cut's own. Not exact if the cut misses Γ, but
    often the only choice -- sometimes one slit cut is all that was
    measured. Γ still enters the geometry as an angle, not as a shift of
    the converted axis. Inheriting Γ from a converted map, Γ's deflector
    angle and the sample rotation are under **Advanced: Γ off this cut**.
- **Fermi edge fit is a tool-panel button** (*2D & 3D*), for a cut or a
  map, in angle or in momentum, instead of an entry of the cut viewer's
  Functions menu. The fit and the window it works on open together and are
  tied: closing either closes the other.
  - A **cut** opens in its viewer, with the fit beside it, as before.
  - A **map** opens on its slit cut (the contour stays off screen), and the
    fit is of the cut on screen: moving the cut's slider along the map's
    first axis (deflector, kx, or photon energy) gives another cut to fit,
    and the EDC follows.
  - **Offset energy axis** on a map asks first: the same offset for the whole
    map, or one per cut. *Yes* shifts the whole map by this E_F. *No* opens
    **Fitted cuts** beside the fit: every fit from then on is added there
    (a second fit at the same place replaces the first), E_F can be edited
    or rows removed, and a plot shows the fitted levels and the line between
    them. **Offset energy axis by these fits** shifts every slice by its own
    E_F -- the fitted cuts' own, a straight line between neighbouring fits
    (`fermi.levels_along`), and the nearest fit held beyond the first and
    the last -- and keeps the energy range all slices still reach, the kz
    map's own alignment (`kzmap.align`). The result is listed as
    `[E-Ef]` with the fits on record.
- **Align Fermi levels (kz map) is a tool-panel button** (*3D only*,
  "Align Fermi levels (kz)..."), for a photon-energy scan before its k
  conversion, instead of an entry of the map's Functions menu. It opens with
  the slit cut it picks its box on, the two tied like the Fermi edge fit.
- **Remove detector grid is a tool-panel button** (*2D & 3D*), for the
  selected cut, map or kz map -- no longer in the viewers' Functions menus.
  A cut still takes its grid from a `[grid]` pattern in the list when one
  matches; a map in momentum is greyed out, since it has been resampled off
  the detector's pixels (`degrid.open_degrid` is the one way in).
- **A viewer's Functions menu no longer repeats a tool-panel tool.** Gone
  from the cut viewer: MDC fit, EDC fit, Cut arithmetic, Remove detector
  grid; from a map's contour and slit-cut windows: Remove detector grid;
  from the curve viewer: Figure composer. What stays is what only the
  viewer can do -- k conversions, the FS correction,
  arbitrary cuts, the Brillouin zone, the multi-slice figure, saving or
  freezing the slice on screen, and the curve viewer's own operations
  (the tool panel's crop / bin / normalise do not take curves).
  - Cut arithmetic is opened with both cuts selected in the list. The cut
    viewer's way -- "now click the other cut in the list" -- went with its
    menu entry (`_PickOtherCutPrompt`, `await_list_selection`), and with it
    the arithmetic window's *Take the box from A's viewer* button (now
    hidden, there being no viewer); the region is typed instead.
- **Fixed: Save the view and To figure composer failed when clicked** (the
  3-D views). A button's `clicked` signal passes its `checked` flag --
  False -- to the slot, and both methods took it as their optional argument
  (the file to write, the composer to add to). They are connected through a
  lambda now. The same mistake, older, is fixed in three more places:
  **Find peaks** in the curve fit never found a peak (`max_peaks=False`),
  and **Apply** in the 2-D and 3-D processing windows ran on the GUI thread
  (`background=False`), freezing the window with no progress or Cancel.
  - `test_imports` now fails on any button connected straight to a method
    whose first argument is optional, and the 3-D view's test clicks the
    real buttons rather than calling the methods.

- **MDC fit and EDC fit are two tools.** "MDC / EDC fit" was one window
  with a direction switch, and open only for a cut in momentum, though an
  EDC fit means the same in angle. Now:
  - **MDC fit (k-cut only)...** -- MDCs only, and only for a cut converted
    to momentum. Its tool-panel button is greyed out for a cut still in
    angle, with the reason in the tooltip: whether a cut is in k is worked
    out once per row from its axis labels (read from the file the first
    time it is the one row selected, its values left on disk) and kept
    with the row.
  - **EDC fit...** -- EDCs only, for any cut, with the Fermi cut-off in the
    model as before. Its *Dispersion...* (v_F, m*) is offered only for a
    cut in momentum; for an angle cut the fitted peaks can still be saved
    as a table.
  - The cut viewer's Functions menu has the same two entries.
- **Smooth, Second derivative, Curvature, Symmetrise and Background
  subtraction each open a window of their own**, in 2D and 3D, instead of
  tabs of one "Smooth / derivative" window. A 3-D window lists only its own
  operation's variants (smooth: Gaussian, Savitzky-Golay, remove spikes;
  second derivative along either axis; curvature 2D or 1D) and only the
  settings they use. A chain of filters is now a chain of datasets: smooth,
  select the result in the list, then open the next on it.
  - The second-derivative and curvature windows say at the top that they
    work better on smoothed data, and how to get there.
  - **"Background" is now "Background subtraction"**, with a line saying
    what it removes (Shirley / Tougaard inelastic background, a floor common
    to every angle, a smooth polynomial, or dividing out the Fermi cut-off).
- **Every tool is in sight: a tool panel beside the list, and one button
  per data operation under it.** Several tools were only reachable through
  the list's right-click menu or as a tab of a window opened by a button
  whose name did not mention them, so a user who had not read the guide
  would never find them.
  - The launcher is now two boxes side by side. The left one, the tool
    panel, holds every tool that analyses or processes the selection,
    grouped by the dimension of data it takes: *1D & 2D* (figure
    composer), *2D & 3D* (smooth, second derivative, curvature,
    symmetrise), *2D only* (background, stack plot, MDC/EDC fit,
    core-level check, cut arithmetic), *3D only* (3D view). Under them:
    the memory meter, Free memory, Close all viewers and Open auto-save
    folder. The panel is part of the launcher window -- no title bar or
    buttons of its own.
  - A tool's button is greyed out until the list's selection is something
    it can take, with the reason in its tooltip -- the same rules as the
    right-click menu (`ui/launcher/list_actions.py`), from the list's
    records, so it costs nothing per click.
  - Under the list, one button for each operation that changes the data
    itself: **Combine...**, **Truncate...**, **Compress...**,
    **Self-normalise...**. The last three were the tabs of one
    "Crop / bin / normalise" window; each now opens that operation alone.
  - The smooth / derivative / ... buttons open the 2D or 3D processing
    window on their own operation; the other tabs stay, so a chain of
    filters is still one window. "Open the 3D view" left the 3D processing
    window for the tool panel's **3D view...**.
  - The right-click menu keeps only what is done to the rows: Open, Open
    slit cut, Open scan-axis cut | Combine datasets, Save dataset, Remove
    from list | Rename, Show information, Session log.
  - **"Deflector cut" is now "scan-axis cut"**, in the menu and on a map's
    own window: the map's first axis is whatever was scanned -- a
    deflector angle, a manipulator rotation, or the photon energy of a kz
    map. The tooltip names the axis this map has.
- **The 3-D view is three tools: 3D slices, Notched cube, Volume
  projection.** They were tabs of one window, behind one "3D view" button,
  though they are different pictures with different controls. Each is now
  its own button in the tool panel's *3D only* group and its own window.
  - **No sampling question before the data is on screen.** A view opens at
    the "Balanced" sampling (about 160 points per axis) over the whole
    cube. Under *Save the view* the window shows the sampling it is drawn
    from -- points per axis, the share of the measurement, the range and
    whether it is cropped -- and **Change sampling...** opens the region /
    sampling dialog, prefilled, and redraws from the full cube. The window
    keeps the dataset open for that and releases it on close; a
    file-backed cube is cropped before it is read
    (`volume.reduce_volume`), so a small window onto a large map reads
    only that window.
  - **Colours per slice, with transparency** (slices and notched cube).
    *Apply to* chooses all planes or only those at constant deflector,
    slit or energy; each orientation keeps its own colormap, levels,
    gamma, **opacity** and **fade low values** (the weakest intensities
    go transparent, so a slice can be looked through where it holds only
    background). Editing with *All* changes only the setting edited, so a
    colormap chosen for all keeps each slice's levels. *Auto* takes the
    levels from the chosen planes' own data; *Each its own* gives every
    orientation its own. Translucent faces are drawn back to front with
    the hidden ones included, so what is behind shows through.
  - **Coordinate axes with ticks, values and titles**, drawn on edges of
    the box. *Automatic* keeps each axis on an outline edge facing the
    viewer -- at the bottom, or the left for the upright one -- and moves
    it as the view turns; the edge lists are greyed out but show the edge
    in use. Otherwise each axis gets its own edge (which of the four
    parallel ones) and its direction (from its min or its max end), which
    together set where it starts. Titles run along their axis. The corner
    tripod is now an option, off by default.
  - **Save the view writes a figure**, by the figure composer's own export
    (`figure.write_figure`): PDF, SVG, PNG or TIFF, 89 mm wide at 600 dpi,
    with the composer's font, point sizes, axis line width and tick length
    for the 3-D axes. **To figure composer...** adds the view as it is
    now as a panel of a new figure or of one already open, where it is
    lettered, titled and annotated like any panel. The figure painter
    draws such a panel (`kind == "scene3d"`) with the same function as the
    window (`volume.paint_scene`), so the panel is what the window showed;
    a figure made only of 3-D panels reserves no frame margins.
  - Volume projection is unchanged apart from being a window of its own.
- **Close is always the last button of a dialog's row.** The buttons were
  laid out by `QDialogButtonBox`, which orders them by role in the
  platform's own way; on Windows that put *Close* to the left of *Apply*
  in Crop / bin / normalise, and on GNOME before every action. The dialogs
  with an action and a Close (the data operations, both processing
  windows, the cut arithmetic, de-grid, kz alignment and conversion, and
  the curve viewer's fit and spin windows) now use `widgets.ButtonRow`,
  which keeps the order the buttons are added in.

## 1.0.8 — 2026-10-26

- **A converted Map is stored in float16 by default.** The k-conversion
  dialog has an *Output precision* choice -- float16 (default) or float32 --
  with a note under it saying why half precision is enough: its relative
  step of 2^-11 (0.05 %) is far below the counting noise of a measured
  point (1 % already needs 10^4 counts), so contours, cuts and fits come
  out the same while the cube takes half the memory and roughly half the
  file. Before this, a map read as float64 was also
  converted to float64 -- four times the float16 size for digits the
  counts never had.
  - `kspace.convert_map(..., precision=)`: `"float16"`, `"float32"`, or
    None for the old rule (follow the measurement's dtype). The
    interpolation is still done in float64; only the stored result changes.
  - float16 is granted only when the values fit it
    (`kspace.float16_holds`): a peak above 65504 would overflow, and one
    below 0.0625 would sink a map's weak tail under float16's normal range.
    Either way the result is float32, and the status bar says so.
  - Half precision is a storage format only. `CubeCache` holds a float16
    cube as it is but hands out every slice as float32, and the integration
    window widens before it sums (`cubecache.widen`): a window of a few
    dozen planes of counts summed in float16 would reach inf. A float16
    k-map saved to a file and opened again reads the same way.
  - The default grid (as many points as were measured) is unchanged.
- **A k conversion onto a grid coarser than the measurement now averages instead of picking samples** (Map and Cut, in energy and in k; `tools/momentum/rebin.py`), so a reduced grid keeps every count and no longer aliases; at the measured sampling the result is bit-for-bit what it was.
- **Greyed-out inputs now show what is actually used, never a leftover number.**
  A dialog that offers two ways to give one thing disables the half not
  being typed; that half used to keep whatever it held when the dialog
  opened, and read as the result.
  - k conversion (Map and Cut): points and step sizes are one grid seen two
    ways. Whichever is chosen is typed; the other follows it -- the step the
    counts give over the current k range (which also moves with Γ, the
    rotation and the energy offset), or the counts the steps round to. The
    note under the boxes that used to carry this is gone. The boxes are now
    labelled *step*, not *resolution*: they set the grid spacing, not the
    momentum or energy resolution of the measurement.
  - Brillouin zone, moire: with "Same lattice, twisted" on, the greyed
    bottom-layer a/b/gamma show the top layer's lattice (the one used), not
    3 Å / 3 Å / 120°.
  - Multi-slice figure: in "evenly spaced" mode the greyed list shows the
    positions it gives; with typed positions, the greyed number/from/to
    show how many and their range.
  - Crop / normalise: switching bounds between "by value" and "by index"
    rewrites what is typed, so the bounds keep pointing at the same points
    instead of 1.2 eV being read as point 1.2.

## 1.0.7 — 2026-10-26

- **BESSY One Cube / One Square and SOLARIS URANOS loaders.** All three
  write Scienta SES files, so the SES reader moved out of the Bloch module
  into `loader/formats/ses.py`, and each beamline is a small `SESLoader`
  subclass that claims its own headers (`loader/beamlines/bessy.py`,
  `loader/beamlines/solaris.py`). Written against the headers uploaded to
  `for loader/BESSY` and `for loader/SOLARIS`.
  - One Square's map steps `P-Axis` under a `Point [deg]` label, and its
    run-mode table starts each row with a running number; the motor is now
    also matched against the wave's own axis, so the map is a polar map
    that converts to k.
  - URANOS numbers manipulator points `1, 2, 3 ...`; the motor that moves
    along a dimension (and only that one) now gives the real axis. Motor
    names with a trailing colon (`X:`) and One Square's `P-Axis R-Axis
    Z-Axis` are known.
  - A two-motor manipulator scan is a spatial scan even when one motor is
    an angle (One Square steps polar against Z).
  - The SES `.txt` export with one region per photon energy (how URANOS
    saves a kz scan) opens as one kz map, each region referred to E_F by
    its own hv. APE's `.txt` now uses the same path.
  - One Cube leaves `Location=Scienta`, so it is also recognised by its
    analyser's serial.
- **The code is grouped into subpackages.** `tools/` into `momentum`,
  `crystal`, `processing`, `spectra`, `output`, `runtime`; `ui/` into
  `launcher`, `viewers`, `panels`, `common`; `loader/` into `beamlines`
  (the `_loader` suffixes dropped) and `formats`; `test/` into `loaders`,
  `tools`, `ui`. Only import paths changed. `test_imports` now walks the
  subpackages and checks each has a docstring.

## 1.0.6 — 2026-10-26

- **Elettra APE and ASTRID2 SGM4 loaders, ported from peaks.** No files
  from either beamline were at hand, so both follow the peaks readers. The
  tests build files the way those readers expect them.
  - `loader/ape_loader.py`: APE writes the same SES files as Bloch, so the
    SES reader became a base class (`SESLoader`) with a facility of its own.
    A file is APE's when the `Location` in its header says APE or Elettra.
    The run-mode table now matches motors by name in either beamline's
    spelling (`A P T X Y Z`, `polar tilt X Y Z`). APE's `.txt` spectra are
    read with the CASSIOPEE Scienta parser.
  - `loader/sgm4_loader.py`: `ScanDetails` gives the axes, and
    `TransformedData` holds one row per point with the first slow axis
    fastest. A grid view reads only what is indexed, and pads a stopped
    scan with NaN. The deflectors open as a map, stage axes as a spatial
    scan, and a grating's photon energy as a kz map with SGM4's
    `W = 4.416 eV`. A knife-edge scan is listed but not opened.
  - A `Layout` can now carry the beamline's own work function for kz-map
    referencing. Without one, it is still the 4.5 eV assumed before.

## 1.0.5 — 2026-10-26

- **MAX IV Bloch files open.** `loader/maxiv_loader.py` reads the Scienta
  SES files that Bloch's DA30-L writes. It was written against the headers
  of a cut, a photon-energy scan and a spatial scan (`.ibw`), and the `.ini`
  files of a deflector-map `.zip` (`for loader/MaxIV`). It was checked
  against the SES reader in peaks.
  - `.ibw` files are read by a small version-5 Igor reader written here, so
    `igor2` is not a dependency. The wave's column-major layout is already
    `(*scanned, angle, energy)`, so it is memory-mapped and nothing is read
    until it is looked at. The SPEM file is 1 GB, so this matters.
  - A cut opens as a cut, and a CIS (photon-energy) scan as a kz map. A
    manipulator scan opens as a spatial scan (`spem_4d`), or as a map when
    it steps one motor. `Point` and `Position` are named after the motor
    whose column repeats them in the run-mode table, which is X and Y at
    Bloch.
  - SES's binding-energy axis is negated into `E - E_F`, with no work
    function added, because SES has already referred it.
  - A `.zip` deflector map opens as a map that converts to k. Each region
    in `viewer.ini` is its own dataset. Its `.bin` is mapped in place when
    stored and read into memory when compressed.

## 1.0.4 — 2026-10-26

- **ALBA LOREA, Diamond I05 and Diamond I05-1 files open.** Three new
  loaders read these beamlines' NeXus `.nxs` files. They were written
  against `h5info` dumps of a cut, a deflector map, a photon-energy scan and
  a spatial scan from each (`for loader/*.mat`). ALBA is `loader/alba_loader.py`.
  Both Diamond branches are in `loader/diamond_loader.py`, because they write
  the same dialect, and each is registered as its own loader. What they share
  is in `loader/nexus_arpes.py`. A cut opens as a cut, a deflector scan as a
  map that converts to k, a photon-energy scan as a kz map, and an XY scan as
  a spatial scan.
  - Detection is by structure. ALBA's `NXdata` names its signal and axes,
    Diamond's spectra are in `entry1/analyser`, and neither is claimed by
    the ANTARES reader. The two Diamond branches are told apart by
    `instrument/name`, then the file name, then the I05-1 zone plate.
  - A Diamond spatial scan stores both motors on the whole grid. The motor
    each dimension steps is read from the values, not assumed from the
    order.
  - kz maps are put on one `E - E_F` axis. At ALBA this is the file's own
    binding energy, with its sign checked against the kinetic axes, and the
    work function is taken from the two. At Diamond each spectrum is
    referred by its own hv with `W = 4.5 eV`, and resampled only when the
    windows do not coincide.
  - Everything but a kz map is read lazily.

## 1.0.3 — 2026-10-26

- **ALS MAESTRO (BL 7.0.2) files open.** A new loader,
  `loader/maestro_loader.py`, reads MAESTRO's `.h5` files. It is ported
  from the MAESTRO reader in TensorSpec (fawkesdx/TensorSpec, MIT), which
  worked the layout out against real files. That covers the scan plan in
  `Headers/Low_Level_Scan`, the `(angle, energy)` detector plane whatever
  `unitNames` says, and the point order of each scan kind. A deflector scan
  opens as a map and an XY mesh as a spatial scan. A two-motor line opens
  as one map per X position, and a focus scan as one spatial scan per
  deflector step, because this program has no 4-D or 5-D kind for them. A
  single swept spectrum opens as a cut. Changes from TensorSpec:
  - The spectra are read lazily, so a large spatial scan opens at once.
  - For a swept `Process_000`, only the `0D_Data` channels the scan plan
    names are taken as motors, so a drifting readback such as the beam
    current no longer breaks the grid. A grid is accepted only if it
    reproduces every recorded position, with each axis running one way.

## 1.0.2 — 2026-10-25

Every tool now opens on the conventional setting, and settings say what
they do.

- **Self-normalisation starts on the usual choice, and says what it does.**
  *Crop / bin / normalise → Normalise* opened with no axis ticked, and its
  "Along" was easy to read as "the axis that is kept". Ticking only the
  energy of a map therefore normalised each EDC when each cut (slit ×
  energy) was meant, and nothing warned about it. Results made that way
  should be redone. A **Normalise** menu now picks the piece in ARPES
  terms. It starts on *each EDC* for a cut and on *each cut (slit × energy
  at one scan step)* for a map, k-map or kz map. Each kind also offers its
  other sensible choices, and *custom* for anything else. The ticks are now
  called **Summed over** and can still be changed by hand. A sentence under
  them says what the current ticks do. The energy window (**Sum only
  over**) used to apply silently to the first ticked axis; it now names its
  axis and starts on the energy.
- **The 3-D panel's smoothing does something when applied straight away.**
  Its widths started at 0, which left the data unchanged. They now start at
  1/100 of each axis, like the 2-D panel's. *First axis* and *second axis*
  are replaced by the plane's real axis names (*Second derivative along
  Kinetic energy*). *Normalise each line* now says which way the lines run,
  and offers both directions.
- **Symmetrise mirrors k, not energy.** The 2-D mirror line started at 0°,
  which flips a cut top to bottom in energy. It now starts at 90° through
  angle (or k) = 0, i.e. k → −k.
- **The Fermi cut-off starts at an E_F on the axis.** It started at 0 eV,
  which is wrong for a kinetic-energy cut. It now uses the E_F, temperature
  and resolution the file records, as the MDC/EDC fit panel does. When no
  E_F is recorded, it uses the steepest fall of the angle-integrated EDC.
- **The map k conversion keeps the measured resolution.** kx and ky
  defaulted to 100 points each, which threw away most of a slit's channels.
  They now start at the measured numbers of deflector and slit angles, as
  the cut conversion already did. *Theta offset / Phi offset* are renamed
  **Γ deflector angle / Γ slit angle**, the names the cut conversion uses
  for the same two numbers. *k element no.* is now **k points**, and *by
  element number* is now **by number of points**.
- **Joining starts on the axis the pieces differ along**
  (`tools.combine.guess_join_axis`). Cuts taken in two energy windows used
  to be offered "join along angle".

Tests: `test/test_defaults.py`. `test/conftest.py` now keeps the first
QApplication for the whole session. Each GUI module's own `app` fixture
used to let it be destroyed and re-made between modules. A widget still
alive at that point (here the processing dialogs, held by a queued
`QTimer.singleShot`) made a later module crash with a segmentation fault.
The program itself only ever has one QApplication.

## 1.0.1 — 2026-10-25

- **Swept-mode kz maps from CASSIOPEE open.** The beamline takes an hv scan
  by calling the Scienta analyser once per photon energy, each time with a
  start and end kinetic energy that is only approximately the window asked
  for, so the members' energy axes differ by a point or two (341 channels
  in one, 339 in another). The loader refused any series whose spectra were
  not the same size. A photon-energy series is now cut at the end of the
  energy axis to its shortest member. Nothing is interpolated, every member
  keeps its own start energy, and the info panel says how many points were
  kept (`cassiopee.energy_points_kept`) and trimmed. Fixed-mode hv scans
  have no such wander and are unchanged. A polar or repeated series of
  unequal spectra, and any series whose angle channels differ, is still
  refused.
- **The real reason is shown when a text file fails to load.** A loader
  error on a `.txt` file was handed to the NeXus reader as a fallback, and
  the user saw only "Not an HDF5/NeXus file". The fallback now applies to
  HDF5 files alone.

## 1.0.0 — 2026-10-25

The first numbered version. Updates come often, and without a number a user
could not tell which build they had or whether a fix had reached them.

- **Version and where to get help, in the main window.** The title bar reads
  *ARPES viewer v1.0.0 (updated 2026-10-25)*, and the foot of the main
  window repeats it with a link to
  <https://github.com/DingPei1995/ARPES-viewer> for bug reports
  (Issues) and the latest version. The number lives in `version.py`; bump
  it, and its date, with every change that reaches users, and head the
  changelog entry with it.
- **Names that say what they do.** The main window's *Data operations...*
  and *Process...* could not be told apart by name. They are now
  **Crop / bin / normalise...** (tabs *Crop (truncate)*, *Normalise*,
  *Bin (compress)*) and **Smooth / derivative...**, beside **Combine
  datasets...**, in a box titled *With the selected datasets*. The viewers'
  Functions section *Data operations* is **Transform**, and entries were
  renamed: *Fermi level* → **Fermi edge fit**, *Cut / Map k conversion* →
  **Convert to momentum (k)**, *kz map processing* → **Align Fermi levels
  (kz map)**, *kz -> momentum* → **Convert to momentum (kz, k∥)**, *FS
  correction* → **Straighten bands (FS correction)**, *De-grid* / *De-grid
  map* → **Remove detector grid**, *Slice figure* → **Multi-slice figure**,
  *Open slice in a new panel* → **Freeze slice in a new window**, the list's
  *Plot as a figure* → **Open in figure composer...**, the curve viewer's
  *As a figure* → **Figure composer...**. The guides carry an old → new
  table.
- **Plot tools on every viewer.** A **Plot tools** button on the top row of
  every viewer (and of frozen slices and the curve viewer) draws on the live
  plot: vertical, horizontal and angled guide lines and text labels, each
  with its own colour (nine one-click colours or any other), width, line
  style, label and size; placed by typing or by clicking, dragged on the
  plot, edited or removed from a list. Guides stay while the slice moves and
  are drawn into the panel's image export (*Include the Plot tools guides*).
- **"Plot tools" no longer names two different things.** A frozen slice's
  button that opened the figure composer was called *Plot tools*, and so was
  the composer's own button for its settings dialog. They are now
  **Figure composer...** and **Figure tools...**, and *Plot tools* is the
  new live-plot tool above.
- **Combine datasets: stack or join, any structure.** *Combine* took only
  cuts with identical axes. It now also **joins** pieces of one measurement
  end to end along one of their own axes -- a map whose deflector range was
  scanned in parts, a kz map whose photon-energy range was split over runs,
  a cut whose energy window was taken in halves; cuts, maps, kz maps and
  k-maps, one kind at a time (`tools/combine.py`). Pieces on one grid are
  copied as measured; a different step or a half-step offset is
  interpolated onto the first piece's step; other axes that differ are
  resampled onto the range all pieces cover; overlaps are averaged or the
  earlier / later piece kept; gaps are left at zero. The dialog lists each
  piece's range and the result before anything is computed. Cuts that
  cannot be stacked are now offered *Join* instead of being refused.
- **User guides** (en, zh, fr, and PDFs) and screenshots updated for all of
  the above.

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
