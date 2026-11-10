# Changelog

Round-by-round history of ARPES viewer, newest first. Each entry says what
changed and, more usefully, *why*. The minor versions before the current
one are each merged into one summary (1.2, 1.1, 1.0), and the forty-eight rounds
before 1.0.0 ten at a time at the end. When a new minor version starts
(1.2.x to 1.3.0, say), the previous one's entries are merged into one
summary of it.

What the program does and how to use it is in [README.md](README.md); this
file is the record of how it got that way.

---

## 1.3.3 — 2026-11-10

A Fermi-pocket analysis for quasi-two-dimensional samples (under test), a
minimum-gradient window, a self-energy that states its bare band, and the
agent's steps saved as one script.

- **The SPEM viewer is two windows: the spatial map, and its spectrum in
  the cut viewer.** Each can be sized and placed on its own, and the
  spectrum window has every tool a cut window has (k conversion, band
  straightening, saving or freezing the slice), acting on the spectrum on
  screen. Closing either closes both, and neither keeps the other in
  memory afterwards (`SpatialScanWindow`, `SpemCutWindow`).
  - *Selection boxes above the pictures, applied on Refresh.* "Selection
    box" and "Integrate selection into the other panel" left the
    right-click menu. A row above each picture now holds the box, its
    corners and **Refresh**: dragging the box or typing corners computes
    nothing, and the integration -- the spectrum summed over the map's box,
    or the map summed over the spectrum's k and E -- runs only when Refresh
    is pressed, since on a large scan it reads much of the file. While the
    map's box is on, the spectrum is its sum and no longer follows the
    cursor; unticking the spectrum's box brings back the full map
    (`widgets.SelectionBar`).
  - *Energy or k against position.* Two boxes above the map, "E vs
    position" and "k vs position" (one at a time), draw beside and under
    the map the spectrum through the cursor against each spatial axis,
    sharing the map's axes. Two dashed lines on the spectrum set the band
    of k (or of energy) it is integrated over; only that band of one line
    of pixels is read, and only once the cursor rests
    (`widgets.spatial_profile`).
- **Removed: "Line profile..." and "Stack plot of the selection..." from
  the pictures' right-click menu.** Little used, and the second depended on
  the selection box that has left the menu. The Stack plot button of the
  tool panel is unchanged.
- **Fixed: settings put back from last time that left a picture and its
  controls out of step.** Two cases of one mistake -- a control is filled
  in from what was remembered, and the thing on the picture it is tied to
  is not told.
  - *Map k conversion: the Γ boxes stopped following the cursor.* When the
    dialog opened with the Γ remembered from the last conversion of a map
    of the same size, it counted that Γ as typed by the user and never read
    the contour's readout cursor again: dragging the cursor changed nothing
    in "Γ deflector angle" and "Γ slit angle". (It showed after any earlier
    conversion of a same-size map, in this session or a previous one;
    nothing another viewer did with its own cursor is involved.) The boxes
    and the cursor are now one setting shown twice, as the cut conversion's
    Γ line and box already were: dragging the cursor always fills the
    boxes, and typing a value moves the cursor to it. A typed Γ outside the
    map stays in its box -- it is a legitimate origin -- and the note says
    the cursor cannot sit on it (`KConversionDialog.place_cursor`).
  - *Detector corrections: the trapezoid did not match "Stretch along".*
    The choice of axis came back from last time, the yellow trapezoid's
    corners (which are not kept) stayed laid out for the other axis, and
    with "Correct a trapezoidal image" also ticked the preview showed a
    correction that meant nothing. The trapezoid is now laid out again for
    the restored axis, and by "Defaults" (`DetectorDialog._settings_applied`).
  - Checked and found sound: the cut k conversion (Γ line and box), the kz
    conversion, the Brillouin-zone dialog, the tight-binding, crystal,
    calculated-bands and repeats windows, and the linked cursors of a map's
    contour and cut windows after one of them is closed with its cursor on.
- **Fermi pocket (quasi-2D)...** (tool panel → Advanced, k-maps;
  `tools/spectra/pocket.py`, `ui/panels/pocket.py`, `L.fermi_pocket`).
  **Under test, and only for quasi-two-dimensional samples**: the window,
  the button's tip, every result and the agent's operation say so. The
  area of a contour in one map is a property of the Fermi surface only
  when the bands do not disperse along k_z; for a three-dimensional Fermi
  surface the map is one curved, k_z-smeared sheet through it and the
  numbers mean nothing. The program cannot tell the two apart.
  - *The contour.* From a point inside the pocket, rays go out at equal
    angles; a Lorentzian on a straight background fitted along each, inside
    a ring the user sets, gives k_F there with an error. A ray that
    disagrees with its neighbours is fitted again near them and dropped if
    it still disagrees; a peak needs data on both sides, five times the
    ray's noise, and 2 % of the plane's range. The radius against angle is
    a Fourier series (optionally with only the harmonics an n-fold axis
    allows), and the area follows from its coefficients exactly, with an
    error from their covariance. The area does not depend on the centre.
  - *What the area gives.* Carrier density `g N A/(2π)²`, the fraction of
    the zone and carriers per in-plane cell (Luttinger's count), the
    quantum-oscillation frequency `(ħ/2πe) A`; from the area at several
    energies the cyclotron mass `(ħ²/2π) dA/dE` (its sign says electron or
    hole pocket), the area at E_F off the line, the mean Fermi velocity.
    Several pockets are counted together, electrons minus holes.
  - *What it warns of.* Fewer than a third of the rays finding a band is
    refused; rays lying more than a quarter of a peak width off the
    contour (two bands in the ring, too few harmonics) are pointed out.
    The errors are statistical only, and the window says so.
  - Checked on a synthetic warped pocket of known area and mass (area
    within 1 %, mass within 2-3 %, electron and hole), not yet on
    measured data.
- **Minimum gradient...** (tool panel → Advanced, cuts and maps;
  `process.minimum_gradient`, `L.minimum_gradient`). Along a band's crest
  the intensity's gradient is smallest (He, Wang and Shen, Rev. Sci.
  Instrum. 88, 073903 (2017)): `I/|∇I|` (the default), `1/|∇I|` or `|∇I|`,
  on axes and intensity mapped to [0, 1], with a floor and an anisotropy
  ratio. First derivatives only; neither axis favoured. It replaces the
  `I/|∇I|` mode that was hidden in the Curvature window, for cuts only.
- **Self-energy.** The Kramers-Kronig check was wrong (it integrated over
  the fitted range only, with the wrong sign, and moved the curve to the
  mean of Re Σ): `dispersion.kramers_kronig` now takes |Im Σ| as the same
  on both sides of E_F and constant beyond the range, integrates exactly,
  and fits no constant. The bare band is chosen in the window and written
  into the result -- a line through the band at two energies, a line of a
  typed velocity through the measured k_F, or the Dispersion window's fit
  -- and **Suggest (Kramers-Kronig)** finds the velocity that makes the two
  curves a pair. Reported: k_F, v_F, `v_bare/v_F − 1`, λ, the kink energy,
  |Im Σ| at E_F with lifetime and mean free path. To the list, or CSV.
- **Save the steps as a script...** (AI assistant; `ui/common/agentsteps.py`,
  `L.session_script`). Every step the agent ran -- command files and MCP
  requests, which were kept in memory as one line each -- as one Python
  file with times, failures (as comments) and output; it runs again from
  `viewer_cmd/`. A prompt option, on by default, has the agent write it at
  the end. Steps done by hand are in each dataset's history, not here.
- **Documents.** The user guides (en, zh, fr): §5.1 minimum gradient, §5.4
  the self-energy window, the new §5.8 Fermi pocket with its notice, §7.3
  and §7.4 the saved script. `devtools/guide_screenshots.py` follows the
  1.3.2 row names again and takes the two new windows.

## 1.3.2 — 2026-11-04

An AI agent started in one step, and driven through documented operations
instead of the program's internals; with later work up to 2026-11-05.

- **`L`, the documented operations** (`ui/common/live.py`): about fifty
  operations on the named rows of the list -- looking at data, the Fermi
  level, processing, momentum conversion, the Brillouin zone, figures, the
  tool windows, one's own computation. Each adds rows with their history
  and overwrites nothing. Command files, `viewer_python` and the MCP tools
  `viewer_api` / `viewer_api_help` all reach it.
- **`API.md`** (`arpes_viewer/agent/`, package data), generated from the
  program: one file an agent reads instead of the source. A test fails
  when it falls behind.
- **AI assistant...** at the top of the tool panel: two folders, a few
  options and a request make one prompt; **Copy the prompt and start**
  starts the command folder or the agent bridge. The window lists each
  step with its output, **Pause the agent** holds its commands, and the
  button is a status light (grey, green, yellow, red).
- **From a day of real data processed by an agent**: agent windows no
  longer flash on screen; row names unique from the start (a CASSIOPEE cut
  after its file); `L.add_files` reports what it left out;
  `L.fermi_edge_search` lists the candidate edges and `L.fermi_edge` draws
  each fit; `map_to_k` / `cut_to_k` take `ef=` and `normalise_axes=` (one
  call, one row); `L.cut_arithmetic`, `L.slice_grid`; the working rules in
  the prompt and the reference.
- **Paths written the system's way** everywhere a path is shown or passed
  on (`ui/common/paths.py`).
- **A map whose scan was stopped before its end** opens as far as it went,
  from every beamline (`loader/incomplete.py`): unmeasured steps and a
  clearly weaker last step are cut, and the dataset says so. CASSIOPEE
  judges by intensity, not by the parameter file. An image with no finite
  value is drawn blank.
- **No silent wait** when a tool reads a map not yet opened: a progress
  window after 0.4 s.
- **Saving over the file a row was read from** is done in one step, with
  one question first.
- **One naming rule for processed data** (`tools/runtime/naming.py`): the
  source's name plus one bracketed tag per step, oldest first; "Sort by
  data type" groups by the last tag. Agents name rows the same way
  (`L.naming()`).
- **The SGM4 reader** follows the beamline's Igor loader
  (`ScanDetails/dimensions`, `Dim<n>_*`).
- **The user guides rewritten** (en, zh, fr and PDFs) in eight parts that
  follow the screen, each part a file in `docs/guide/<lang>/`, assembled by
  `devtools/build_guide.py`.

## 1.3.1 — 2026-11-03

From a day of real data processed by an agent (the session's own review of
what the program got in its way).

- **kz conversion.** The manipulator theta is off by default and, when
  ticked, is an offset from Γ, not the motor's absolute reading (which was
  used as the polar angle before). The output grid starts from the
  measurement -- one k∥ point per analyser channel, k_z with the same step
  -- instead of 256 × 256. V0 may be negative, and **Γ at hν → Set V0**
  gives the V0 that puts Γ at normal emission at a chosen photon energy.
  The preview energy is a slider beside the picture, under the data
  viewers' colour controls (colour map, Flip, level bar with gamma). The
  settings column is compact (related inputs on one line); the V0-scan tab
  is gone (Γ at hν replaces it); k_par is written k//, and its direction is
  a rotation about the normal only. **Show the k_z plane in the 3D BZ...** opens the BZ
  overlap tool's cut-plane view with the plane the map measures, its
  high-symmetry points and the measured k_z range in zone periods.
  **Calibrate hν from each fitted E_F** is an option, off
  by default: after the Fermi level has been fitted per photon energy, it
  uses hν − E_kin(E_F) measured at each one instead of the single work
  function (the default stays: E_F flattened, no hν calibration).
- **The "Fermi edge still bends" warning** gave 0.37 eV on a flat edge: it
  was the largest minus the smallest steepest-fall position over single,
  unsmoothed channels, so one weak slit-end channel or a band crossing E_F
  set it. Now blocks of channels, smoothed, the weak ones left out, and the
  range of a robust parabola through them.
- **A Fermi fit with no edge is refused**, with the reason (E_F at the
  window's end, no significant step, E_F undetermined, and a hint that the
  data may have been normalised), in the Fermi window and in the agent's
  `fermi_edge`, instead of returning E_F = 75.2 ± 4.6 eV.
- **An unfinished CASSIOPEE map** (one spectrum without its `_i` file) keeps
  its angle axis; the spectrum is left out and named
  (`cassiopee.dropped_members`).
- **Brillouin-zone overlays are drawn edge by edge, each once**, on the
  contour, in exports and in the kz preview: tiled zones share edges, and a
  dashed edge drawn twice came out solid. Closing BZ overlap no longer
  keeps a plane turned without Plot as the "last used" one.
- **3D BZ: two frames, two sets of names.** The crystal's axes are k_a, k_b,
  k_c by default; the sample's k_x, k_y, k_z (k_z along a chosen cleavage
  plane's normal, k_x along the maps' k_x) on request, as the data has
  them. `look_along` takes "oblique", an axis name or a vector. Labels can
  be sized for the final panel (pt at a panel width in mm) rather than
  scaled with the picture.
- **Slice series**: titles carry the value asked for (−0.2 eV), the plane
  used kept in each panel's information; colour map, levels (percentiles)
  and gamma at creation; the map's zone drawn on every constant-energy
  panel; no "Mean of empty slice" warnings; and `slice_figure(values=...)`
  / `A.open_slice_series(values=...)` without the modal dialog.
- **Figure composer**: a panel can take several grid cells (`span`) and a
  picture keeps its own shape in them; the page height follows panels moved
  by hand; *…but tick numbers on every panel* keeps inner panels' numbers
  with the axis names on the edges.
- **Two pictures drawn transposed under their axes**: the kz-conversion
  preview (k_z and k// swapped against the axis labels and zone lines) and
  the k⊥-integrated image under the calculated contours (mirrored across the
  diagonal). Both were handed to the row-major image item untransposed.
- `agentic/config.json` and `config.example.json` hold a placeholder, not a
  local data path; the live viewer says so when `data_dir` is not a folder.
- **For agents**: a modal dialog opened from `viewer_python` or a live-viewer
  command raises `ModalDialogBlocked` instead of freezing it (warnings are
  printed and answered); `FigureWindow.describe()` / `render(path)` and the
  MCP tools `viewer_figure` / `viewer_render_figure` give a figure in
  numbers and as the PNG it prints as. Recipe r05 uses these.

## 1.3.0 — 2026-11-02

Using an AI agent with the program, made approachable for a newcomer.

- **A beginner's guide in `agentic/README.md`.** The three ways to let an
  agent work with the program -- the MCP server (no programming), scripts
  written by a coding agent, and the live viewer driven through folders --
  with which to choose; connecting Claude Desktop, Claude Code or another
  MCP app step by step, including when the app cannot find
  `arpes-viewer-mcp`; the tools the agent gets; first requests; good
  habits; a troubleshooting table and a glossary.
- **`agentic/PROMPTS.md`**: requests to copy into the chat, from the rules
  for a session and a first look at a folder, through the Fermi edge and
  momentum conversion, to a batch over a beamtime and checking what came
  back.
- **`agentic/examples/`**: three scripts on the headless workspace -- a
  first look at a folder, a cut taken to momentum on E − E_F, a map taken
  to constant-energy contours -- that run with no arguments on the demo
  data, keep the physical parameters at the top, and are tested
  (`test/agent/test_examples.py`).
- **The live viewer runs anywhere**: `launch_viewer.py` and
  `viewer_live.py` start on macOS and Linux as well as Windows, create
  their working folders on first start (the guide said they were shipped;
  they were not), and say what to do when `config.json` is missing;
  `agentic/.gitignore` keeps the working folders and `config.json` local.
- The README's agent section brings the scripted route and the MCP server
  together, and points newcomers to the guide.

## 1.2 — 1.2.0 to 1.2.4, 2026-10-28 to 2026-11-02

The pip package, the step-by-step tools, the crystal and the calculation
side of the program, and the first ways for an AI agent to use it. The
last items below were made after 1.2.4 had been uploaded to PyPI, and first
published with 1.3.0.

- **Packaging and terms** (1.2.1–1.2.2): `pip install arpes-viewer`
  (`arpes-viewer` command), the PolyForm Noncommercial licence, the
  authorship stated in `NOTICE`, `CITATION.cff` with a Zenodo DOI, and the
  repository renamed `DingPei1995/ARPES-viewer` (1.2.3). Errors kept in a
  log file instead of a console window to close by mistake; a progress bar
  for every long step; Enter in a field takes the value, never presses a
  button.
- **Step-by-step tools** (1.2.0): sum repeated scans (with χ² checks of
  whether the sample changed), ridge detection, detector corrections
  (keystone and bad regions), a tight-binding fit, a crystal-structure
  view, calculated bands and stacked slices, each leading through numbered
  steps; the windows ask before closing and remember their settings
  (1.2.1).
- **Calculated bands** (1.2.0–1.2.1): Wannier90, Wien2k, VASP, Quantum
  ESPRESSO and the FPLO + Wannier tools' files recognised by content; bands
  along a path, contours on any plane, a 3-D Fermi surface; a fitted
  renormalisation Z and shift against a measured cut.
- **The figure composer** gets its own `.afig` format with the data and the
  source files, and arranging tools; Igor Pro export; demo data and example
  figures (1.2.0).
- **k-maps and the 3-D views** (1.2.4): the k conversions' energy rows
  (*Energy axis as E − E_F*, the offset behind a tick box); 3-D views of a
  k-map open on the filled planes; a slice-series figure of a map not on
  screen no longer vanishes.
- **The list and Combine** (1.2.4): a search box and sorting by name or
  type; *Combine* stacks cuts that share one axis (the other truncated to
  the common range) and sums repeated scans.
- **Crystal, Brillouin zone and tight binding** (1.2.4 and after): the
  space group first and the cell it allows; CIF files read block by block
  (a FullProf file had failed); **3D BZ** with any number of planes, each
  able to carry a measured map, and of coloured paths; *BZ overlap* for
  the old zone tool; the **Figure** tab (figure composer on top). The
  tight-binding fit groups neighbours by **symmetry orbit**, says it fits
  **one band**, and can fit **two hybridised bands** with their coupling
  and gap.
- **AI agents** (1.2.3–1.2.4): the file-based agentic workflow
  (`agentic/`, `docs/AGENTIC_WORKFLOW_en.md`) and the **MCP server**
  (`arpes-viewer-mcp`; `arpes-viewer --agent-bridge` to drive the window).
- **Code and documents** (after 1.2.4): `loader/nxs_file.py` split into
  `loader/scan.py`, `loader/native.py` and `loader/beamlines/antares.py`,
  with the loaders registered on first use; the code's comments describe
  each tool by what it does; the README reorganised (features first, each
  thing said once); this changelog condensed.

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
