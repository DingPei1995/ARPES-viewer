# Analysis: technical reference

What each analysis does and what it assumes. The computations are in this folder, Qt-free: `momentum/`, `spectra/`, `processing/`, `crystal/`, `output/`, each with its own reference where there is one: [momentum](momentum/README.md) · [spectra](spectra/README.md) · [processing](processing/README.md) · [output](output/README.md).

## Analysis

- **k conversion** (cube and single cut) -- the free-electron formula, with
  the inputs shown and checkable. Refused, with a reason, for an axis that is
  not an emission angle. **Set rotation from contour** reads the sample
  rotation off a direction picked on the contour: two points mark a line, so
  the order you click them in and which side of the origin they sit on make
  no difference, and what comes back is the smaller of the two turns that
  stand it vertical. A converted Map is stored in float16 by default (half
  the memory and file size; its 0.05 % steps are far below any point's
  counting noise), with float32 one click away. Values outside float16's
  range are kept in float32 automatically, and every slice is widened to
  float32 before it is summed, cut or fitted.
- **Fermi level** -- fit the edge, offset the energy axis, or divide it out.
- **MDC / EDC fitting** -- fit the peaks across a cut and read the band off
  them: `v_F`, `m*`, and the self-energy. Only accepts a cut whose in-plane
  axis is already in Å⁻¹, because every quantity built on the fitted band
  would otherwise carry meaningless units.
- **Core-level check** -- which element and orbital each peak of a cut's
  angle-integrated EDC is; see below.
- **Arbitrary cuts** -- any straight line through a contour.
- **Fermi-surface correction**, **stack plots**.
- **Cut arithmetic** -- linear and circular dichroism, dividing by a
  reference, differences, ratios and sums between two cuts; see below.
- **Processing** (2-D and over a cube) -- smoothing, derivatives, curvature,
  backgrounds, symmetrisation, despiking.
- **Crop / bin / normalise** -- truncate, self-normalise, compress, on
  several datasets at once when they really are the same format.
- **Combining datasets** -- *Stack* cuts into a map along a new axis (a
  photon-energy series of angle cuts becomes a kz map; cuts that share one
  axis are stacked on the range they all cover), *Join* cuts, maps, kz maps
  or k-maps of one kind end to end along one of their own axes
  (`tools/processing/combine.py`), or *Sum repeated scans*. Pieces on one
  grid are copied as measured; a different step or offset is interpolated
  onto the first piece's step; overlaps are averaged (or the earlier / later
  piece kept); gaps are left at zero and reported.
- **Sum repeated scans** -- checks before it adds: that the scans are
  repeats (grid and recorded conditions), whether the sample changed (each
  scan against the sum of the others, χ²/point from counting statistics,
  count rate, EDC energy shift by cross-correlation), then sum or mean with
  the changed scans left out and the shifts undone if asked.
- **BZ overlap** -- a conventional, irreducible or moiré zone on a
  converted contour. Space group first, then the lattice parameters it
  constrains; a 3-D preview shows the cut plane and the high-symmetry
  points (Γ, M, K, Z, L, ...), and **Through point** offers the offsets that
  put the cut through one of them. Starts from the last crystal used
  (`~/.arpes_viewer/brillouin_zone.json`).
- **3D BZ** (Figure tab) -- the zone in 3-D with k axes, any number of
  planes (hkl) each able to carry a k-map's constant-energy map, and
  several coloured high-symmetry paths; to the figure composer.
- **kz map processing** and **kz -> momentum** -- see below.
- **The curve viewer**, its **curve fit** and **spin analysis** -- see below.
- **De-grid** -- remove the detector's grid (MCP pattern or mesh) from a map
  or a cut; see below.
- **Detector corrections** -- on the detector's own pixels: a keystone
  stretched to a rectangle by an exact inverse map that keeps each line's
  counts, and bad regions patched (linear, or a harmonic fill factorised
  once for a whole map); *Find bad pixels* locates them.
- **Ridge detection** -- bands as ridges of the smoothed intensity, placed to
  a fraction of a pixel by Gaussian-derivative filters, with smoothing set
  per axis in its own unit so eV or meV gives the same answer (within
  0.2 meV on a synthetic band). The ridge image to the list, the points to
  a CSV.
- **Tight-binding fit** (Figure tab) -- **one band**: E(k) = e0 + Σ t_n Σ
  cos(k·R) on any 2-D or 3-D lattice (space group first), one hopping per
  symmetry orbit of neighbours (the space group's point group, or the
  lattice's own symmetry), fitted to band points from ridge detection,
  clicks or a file. A linear least-squares fit
  with standard errors and Tukey reweighting; a condition-number check says
  when the points cannot tell the shells apart. Contours over the data, the
  spectral function to the list.
- **Crystal structure** (Figure tab) -- the crystal in 3-D from a CIF or
  typed in (space group first, then the free parameters, then the basis).
  Per-element colour and size, bonds, and a cleavage plane (hkl) put on any
  atomic layer to show the termination. Drawn with QPainter, so it renders
  at any size; to the figure composer.
- **Calculated bands** (Figure tab) -- Wannier90 `_hr.dat` and the other
  formats in the guide, with orbital weights: bands along a path,
  constant-energy contours, and a fitted renormalisation Z and shift
  against a measured cut. Bands followed through crossings by eigenvector
  overlap.
- **Stacked slices** -- constant-energy or constant-k_z slices of a volume
  as faded layers in 3-D, with curves marked through them.

Windows that take several decisions lead through them as numbered steps
(Back / Next, with Next greyed and the reason shown until the step is
complete; `ui/common/stepper.py`).
