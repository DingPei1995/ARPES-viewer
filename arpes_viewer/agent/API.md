# ARPES viewer -- the agent's reference

*Generated from the program by `python -m arpes_viewer.agent.catalog
--write`; do not edit by hand. A test fails when it is out of date.*

Read this before anything else: it is everything the program can do, by
name, so nothing has to be found by reading the source or by pressing
buttons by their text.

## How to use it

In a command file of the live viewer (route 3) -- and in `viewer_python`,
or through the MCP tool `viewer_api` (route 1 with the program on
screen) -- **`L`** is the running program:

```python
print(L.rows())                                   # what is in the list
fit = L.fermi_edge("FS_cut", energy_window=(-0.15, 0.1), temperature=30)
cut = L.shift_energy("FS_cut", ef=fit["values"]["ef"])
k = L.cut_to_k(cut, gamma_slit_deg=0.8)            # -> a new row, its name
L.picture(k, "k", "energy", path=HERE + "/shots/cut_k.png")
L.help("kz_to_k")                                 # one operation in full
```

Rows are named, never guessed; every operation that makes data adds a new
row and records how; nothing is overwritten; no dialog waits for a click.
Results are plain dicts, lists and strings. An error says what was wrong
-- read it rather than retrying blindly.

### Which operation for which step

| Step | Operation |
|---|---|
| What is in the folder / the list | `L.add_files(folder_or_files)` (report its `left_out`, `unrecognised`, `warnings`), `L.rows(compact=True)`, `L.describe(row)`, `L.metadata(row, "photon")` |
| Look without reading the screen | `L.picture(row, x, y, path)`, `L.profile(row, along, ranges, summary=True)` |
| Fermi level, E - E_F | `L.fermi_edge_search(row)` (the candidate edges on that row's axis), `L.fermi_edge(row, window, picture=path)`, `L.shift_energy(row, ef)`; kz map: `L.kz_align_fermi(...)` |
| Clean up | `L.crop`, `L.bin`, `L.normalise` (after the Fermi fit), `L.smooth`, `L.background` |
| Second derivative, curvature, minimum gradient, symmetrise | `L.derivative`, `L.curvature`, `L.minimum_gradient`, `L.symmetrise` |
| Dichroism, difference, ratio of two cuts | `L.cut_arithmetic(a, b, operation="asymmetry", normalise="total")` |
| To momentum | `L.cut_to_k`, `L.map_to_k` (both take `ef=` and `normalise_axes=`: one call, one row), `L.kz_to_k` (V0 from `gamma_hv`) |
| The Brillouin zone | `L.brillouin_zone`, `L.bz_overlay(row, ...)`, `L.bz3d_picture(path, ..., labels="G, L")` |
| A figure | `L.slice_series(row, values=...)`, several maps side by side: `L.slice_grid(rows, values=...)`; `L.figure_from(rows)`, `L.panel_set`, `L.panel_picture`, `L.figure_arrange`, `L.figure_describe`, `L.figure_render`, `L.figure_export`, `L.figure_save` |
| MDC/EDC fits, core levels, tight-binding, calculated bands, 3-D views ... | `L.tools()`, `L.run_tool(action, row)` (section 2) |
| Anything else | `L.data(row)` + the program's functions (section 4) + `L.add(...)` |

Where no operation fits: open the tool on screen with `L.run_tool(action,
row)` (section 2), or compute with the program's own functions (section 4)
on `L.data(row)` and list the result with `L.add(...)` -- and say that you
did.

### Working rules (learnt from real sessions)

- **Look before you compute.** Before a new kind of step, search
  `L.help()`, `L.tools()` and `L.functions()`; the program probably has it
  (dichroism is `L.cut_arithmetic`, not a formula of your own).
- **Never go around an operation silently.** Do not edit the program's
  internal tables (`A.loaded_items` ...); if no operation does it, say
  which one is missing and ask before working around it.
- **After `add_files`**, compare the rows with the folder and report what
  was left out, not recognised or warned about. Rows can be named by their
  number in `rows()` or their file's path when names are not enough.
- **Names**: say which part of a name comes from the file name and which
  from recorded metadata; mark guesses. A processed row keeps its source's
  name and adds one tag **in square brackets** per step, oldest first,
  from the ordered table of `L.naming()` -- `Map80eV [norm] [E-E_F] [k]`,
  never `Map80eV_norm_k`; a `new_name=` of your own follows the same rule.
- **Fermi level**: on raw data, per row, on that row's own axis
  (`fermi_edge_search`); the Fermi edge is the *last* drop to the floor,
  not the steepest one. Draw each fit (`picture=`); rows of the same photon
  and pass energy must agree; when the data cannot decide, ask once.
- **A tidy list**: chain steps in one call (`map_to_k(row, ef=...,
  normalise_axes=(1, 2))`) so only the final row is listed; remove rows
  only when the person agrees.
- **Figures**: test in a `check` folder, publish one version per figure;
  signed quantities get a diverging colour map with symmetric levels.
- **Small outputs**: `rows(compact=True)`, `profile(..., summary=True)` or
  `path=`; arrays to files, not into the conversation. Code files as UTF-8,
  non-ASCII as `\u` escapes.
- **Windows** the operations open and close never appear on screen; the
  ones left open (a figure, a tool for the person) appear on the main
  panel's screen.

## 1. Operations: `L.<name>(...)`

### Start here

#### `L.help(topic='')`

Every operation, grouped, one line each; ``help("name")`` gives
one operation in full, ``help("group")`` one group. Read this (or
``arpes_viewer/agent/API.md``) before anything else: it is the program's own
list of what it can do, so nothing has to be found in the source.

#### `L.status()`

The program's version, how many rows the list has, which windows
are open, and where the agent's folders are.

#### `L.session_script(path, with_output=True)`

Write every step run so far in this session -- command files
and MCP requests, oldest first -- as one Python script at ``path``:
each step's code, when it ran, whether it failed (those are kept
as comments) and, with ``with_output``, what it printed. The record
of the whole processing, and a script that does it again. Call it
at the end, as a step of its own (the step calling it is not yet
in the record). Returns ``{"path", "steps", "failed"}``.

### The list

#### `L.rows(compact=False)`

The rows of the main list: ``row`` (its number, which every
operation also takes in place of a name), ``name``, ``kind`` (Cut,
Map, kz map, k-map ...), ``path`` of the file behind it, and whether
it is selected. ``compact=True`` gives one line per row instead
("3 | Map LH 117eV | Map | D:\...\Map_1_ROI1_.txt"): a long list
costs far fewer tokens that way.

#### `L.add_files(paths, extras=False)`

Add files to the list, the reader detected as by Quick add.
``paths`` is one path or a list; a folder adds every file in it a
reader recognises, and the scans in its sub-folders (a CASSIOPEE
map folder is one row). Returns ``added`` (the names of the new
rows), and what to tell the person before going on:

* ``left_out``: single spectra found inside a sub-folder next to a
  map's numbered scans (a test spectrum, a reference ...) -- not
  part of the map, so not listed unless ``extras=True``;
* ``unrecognised``: files no reader took (parameter files, notes);
* ``warnings``: what a reader noticed, e.g. a polarisation in the
  file name that differs from the one recorded with the data.

Row names come from the file or folder name, with the photon energy
and polarisation the beamline recorded; names are unique.

#### `L.select(*names)`

Select these rows (and only these), as a click would; what the
tool windows act on. Returns the names selected.

#### `L.rename(name, new_name)`

Give a row a new name (made unique if taken). Returns it.

#### `L.naming()`

How a processed row is named: its source's name plus one tag in
square brackets per step, oldest first ('Map80eV [norm] [E-E_F]
[k]'), from the ordered table returned here. Every operation names
its result this way; a ``new_name=`` of your own keeps the tags and
adds the step's tag in brackets too, so "Sort by data type" groups
the list by what was last done.

#### `L.remove(*names)`

Take rows off the list (and drop their auto-saved copies). The
files they were read from are not touched. Only when the person has
asked for it.

#### `L.save(names, path, fmt='')`

Write rows to one file: ``.nxs`` (the program's own format, which
it opens again) or ``.itx`` for Igor Pro; ``fmt`` "nxs"/"igor" if
the extension does not say. Never overwrites: an existing file is
refused.

### Looking at data

#### `L.describe(name)`

A row's kind, shape and axes (label, range, step, points).

#### `L.metadata(name, contains='', limit=200)`

A row's metadata (photon energy, temperature, polarisation,
manipulator, the history of how it was made ...), the keys
containing ``contains`` if given.

#### `L.picture(name, x, y, path, ranges=None, colormap='gray', flip=False, levels=None, gamma=1.0, width=700, height=520)`

Write a picture of ``y`` against ``x`` (axis labels, indices, or
"energy") to the PNG ``path``, integrating the other axes over
``ranges`` ({axis: (lo, hi)}); for looking at data without reading
the screen. Returns what was drawn.

#### `L.profile(name, along, ranges=None, summary=False, path='', max_points=400)`

An EDC or MDC as numbers: the values along one axis, the others
integrated over ``ranges`` ({axis: (lo, hi)}). Hundreds of numbers
cost many tokens: ``summary=True`` gives only the axis range and
step, the maximum (where), the minimum, and the steepest fall and
rise; ``path`` writes the whole curve to a CSV file (then read it
with your own code); ``max_points`` thins what is returned.

#### `L.open(name)`

Open the row's viewer window on screen (as a double-click does).
Returns the window's title.

### Energy

#### `L.fermi_edge(name, energy_window=None, temperature=30.0, ranges=None, fit_temperature=False, picture='')`

Fit the Fermi edge of the EDC summed over ``ranges`` of the other
axes, within ``energy_window`` (lo, hi) on the row's own energy axis.
The temperature is held unless ``fit_temperature``. Returns E_F,
the resolution, their errors and the reduced chi2; a fit that finds
no edge (normalised data, a window without the edge) is refused
with the reason, the row's energy axis, and where the curve falls
fastest. Each row has its own energy axis: choose the window per
row (``fermi_edge_search`` lists the candidate edges), never reuse
another row's. ``picture`` writes a PNG of the EDC, the window and
the fitted curve -- for the person to check, also when the fit is
refused.

#### `L.fermi_edge_search(name, ranges=None, temperature=30.0, fit=True, half_window=0.15)`

Find where the Fermi edge may be on a row's own energy axis, for
choosing the window of ``fermi_edge``: the drops of the EDC (summed
over ``ranges``, raw data) that stand clearly above the noise,
highest energy first. The Fermi edge is the *last* drop, after which
the intensity stays at the floor -- not the steepest one: a band
edge, or the strong drop under a weak tail of pass-energy-20 data,
can be steeper. With ``fit`` each candidate is fitted on its
``window`` and judged (E_F inside the window, a real step, a
resolution, chi2). Returns the axis, the candidates and advice: when
two fit well, the data cannot decide -- ask the person, once, and
apply the answer to the rows of the same photon and pass energy.

#### `L.shift_energy(name, ef, new_name='')`

A copy on E - E_F: ``ef`` (on the row's own energy axis) is
subtracted. Returns the new row's name.

#### `L.kz_align_fermi(name, angle_range, energy_range, temperature=30.0, hold_temperature=True, normalise=True)`

Align a photon-energy scan (kz map) on its Fermi level: one
Fermi-edge fit per photon energy, over the analyser channels
``angle_range`` (lo, hi, inclusive indices) and the energy channels
``energy_range`` (indices), each spectrum shifted to put its own
edge at zero, optionally normalised by its total. Adds the aligned
row (its per-hv E_F kept in ``kz.fermi_level_eV``, which the kz
conversion's hv calibration uses). Returns the new row and the
Fermi levels.

#### `L.fs_correction(name, points=None, reference='', mode='channels', order=2, new_name='')`

Fermi-surface correction (tool panel, Basic). Either by hand:
``points``, [(angle, E), ...] on the Fermi edge in the row's own
units (at least ``order`` + 1); a polynomial of ``order`` through
them is flattened, every angle column shifted. Or from a
``reference``: another row whose Fermi edge has been fitted
(``fermi_edge``, or the Fermi edge fit tool), its fit applied --
``mode="offset"``, the energy axis shifted by its E_F;
``mode="channels"``, every channel on its own E - E_F from its
channel-by-channel fit (blank borders and unfitted channels cut
off). A map (or kz map) is corrected whole, along its slit. Before
the k conversion. Returns the new row (and, by hand, the polynomial,
highest power first, and the number of points).

### Processing

#### `L.crop(name, bounds, new_name='')`

Cut out a box: ``bounds`` is one (lo, hi) per axis in the axes'
own units, None for "to the end". Returns the new row.

#### `L.bin(name, factors, new_name='')`

Sum blocks of neighbouring points: one factor per axis (1 keeps
it). Counts are preserved. Returns the new row.

#### `L.normalise(name, axes=1, window=None, to_peak=False, new_name='')`

Divide the data by its own intensity: every line along axis
``axes`` (an index; 1 = energy for a cut) by that line's total, or
every plane spanned by two axes (``axes=(0, 1)``) by its total; the
sums taken inside ``window`` (lo, hi, on the first of them) if given;
``to_peak`` divides by the maximum. Never before a Fermi fit: fit the
raw data first.

For a map (axes 0 = deflector/polar, 1 = slit, 2 = energy):
``axes=(1, 2)`` divides every cut of the map (one slit x energy
plane per deflector angle) by its own total -- what evens out the
intensity from cut to cut; ``axes=2`` divides every EDC by its total;
``axes=(0, 1)`` every constant-energy plane. ``map_to_k`` can do the
E - E_F shift and this in the same call (``ef``, ``normalise_axes``)
so no intermediate rows are listed.

#### `L.smooth(name, widths, new_name='')`

Gaussian smoothing, NaN-aware; ``widths`` one sigma per axis in
the axis's units (0 leaves it). Returns the new row (tagged
smoothed).

#### `L.derivative(name, axis=1, order=2, window=None, new_name='')`

The (negated) ``order``-th derivative along ``axis`` (index), by
local polynomial fit over ``window`` (axis units). Returns the new
row.

#### `L.curvature(name, mode='2d', a0=1.0, new_name='')`

Curvature of a 2-D cut or map plane: ``mode`` "2d" (isotropic),
"x" or "y" (one-dimensional along that axis); ``a0`` the
dimensionless free parameter. Returns the new row.

#### `L.minimum_gradient(name, form='ratio', floor=0.05, ratio=1.0, new_name='')`

The minimum-gradient picture of a cut, or of every
constant-energy plane of a map: bands are where the intensity's
gradient is smallest. ``form`` "ratio" is I/|grad I| (the usual
one: slow intensity changes cancel, empty regions stay dark),
"inverse" 1/|grad I|, "modulus" |grad I| itself (bands dark).
``floor`` caps the brightness of flat patches (a fraction of the
gradient's RMS; lower it on smoothed data); ``ratio`` above 1
weighs the second axis less. First derivatives only, so less
noisy than ``derivative`` or ``curvature`` -- but smooth noisy
data first (``smooth``). A picture to find bands on, not a
quantity: take numbers from a fit. Returns the new row.

#### `L.background(name, method='percentile', axis=1, new_name='', **options)`

Subtract a background from a cut: ``method`` "percentile",
"polynomial", "shirley" or "tougaard" (see tools/processing), along
``axis`` for the one-dimensional ones. Returns the new row.

#### `L.symmetrise(name, fold=1, centre=(0.0, 0.0), mirror_angles=(), inversion=False, new_name='')`

Average a constant-energy map (each energy plane of a k-map, or a
2-D map) over ``fold``-fold rotations, mirrors at ``mirror_angles``
(degrees) and inversion, about ``centre`` -- which is yours to give,
never guessed. Returns the new row and the residual.

#### `L.cut_arithmetic(name_a, name_b, operation='asymmetry', normalise='total', intensity_floor=0.05, region=None, ranges=None, new_name='')`

Combine two cuts as the Cut arithmetic window does -- dichroism
(LH vs LV, CR vs CL), a difference, a ratio: ``operation``
"asymmetry" (A − B)/(A + B), "difference", "ratio" or "sum";
``normalise`` "total" (B scaled to A's total over the common area),
"region" (over ``region`` (x0, y0, x1, y1)) or "none";
``intensity_floor`` hides points where A + B is below that fraction
of its maximum. Both cuts are first cropped to the range they share
(and to ``ranges``, ((x_lo, x_hi), (E_lo, E_hi)), if given); B is
resampled onto A's grid. Use the same kind of cuts (both in k, both
on E - E_F). The result is signed: show it with a diverging colour
map ("redwhiteblue", flipped for red = positive) and symmetric
levels. Returns the new row, B's scale factor, the summary and any
polarisation warning.

### Momentum

#### `L.cut_to_k(name, gamma_slit_deg=0.0, deflector_deg=0.0, gamma_deflector_deg=None, azimuth_deg=0.0, n_k=None, new_name='', ef=None, normalise_axes=None)`

A cut in momentum (k conversion, cut): normal emission at slit
angle ``gamma_slit_deg``; the deflector or polar angle the cut was
taken at and where Γ is on it, if off normal. A cut already on
E - E_F stays on it. ``ef`` (the fitted E_F on the row's own axis)
and ``normalise_axes`` (as ``normalise``) do the E - E_F shift and
the normalisation in the same call, so the list gets only the final
row; the history records every step. Returns the new row.

#### `L.map_to_k(name, gamma_deflector_deg=0.0, gamma_slit_deg=0.0, azimuth_deg=0.0, n_kx=None, n_ky=None, new_name='', ef=None, normalise_axes=None)`

An angle map in momentum, (kx, ky, E) (k conversion, map): Γ at
deflector/polar ``gamma_deflector_deg`` and slit ``gamma_slit_deg``,
turned by ``azimuth_deg``. Convert a map already on E - E_F, so the
result is too -- or give ``ef`` (the fitted E_F on the row's own
axis) and, if wanted, ``normalise_axes`` ((1, 2): every cut of the
map by its own total), and the shift, the normalisation and the
conversion are one call that lists only the k-map. The kx grid
defaults to twice the scanned angles, at most 100 points (never
fewer than the scan has): one point per scan step gives streaks;
ky to the slit's points. Returns the new row (a k-map).

#### `L.kz_to_k(name, *, space_group, a, b=None, c=None, alpha=None, beta=None, gamma=None, surface_hkl=(0, 0, 1), kpar_rotation_deg=0.0, inner_potential=None, gamma_hv=None, work_function=None, effective_mass=1.0, normal_emission_deg=0.0, theta_offset_deg=None, calibrate_hv=False, n_kz=None, n_kpar=None)`

A photon-energy scan (on E - E_F) in (k_z, k//, E), as the kz
conversion window does it. Give ``inner_potential`` (V0, eV), or
``gamma_hv``: the photon energy at which normal emission passes
through Γ, from which V0 is set. The lattice decides the zone and
the period; ``surface_hkl`` the surface normal; k// runs along a*
(or the first reciprocal axis not along the normal) turned by
``kpar_rotation_deg``. ``theta_offset_deg`` only to correct a
manipulator offset from Γ; ``calibrate_hv`` uses each photon energy's
fitted E_F (after kz_align_fermi). Grid: from the measurement unless
given. Returns the new row, V0 and the k ranges.

#### `L.fermi_pocket(name, centre, r_min, r_max, energy=None, half_width=None, ef=0.0, rays=72, harmonics=6, symmetry=1, spin=2, pockets=1, cell=None, energies=None, recentre=True, picture='', to_list=False)`

UNDER TEST, and ONLY FOR QUASI-TWO-DIMENSIONAL SAMPLES (surface
states, layered materials with negligible k_z dispersion): for a
three-dimensional Fermi surface the area of a contour in one map
is not a carrier density -- ask the person which it is, and say so
with the numbers.

The contour of one Fermi pocket of a k-map (``name``) and its
area: rays from ``centre`` (kx, ky; any point inside the pocket)
find the band between ``r_min`` and ``r_max`` (a ring holding this
band only), on the plane at ``energy`` +- ``half_width`` (default:
E_F = ``ef``, the map's own energy step and a half). The contour
is a Fourier series up to ``harmonics``, with an n-fold
``symmetry`` about the centre if given; ``recentre`` moves the
centre to the contour's middle and traces again.

Returns ``area`` (A^-2) and ``area_error`` (statistical only),
``k_f`` and its extremes, ``rays_kept`` of ``rays`` (many dropped:
look at the ``picture`` and close the ring), and for a quasi-2D
sample ``density`` (cm^-2, ``spin`` states per k, ``pockets``
equivalent pockets in the zone), ``frequency`` (T, of quantum
oscillations), and with ``cell`` = (a, b, gamma_deg) of the plane
``zone_fraction`` and ``per_cell`` (carriers per cell). With
``energies`` (a list, the first where the pocket is clearest)
also ``mass`` (cyclotron mass in m_e, positive for an electron
pocket, negative for a hole pocket), ``area_at_ef`` and
``series`` (the area at each energy). ``picture`` writes a PNG of
the window (plane, rays, contour) to check it; ``to_list`` adds
the contour (and the area series) as curve rows.

### Crystal and Brillouin zone

#### `L.brillouin_zone(space_group, a, b=None, c=None, alpha=90.0, beta=90.0, gamma=None)`

The zone's high-symmetry points (Cartesian, Å⁻¹) and the
reciprocal vectors, for a space group and cell; the parameters the
space group fixes are set by it.

#### `L.read_cif(path)`

A CIF file's cell, space group and atom sites.

#### `L.bz_overlay(name, *, space_group, a, b=None, c=None, alpha=None, beta=None, gamma=None, hkl=(0, 0, 1), offset=0.0, azimuth_deg=0.0, kpar_hkl=(0, 0, 0), repeat=True, labels=True, irreducible=False, layer_2d=False)`

Draw the Brillouin zone on a k-map (or a converted kz map) and
keep it with the row, as BZ overlap does: the cut of the 3-D zone by
the plane normal to ``hkl`` at ``offset`` (Å⁻¹ along it), turned by
``azimuth_deg``; for a kz map, ``hkl`` is the surface normal and
``kpar_hkl`` the k// direction. ``layer_2d`` uses a plane lattice
(a, b, gamma) instead. The zone then goes into slice series and
exports. Returns what was drawn.

#### `L.bz3d_picture(path, *, space_group, a, b=None, c=None, alpha=None, beta=None, gamma=None, planes=((0, 0, 1, 0.0),), paths=('',), frame='crystal', surface_hkl=(0, 0, 1), azimuth_deg=0.0, axes=True, labels=True, left_labels='', view='oblique', size=(1600, 1600), panel_mm=0.0, text_pt=8.0)`

A picture of the 3-D Brillouin zone (the 3D BZ window), for a
schematic panel: ``planes`` as (h, k, l, height) with height in units
of the reciprocal vector (0 through Γ, 0.5 the zone top); ``paths``
like "G-M-K-G"; axes in the crystal frame (k_a, k_b, k_c) or, with
``frame="sample"``, the data's (k_x, k_y, k_z: k_z along
``surface_hkl``, k_x turned by ``azimuth_deg``); ``view`` "oblique",
an axis name or a vector; ``labels`` True (every high-symmetry
point), False (none) or the ones to show ("G, L" or ["Γ", "L"]);
labels sized for a ``panel_mm`` wide panel at ``text_pt`` if given.
Never overwrites ``path``.

### Figures

#### `L.slice_series(name, values, *, axis=2, half_width=0.0, cols=3, nominal_titles=True, shared=True, colormap=None, flip=None, percentiles=(0.0, 100.0), gamma=1.0, zone=True, zone_style='solid', title='', high_factor=1.0, zone_color=None, zone_width=0.6)`

A page of slices through a map (Slice series figure): one panel
per value along ``axis`` (2 = energy), each the planes within
``half_width``, titled with the value asked for; colour map, levels
(each panel's ``percentiles``, the span stretched by ``high_factor``
so the strongest intensity is not saturated; ``shared=False`` keeps
each panel's own), gamma at creation; the row's Brillouin zone on
constant-energy panels, in ``zone_style`` ("solid", "dashed"),
``zone_color`` ("#RRGGBB", or "#AARRGGBB" for a see-through line,
e.g. "#B8D62020") and ``zone_width`` (pt). Several maps side by
side: ``slice_grid``. Returns the figure in numbers (its title names
it for the other figure operations).

#### `L.slice_grid(names, values, *, axis=2, half_width=0.0, column_titles=None, colormap='gray', flip=False, percentiles=(0.0, 100.0), high_factor=1.0, gamma=1.0, shared=False, zone=True, zone_style='solid', zone_color=None, zone_width=0.6, width_mm=0.0, title='Slice grid')`

One figure of the same slices through several maps: a column per
map (``names``; ``column_titles`` to name them, e.g. "LH", "LV"), a
row per value along ``axis`` (2 = energy) -- a polarisation or
temperature series. Each panel is titled "<column>, <value> <unit>";
colour, levels, gamma and the Brillouin zone as in
``slice_series``. Returns the figure in numbers.

#### `L.figure_from(*names, title='')`

A figure composer with these rows as panels (as "Plot as
figure"). Returns the figure in numbers.

#### `L.figures()`

The titles of the open figure windows: the names the other figure
operations take.

#### `L.figure_describe(title='')`

A figure in numbers: page size, each panel's frame (mm), title,
axis names, colour scale, text sizes. Check a layout with this, not
with a picture.

#### `L.figure_style(title='', **style)`

Set the figure's style: width_mm, height_mm, font_pt, gap_x_mm,
gap_y_mm, edge_labels_only, inner_tick_numbers, shared_levels,
equal_aspect, panel_label_position ... (FigureStyle). Returns the
figure in numbers.

#### `L.panel_set(title='', index=0, **attributes)`

Set panel ``index`` of a figure: colormap, flip, levels (lo, hi),
gamma, title, x_label, y_label, x_range, y_range, colorbar, span
(rows, cols), font_pt ... (figure Panel). Returns the figure in
numbers.

#### `L.panel_picture(title='', index=0, path='', span=None)`

Fill panel ``index`` with a picture file (a schematic, a 3D BZ
picture); it keeps its own shape. ``span`` (rows, cols) lets it take
several grid cells at the next arrange.

#### `L.figure_arrange(title='', rows=1, cols=1)`

Put the panels on a rows x cols grid (each taking its span), the
page height following. Returns the figure in numbers.

#### `L.figure_render(title='', path='', dpi=0)`

Write the figure as a PNG, as it will print (not a screenshot),
and return its numbers. Never overwrites ``path``.

#### `L.figure_export(title='', path='')`

Write the figure as PDF, SVG, PNG or TIFF (from the extension).
Never overwrites. Returns the files written.

#### `L.figure_save(title='', path='', with_data=True)`

Save the figure as an .afig file to open and edit again, with
(``with_data``) the data of each panel in "data for <name>" beside
it -- leave that out of anything shared. Never overwrites. The window
keeps its title, so the other figure operations still find it by
the same name.

### Tool windows

#### `L.tools()`

Every tool-panel button, by action name, with what it acts on --
for the tools that have no operation of their own here (MDC/EDC
fits, core levels, detector corrections, tight-binding fit,
calculated bands, 3-D views ...). Open one with ``run_tool``.

#### `L.run_tool(action, *names)`

Select ``names`` and open the tool ``action`` (see ``tools()``)
on them, on screen. Returns the title of the window it opened. Its
controls are then the window's own; prefer an operation here where
there is one.

#### `L.windows()`

The titles of the program's open windows (viewers, tools,
figures), for ``close`` and for knowing what is on screen.

#### `L.close(title)`

Close a window by (part of) its title; not the main window.

### Your own computation

#### `L.data(name)`

A row's data as plain arrays (``.kind``, ``.axes``, ``.labels``,
``.values``, ``.info``), for a computation the operations above do
not cover -- with the program's own functions (``functions()``)
where there is one. Say so when you compute something yourself.

#### `L.add(name, kind, axes, values, labels=None, info=None, made_from='', step='computed', parameters=None)`

Put a result of your own on the list as a new row: ``kind``
"cut", "map", "k_map", "kz_map", "kz_map_k", "edc", "mdc" ...;
``axes`` one array per dimension (array order); ``labels`` one per
axis. With ``made_from`` (a row) the new row carries its metadata
and a history step (``step``, ``parameters``) saying how it was
made. Returns the row's name.

#### `L.functions(module='')`

The program's own computations (Qt-free, under
``arpes_viewer.tools``) with their signatures and what each does:
all modules, or one (e.g. "spectra.peaks"). Use these on
``data(name).values`` rather than writing your own.

## 2. Tool windows: `L.run_tool(action, row)`

The tool panel's buttons, for what has no operation of its own above. The window opens on screen, on the rows given.

| action | button | takes | what it does |
|---|---|---|---|
| `fermi` | Fermi edge fit... | a cut or a map | Fit the Fermi edge: E_F and the resolution, then offset the energy axis to E - E_F. A cut opens with its viewer; a map with its slit cut, whose slider picks the cut to fit -- one E_F for the whole map, or one per cut, interpolated between them. |
| `fscorr` | Fermi surface correction... | a cut, or a map or kz map before its k conversion | Straighten a Fermi edge the analyser bends, step by step: first how its curve is found -- clicked on the data viewer where the Fermi edge is, or fitted channel by channel on a reference cut or map of the main list (gold; a reference fitted before is not fitted again) -- then a polynomial through it, and every angle column shifted to flatten it. A map is corrected whole, from its slit cut. |
| `degrid` | Remove detector grid... | a cut, or a map or kz map before its k conversion | Remove the detector's grid pattern. From a whole map (or kz map), using the map itself as the reference -- do this first, before a k conversion or Fermi-surface correction. From a cut, with a grid found on a map with the same settings if one is in the list, by notching the cut's own grid peaks otherwise. |
| `detcorr` | Detector corrections... | a cut, or a map or kz map before its k conversion | Before anything else, on the detector's own pixels: make a trapezoidal (keystone) image rectangular again, and patch dead or bad regions of the detector from their neighbours. A cut, or every slice of a map at once. |
| `background` | Background subtraction... | cuts | Remove the intensity that is not the bands: Shirley or Tougaard inelastic background, a floor common to every angle, a smooth polynomial -- or divide out the Fermi cut-off. |
| `kcut` | k conversion (cut)... | a cut in angle | Convert a cut to momentum. By default a vertical line on the cut picks Γ's slit angle (Γ taken to lie on the cut); Advanced inherits Γ from a converted map. Starts from the last conversion of a cut of the same size. |
| `corelevel` | Core-level check... | a cut | Which element and orbital each peak of the angle-integrated EDC is: the sample's elements against tabulated binding energies, after checking E_F and the photon energy; unexplained peaks get possible contaminants. |
| `kmap` | k conversion (map)... | an angle map (one in k or a kz map is not converted this way) | Convert an angle map to momentum (Å⁻¹). It opens on its constant-energy contour, where the readout cursor picks Γ; the settings start from the last conversion of a map of the same size. |
| `kzalign` | Align Fermi levels (kz)... | a photon-energy scan (kz map) before its k conversion | Fit the Fermi edge of every spectrum of a photon-energy scan, shift each one to put its own edge at zero, and crop to the energy range they all still cover. Before the kz conversion. |
| `kzconv` | kz conversion... | a photon-energy scan (kz map) not yet in momentum | Convert a photon-energy scan to (k_z, k_par), choosing the inner potential against the lattice's own period. Flatten the Fermi edge first. Starts from the last conversion of a scan of the same size. |
| `bz` | BZ overlap... | a map in momentum (a k-map, or a converted kz map) | Overlay a Brillouin zone (or a moire zone) on a map in momentum -- a k-map or a converted kz map. Once plotted, the zone stays with the dataset: its viewer shows it with the Brillouin zone tick box, and its exports can draw it. |
| `smooth` | Smooth... | cuts or maps | Gaussian, Savitzky-Golay or moving-average smoothing, with spike removal. A map is smoothed plane by plane, on the plane you pick. |
| `derivative` | Second derivative... | cuts or maps | -d²I/dE² or -d²I/dk² after a pre-smooth, to sharpen the bands. |
| `curvature` | Curvature... | cuts or maps | The 1D or 2D curvature (Zhang et al.), which follows the band better than a second derivative. |
| `gradient` | Minimum gradient... | cuts or maps | I/\|∇I\|: bands as the valleys of the intensity's gradient (He, Wang and Shen). First derivatives only, so less noise than a second derivative or the curvature; neither axis is favoured, and shoulders show. |
| `symmetry` | Symmetrise... | cuts or maps | Mirror a cut about a line; for a map, mirror or rotate its constant-energy planes. |
| `ridge` | Ridge detection... | cuts or maps | Trace the bands as ridges of the intensity: the Hessian of the smoothed image, kept where it curves down across the band and the slope across it changes sign. Sharper than a second derivative, with no false double lines; the ridge points can be listed or saved for a fit. A map is done plane by plane. |
| `stack` | Stack plot (EDC / MDC)... | a cut | A waterfall of EDCs or MDCs across the cut. |
| `mdcfit` | MDC fit (k-cut only)... | a cut in momentum (k) | Fit the momentum distribution curves line by line, then read the band off the fitted centres: Fermi velocity, effective mass, self-energy. Only for a cut converted to momentum (k). |
| `edcfit` | EDC fit... | a cut | Fit the energy distribution curves line by line, optionally with the Fermi cut-off in the model. Any cut; v_F and m* from the fitted band need a cut in momentum. |
| `arithmetic` | Cut arithmetic (two cuts)... | two cuts | Combine two cuts: linear or circular dichroism, dividing by a reference, A − B, A / B, (A − B)/(A + B), A + B. The first selected is A; the window can swap them. |
| `slicefig` | Slice series figure... | a map | A page of 2-D slices through the map as one figure for a paper: constant-energy contours at a series of energies, or cuts at a series of angles or momenta, with a shared colour scale and labels on the outer edges only. Flat panels, not a 3-D view (that is 3D slices). |
| `slices3d` | 3D slices... | a map | The three orthogonal planes through the cube drawn in 3-D, turned with the mouse, each placed where you choose and with its own colours. For flat panels on a page, see Slice series figure. |
| `notch3d` | Notched cube... | a map | The cube with one corner cut away: a constant-energy map and two dispersions in one picture. |
| `projection3d` | Volume projection... | a map | The whole volume projected along the view: maximum intensity, sum, alpha composite, or a shaded isosurface. |
| `stack3d` | Stacked slices... | a map | Parallel slices of the cube stacked in 3-D -- constant-energy maps one above another up the energy axis, or cuts one behind another along k_z -- each layer's background transparent, with a curve marked through the layers (a Dirac point followed). For figures of how a band evolves. |
| `pocket` | Fermi pocket (quasi-2D)... | a map converted to momentum (a k-map) | Under test. The contour of one Fermi pocket of a k-map, its area, and from it the carrier density, the carriers per cell, the quantum-oscillation frequency and the cyclotron mass. Only for quasi-two-dimensional samples (no k_z dispersion): for a three-dimensional Fermi surface these numbers mean nothing. |
| `figure` | Figure composer... | cuts or curves | A figure laid out like a manuscript page: one panel per selected dataset, or, with nothing selected, a blank page of empty panels to fill from the list or with pictures. |
| `lattice` | Crystal structure... |  | The crystal in real space, in 3-D: typed in (the space group first, then the cell it allows, then the atoms), or filled from a .cif file. Draw a cleavage plane (hkl) and slide it through the cell; atoms' colours, gloss, transparency and size are yours to set. The picture goes to the figure composer. |
| `bz3d` | 3D BZ... |  | The crystal's Brillouin zone in 3-D: the space group first, then the cell it allows (or a CIF file); as many planes as you like, each with its own (hkl), height and colour -- a selected k-map can lie on one -- and paths through the labelled points in colours of their own. The picture goes to the figure composer. |
| `tbfit` | Tight-binding fit... | a map in momentum (or nothing, to read points from a file) | Fit a tight-binding band E(k) = e0 + sum of hoppings x cos(k.R) to band points -- picked on a k-map, traced by ridge detection, or read from a file -- shell by shell of neighbours of a 2-D or 3-D lattice. Step by step; the model's contours go back onto the map and its band into the list. |
| `bands` | Calculated bands... | maps or cuts in momentum (or nothing, for the calculation alone) | A band structure from the theory side -- a .bxsf band grid (Wien2k, QE, VASP, Wannier90), a Wannier90 _hr.dat Hamiltonian, or bands along a path (_band.dat, .spaghetti_ene, VASP EIGENVAL) -- along a high-symmetry path over the measurement assembled from the selected k-maps, and over a cut or a map where it was really measured (its k_z). Fits the renormalisation Z and the shift; panels go to the figure composer. Select k-maps, kz maps in k and cuts in k. |

## 3. Without the program on screen: the MCP tools

`arpes-viewer-mcp` (route 1) offers these; the `viewer_*` ones need the program started with `--agent-bridge`, and `viewer_api` calls any operation of section 1.

- **`list_loaders`** -- The beamline readers this program has, with the file patterns each reads.
- **`find_files`** -- Data files in a folder that a reader recognises, with the datasets each holds (entry, kind).
- **`open_dataset`** -- Read one dataset (a cut, map, kz map, k-map, spatial scan, curve) with the program's loaders; returns its id and a description of its axes.
- **`list_datasets`** -- The datasets open in this session.
- **`describe`** -- Kind, axes (label, range, points, step) and key metadata of a dataset.
- **`metadata`** -- The dataset's metadata (photon energy, temperature, analyser settings, motors...), filtered by words.
- **`close_dataset`** -- Forget a dataset of this session.
- **`get_profile`** -- A curve -- an EDC or an MDC -- along one axis, averaged over ranges of the others; numbers back as text, optionally saved as CSV.
- **`get_image`** -- A 2-D picture of the data -- a cut, a constant-energy map, a dispersion through a map -- as PNG, the other axes averaged over ranges. Optionally saved as PNG / CSV.
- **`fit_fermi_edge`** -- Fit the Fermi edge (Fermi-Dirac x linear DOS, Gaussian resolution) of the EDC averaged over ranges of the other axes: E_F, resolution, their errors.
- **`shift_energy`** -- A copy of the dataset on E - E_F, E_F given on its own energy axis (e.g. from fit_fermi_edge).
- **`crop`** -- A copy cut to ranges of its axes.
- **`convert_cut_to_k`** -- Convert a cut from angle to momentum, as the k conversion (cut) tool: Γ's slit angle, the cut's deflector angle (and Γ's, if Γ is off the cut). The energy axis must be kinetic (or the cut shifted to E - E_F by this program); output_fermi_level_eV puts the result on E - E_F.
- **`convert_map_to_k`** -- Convert an angle map (deflector, slit, energy) to a k-map (kx, ky, E), as the k conversion (map) tool.
- **`save_datasets`** -- Save datasets: .nxs (this program's own -- the viewer opens it, several per file), .itx (Igor text) or .ibw (one Igor wave).
- **`brillouin_zone`** -- The Brillouin zone's high-symmetry points (Cartesian, Å⁻¹) and reciprocal vectors for a space group and cell; parameters the space group fixes are set by it.
- **`read_cif`** -- A CIF file's cell, space group and atom sites.
- **`viewer_status`** -- Whether the program is open with the agent bridge; its version, rows and open windows.
- **`viewer_rows`** -- The rows of the program's data list (name, kind, path, selected).
- **`viewer_add_files`** -- Add files to the program's list (as Quick add: reader detected).
- **`viewer_select`** -- Select rows of the list by name (part of it, or exact) or number.
- **`viewer_run_tool`** -- Press a tool-panel button (or list button / right-click entry) for the selected rows, e.g. open, fermi, kcut, kmap, bz, bz3d, figure, slices3d, notch3d, combine, lattice, tbfit, bands. The window opens on screen; look with viewer_screenshot.
- **`viewer_windows`** -- The program's open windows.
- **`viewer_screenshot`** -- A picture of one of the program's windows (the main window by default; else by part of its title).
- **`viewer_api_help`** -- The program's documented operations (L.<name>): all of them one line each, one group, or one in full. Read this before driving the program: it replaces reading the source.
- **`viewer_api`** -- Call one documented operation of the running program on the rows of its list, e.g. operation='fermi_edge', args={'name': 'cut1', 'energy_window': [-0.15, 0.1]}. Every operation that makes data adds a new row and returns its name.
- **`viewer_figure`** -- A figure window in numbers, without a picture: page size, each panel's frame (mm), title, axis names, colour scale and text sizes. Check a layout with this.
- **`viewer_render_figure`** -- Write a figure window as a PNG, as it will be printed (not a screenshot), and return it with its numbers (viewer_figure).
- **`viewer_close_window`** -- Close one of the program's windows (by part of its title).
- **`viewer_python`** -- Run Python inside the running program (globals: A = arpes_viewer.app, L = the documented operations, QtCore, QtWidgets, np, os, re, inspect, json); what it prints comes back. For anything the operations (viewer_api) do not cover; never to edit the program's internal tables -- ask the person first and name the missing operation.

## 4. The program's computations (`arpes_viewer.tools`)

Qt-free functions, for a computation of your own on `L.data(row).values` / `.axes`, or in a script (route 2). `L.functions("spectra.peaks")` prints a module's signatures and first lines; `help(function)` the whole description.

- **`spectra.corelevel`** -- A quick core-level check of a cut, as plain numpy/scipy with no Qt: which element and orbital each peak of the angle-integrated EDC comes from. `assign`, `candidates_near`, `check`, `common_elements`, `describe_candidates`, `detect_scale`, `element_lines`, `expected_fermi_level`, `find_peaks`, `info_number`, `integrated_edc`, `locate_fermi_edge`, `parse_elements`, `peak_at`, `photon_energy_of`, `reference_lines`, `suggest_shift`, `work_function_of`
- **`spectra.curves`** -- One-dimensional data: EDCs, MDCs, spin EDCs -- as tables, with no Qt. `channel_names`, `crop`, `curve_info`, `data_channels`, `is_sigma`, `looks_like_counts`, `normalise`, `rebin`, `shift_x`, `sigma_name`, `sigma_of`, `subtract_background`, `table`, `value_label`, `with_poisson_sigma`
- **`spectra.dispersion`** -- What comes out of a fitted band: the dispersion, the Fermi velocity, the effective mass, and the self-energy. `bare_band_from_anchors`, `bare_band_line`, `fermi_crossing`, `fit_dispersion`, `kramers_kronig`, `line_crossing`, `self_energy`, `suggest_bare_velocity`, `window_scan`
- **`spectra.fermi`** -- Fermi-edge fitting, as plain numpy/scipy with no Qt -- the same split as ``tools.momentum.kspace`` and ``tools.processing.analysis``. `broadened_fermi`, `channel_fit_error`, `divide_fermi`, `edge_candidates`, `edge_problems`, `fermi_edge_model`, `fermi_function`, `fit_channels`, `fit_fermi_edge`, `initial_guess`, `levels_along`, `measured_channels`, `plan_channel_fit`, `steepest_drop`
- **`spectra.peaks`** -- MDC and EDC peak fitting, with no Qt: a band model that carries its own identity and the energy range it exists over, hand-placed seeds interpolated into a star. `fit_line`, `fit_series`, `peak_profile`, `suggest_seed`
- **`spectra.pocket`** -- A Fermi pocket of a **quasi-two-dimensional** sample, from a k-map: its contour, its area, and what the area says. `cell_area`, `energy_plane`, `fit_ray`, `numbers`, `radial_profiles`, `series`, `trace`
- **`spectra.spin`** -- Spin polarisation from the channels of a spin-resolved EDC, with no Qt. `analyse`, `axes_available`, `channels_from_info`, `design_report`, `pairs`, `parse_channel`, `parse_channels`
- **`momentum.cutk`** -- Angle-to-momentum conversion for a single **Cut** -- one E-vs-angle spectrum taken at one deflector position -- as the companion to ``tools.momentum.kspace``'s . `convert_cut`, `cut_directions`, `cut_extent`, `cut_momenta`
- **`momentum.kspace`** -- Angle-to-momentum conversion for ARPES Maps (a deflector Map; k_z is not covered here, and the single-Cut case lives in ``tools.momentum.cutk``, which builds on. `angle_grid_to_directions`, `convert_map`, `convert_map_forward_reference`, `float16_holds`, `k0_of_energy`, `k_extent`, `origin_rotation`, `points_to_azimuth`, `result_dtype`, `rotation_matrix`, `storage_dtype`
- **`momentum.kzconv`** -- A photon-energy scan into momentum: (hv, angle, E) -> (k_z, k_par, E). `calibrated_photon_axis`, `default_grid`, `edge_flatness`, `forward`, `inner_potential_for_gamma`, `inverse`, `kz_bounds`, `measured_work_functions`, `photon_arc`, `scan_inner_potential`, `to_kz_cube`
- **`momentum.kzmap`** -- Putting a photon-energy scan onto one Fermi level. `align`, `fit_levels`, `normalise_totals`, `process_kz_map`, `region_edc`
- **`momentum.rebin`** -- Averaging for a conversion onto a grid coarser than the measurement. `bin_average`, `box_filter`, `box_kernel`, `is_reduction`
- **`processing.analysis`** -- Two analysis operations, as plain numpy/scipy functions with no Qt anywhere -- the same split as ``tools/momentum/kspace.py``, so both can be tested (and reused. `arbitrary_cut`, `fit_feature`, `fs_correction`, `line_samples`, `offset_per_channel`, `shift_bins`
- **`processing.combine`** -- Datasets measured in pieces, joined back into one. `interp_axis`, `join`, `plan`
- **`processing.cutops`** -- Arithmetic between two cuts: dichroism, asymmetries, and dividing by a reference. `axis_unit`, `combine`, `looks_like_counts`, `metadata_differences`, `polarisation_warnings`
- **`processing.dataops`** -- Three bulk operations, as plain numpy functions with no Qt: **truncate**, **self-normalisation** and **compress** (binning -- resampling is deliberately left ou. `axis_index`, `axis_summary`, `compress`, `normalise_presets`, `resolve_bounds`, `same_format`, `self_normalize`, `truncate`
- **`processing.degrid`** -- Removing the detector grid from ARPES images, with no Qt. `degrid_cut_notch`, `degrid_cut_with_grid`, `degrid_map`, `estimate_map_grid`, `find_regions`, `fit_to`, `grid_contrast`, `illuminated_box`, `model_from_pattern`, `not_pixel_locked`
- **`processing.detector`** -- Corrections made on the detector's own pixels, before anything else: a trapezoidal (keystone) image made rectangular again, and dead or bad regions patched from. `apply_to`, `detector_frames`, `find_bad_regions`, `keystone_correct`, `not_on_detector`, `patch_regions`
- **`processing.process`** -- The 2-D data operations, as plain numpy functions with no Qt: smoothing, derivatives, curvature, symmetrisation, background subtraction, normalisation and despi. `axis_step`, `box_smooth`, `curvature`, `derivative`, `despike`, `divide_fermi_edge`, `gaussian_smooth`, `gradient_enhance`, `gradient_modulus`, `history_of`, `is_smoothed`, `laplacian`, `minimum_gradient`, `normalise`, `normalise_unit`, `percentile_background`, `polynomial_background`, `record_step`, `savgol_smooth`, `shirley_background`, `subtract_background`, `suggest_a0`, `symmetrise`, `symmetry_operations`, `tags_of`, `tougaard_background`
- **`processing.repeats`** -- One measurement taken in several batches, added back together. `diagnose`, `energy_shift`, `flag_changed`, `grid_plan`, `sum_repeats`
- **`processing.ridge`** -- Bands traced as ridges of the intensity. `default_sigmas`, `ridge_cube`, `ridges`
- **`processing.stackcuts`** -- Several cuts stacked into one cube along an axis the user names. `axis_label`, `compatibility`, `kind_for_role`, `stack`, `stack_axis`, `truncated_frames`, `truncation_plan`
- **`processing.volume`** -- Three-dimensional display geometry, with no Qt and no OpenGL: orthogonal slices, the notched cube, a shaded isosurface and volume projections. `apply_plane_wise`, `auto_edges`, `axis_segments`, `edge_ends`, `filled_ranges`, `isosurface_depth`, `notched_box`, `outline_edges`, `project_volume`, `reduce_volume`, `sample_plane`, `slice_faces`, `sort_faces`, `stack_faces`, `symmetrise_volume`, `view_volume`, `visible`
- **`crystal.bandfiles`** -- Calculated band structures read from (and written to) the files the calculation codes leave behind. `companion_files`, `detect`, `formats_for`, `join_pieces`, `read`, `read_bxsf`, `read_eigenval`, `read_fplo_band`, `read_fplo_eigenvalue`, `read_fplo_grid`, `read_fplo_kpoints`, `read_hr`, `read_matlab_grid`, `read_poscar`, `read_procar`, `read_spaghetti`, `read_wannier_band`, `read_win_cell`, `split_groups`, `survey`, `write_bxsf`, `write_hr`
- **`crystal.bands`** -- Calculated band structures, and the arithmetic of comparing them with ARPES. `bands_along_cut`, `contour_lines`, `contours`, `fit_alignment`, `follow_band`, `kz_of`, `kz_on_sphere`, `named_path`, `node_line`, `parse_path`, `reciprocal_of`, `sample_path`, `spectral_function`
- **`crystal.bz2d`** -- The 2-D Wigner-Seitz cell of a plane lattice, and tiling copies of it across a field of view. `irreducible_cell_2d`, `lattice_point_group_2d`, `reciprocal_vectors_2d`, `tile_2d`, `wigner_seitz_cell_2d`
- **`crystal.bz3d`** -- The general 3-D Brillouin zone (the reciprocal lattice's Wigner-Seitz cell), an arbitrary-orientation planar cut through it, and tiling copies of it across a fi. `cut_points_3d`, `cuts_in_frame`, `face_planes`, `irreducible_wedge`, `kz_frame`, `kz_zone_cuts`, `plane_basis`, `plane_cut`, `tile_and_cut`, `wigner_seitz_cell`
- **`crystal.cleavage`** -- From a measured k_z period to which plane the crystal cleaved along. `candidates`, `reciprocal_lengths`
- **`crystal.compare`** -- Putting a calculation and a measurement on the same axes. `band_points`, `band_segments`, `experiment_along_path`, `in_plane_operations`, `symmetry_fold`
- **`crystal.fermisurface`** -- The 3-D Fermi surface (or any constant-energy surface) of a calculation that knows its bands everywhere -- a band grid or a Wannier Hamiltonian -- as triangles . `clip_to_zone`, `crossing_bands`, `fermi_surface`, `inside_zone`, `marching_tetrahedra`, `sampled`, `zone_distance`
- **`crystal.highsym`** -- The named high-symmetry points of the first Brillouin zone (Gamma, M, K, Z, L, ...), for the Brillouin-zone tool: labels in its 3-D view of the cut plane, label. `equivalent_points`, `high_symmetry_points`, `lattice_variant`, `plane_offsets`, `points_in_frame`, `points_on_plane`
- **`crystal.lattice`** -- Real-space and reciprocal-space lattice vectors from unit-cell parameters and (optionally) a space-group number, for the Brillouin-zone tool. `bravais_symbol`, `conventional_vectors`, `free_parameters`, `point_group_operations`, `primitive_vectors`, `reciprocal_vectors`, `validate_lattice_parameters`
- **`crystal.moire`** -- The moire Brillouin zone of two stacked 2-D lattices (independent lattice constants, independent orientations), for the Brillouin-zone tool's moire mode. `hex_moire_lattice_fast`, `moire_bz`, `moire_reciprocal_vectors`
- **`crystal.planecut`** -- A calculation cut by any plane of k-space, the way the Brillouin-zone tool cuts the zone: a surface normal given as Miller indices (hkl), an offset along it (st. `contours`, `named_points`, `plane_of`, `sample`, `spectral_map`, `through_points`, `to_model_frame`, `zone_outlines`
- **`crystal.structure`** -- A crystal in real space: the cell, the atoms in it, and planes through it. `atomic_layers`, `cartesian_atoms`, `coordination_polyhedra`, `covalent_radius`, `element_colour`, `element_of`, `expand`, `lattice_point_atoms`, `parse_cif`, `parse_symop`, `plane_normal`, `plane_outline`, `read_cif`, `space_group_number`
- **`crystal.tightbinding`** -- A one-band tight-binding model fitted to measured band points. `design_matrix`, `evaluate`, `fit`, `fit_azimuth`, `fit_two_band`, `integer_coordinates`, `lattice_2d`, `lattice_symmetry`, `read_points`, `rotate`, `shells`, `two_band_energies`
- **`output.explog`** -- The experiment log: one CSV row per measurement, written from the data files' own metadata instead of typed in by hand during the beamtime. `append`, `available_fields`, `axis_range`, `cell`, `default_header`, `default_template`, `load_settings`, `load_template`, `logged_names`, `number`, `plain`, `read_log`, `reformat`, `reformat_plan`, `resolve`, `row`, `save_settings`, `save_template`, `sniff_delimiter`, `template_from_header`
- **`output.figure`** -- The model behind the figure composer: what a publication figure *is*, laid out in millimetres, with no Qt in sight. `empty_data`, `parse_markup`, `picture_data`, `pt_to_mm`, `text_width_mm`
- **`output.igor`** -- Datasets written for Igor Pro: an Igor text file (``.itx``) holding any number of waves, or one Igor binary wave (``.ibw``, version 5) per dataset. `axis_specs`, `ibw_bytes`, `igor_name`, `itx_text`, `split_label`, `wave_from_dataset`, `write_datasets`, `write_ibw`, `write_itx`
