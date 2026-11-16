"""
tools/momentum/kzmap.py
=======================
Putting a photon-energy scan onto one Fermi level.

The problem
-----------
A kz map is a stack of spectra, one per photon energy, and they do not share
an energy axis in any way the files can tell you about. The monochromator's
nominal photon energy is off by an amount that drifts with hv, the analyser's
work function is known only from a calibration table, and the operator set
each spectrum's window from whatever the Fermi level looked like at the time.
The loader stacks them as measured and says so (``loader/beamlines/cassiopee.py``);
this module is the step that actually calibrates them.

The measurement contains the answer. Every spectrum has a Fermi edge in it,
and where that edge sits *is* the energy reference. So: fit the edge in each
spectrum, shift each one to put its own edge at zero, and the stack is
aligned -- by the data rather than by a table.

What this module does, in order
-------------------------------
1. :func:`fit_levels` -- one Fermi-edge fit per photon energy, over an EDC
   summed across a region the user picked once, on the same *index* range in
   every spectrum.
2. :func:`align` -- shift each spectrum by its own E_F and resample onto one
   common energy axis, cropped to the range every spectrum still covers.
3. :func:`normalise_totals` -- optionally divide each spectrum by its own
   total, which is what makes them comparable when the photon flux varies
   across the scan (it does, strongly).

Two other ways to the Fermi level of each spectrum, where fitting every
edge is not wanted or not possible (a weak edge, a dispersing band across
it):

* :func:`levels_from_points` -- E_F clicked by hand at a few photon
  energies on the scan-axis cut (photon energy against energy), and a
  polynomial through the points: one function over the whole scan by
  default, or one per segment (``breaks``) where the monochromator's
  calibration changes, at a grating change, say.
* :func:`levels_from_reference` -- the levels of another kz map aligned
  before (:data:`KZ_FIT_KEY`), interpolated onto this one's photon
  energies: a scan of gold, or of the same sample, taken with the same
  monochromator and analyser settings. Spectra outside the reference's
  photon-energy range are cut off.

:func:`align_to_levels` aligns, crops and normalises with levels from
either.

Nothing here imports Qt, so the whole calibration can be run from a script
over a directory of scans.
"""
from __future__ import annotations

import warnings

import numpy as np

from arpes_viewer.tools.spectra.fermi import fit_fermi_edge

__all__ = ["region_edc", "fit_levels", "align", "normalise_totals",
           "process_kz_map", "KzMapResult", "KZ_FIT_KEY", "segment_breaks",
           "levels_from_points", "levels_from_reference", "align_to_levels",
           "fit_record", "fit_of"]

#: Where a kz map's Fermi level against photon energy is kept, as JSON
#: (:func:`fit_record`): on the aligned row and on the row it was aligned
#: from, so either can be another kz map's reference.
KZ_FIT_KEY = "kzfit.json"


class KzMapResult:
    """What :func:`process_kz_map` produced, and how well it went.

    Kept as an object rather than a tuple because the diagnostics matter as
    much as the cube: a kz map whose edges were fitted badly looks perfectly
    convincing, and the only way to know is to look at E_F against photon
    energy and see whether it is a smooth curve or a scatter.
    """

    def __init__(self, cube, energy, ef, ok, fits, trimmed, normalised):
        #: The aligned (and optionally normalised) cube, (hv, angle, E).
        self.cube = cube
        #: The common energy axis, zero at the Fermi level.
        self.energy = energy
        #: Fitted E_F per photon energy, in the *original* energy units.
        self.ef = ef
        #: Which of those came from a fit that converged. Where it is False
        #: the value was interpolated from the neighbours that did.
        self.ok = ok
        #: The FermiFit for each spectrum, or None where the fit failed.
        self.fits = fits
        #: How much energy range the shifting cost, in eV.
        self.trimmed = trimmed
        #: Whether each spectrum was divided by its own total.
        self.normalised = normalised

    @property
    def spread(self) -> float:
        """How far apart the fitted Fermi levels were, in eV.

        This is the number the whole exercise is about: it is how wrong the
        nominal photon energies and the tabulated work function were, and it
        is also exactly what had to be trimmed off the cube.
        """
        finite = self.ef[np.isfinite(self.ef)]
        return float(finite.max() - finite.min()) if finite.size else 0.0

    def summary(self) -> str:
        failed = int((~self.ok).sum())
        lines = [
            f"{self.ok.size} spectra, {self.ok.sum()} fitted, "
            f"{failed} interpolated from their neighbours",
            f"Fermi level spread {self.spread:.4f} eV",
            f"energy range kept {self.energy[0]:.4f} to {self.energy[-1]:.4f} eV "
            f"({self.trimmed:.4f} eV trimmed by the shift)",
        ]
        if self.normalised:
            lines.append("each spectrum divided by its own total intensity")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# 1. Fitting
# --------------------------------------------------------------------------
def region_edc(cube, index_region):
    """The EDC of one spectrum, summed over the picked angle range.

    ``index_region`` is ``((angle_from, angle_to), (energy_from, energy_to))``
    with **inclusive** bounds, as the image views report a dragged box.
    """
    (a0, a1), _energy_range = index_region
    block = cube[a0:a1 + 1, :]
    with warnings.catch_warnings():
        # An all-NaN column is a dead detector channel, not an error.
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nansum(block, axis=0)


def _is_an_edge(fit, lo: float, hi: float, margin: float) -> bool:
    """Did this fit actually find a Fermi edge, or merely converge?

    The test is :func:`arpes_viewer.tools.spectra.fermi.edge_problems`
    (E_F pinned to the window, no significant step down, E_F undetermined).
    Worth catching rather than leaving to the eye: shifting a spectrum by a
    wrong level moves it out of the stack, which shows up as a dim band in
    the final map rather than as anything that says "this fit failed".
    """
    from arpes_viewer.tools.spectra.fermi import edge_problems
    return not edge_problems(fit, lo, hi, margin)


#: Public name for the check, for anything else that fits one edge and
#: must not take a converged fit for a found edge (the curve fit panel).
is_an_edge = _is_an_edge


def fit_levels(cube, energy, index_region, *, temperature: float = 30.0,
               fixed=("temperature",), progress=None):
    """Fit the Fermi edge of every spectrum in the stack.

    ``cube`` is ``(hv, angle, E)``. The same *index* region is used for all
    of them -- which is the point of picking it once: an index range is the
    same detector channels and the same analyser window in every spectrum,
    whereas an energy range would mean something different in each, since
    they are exactly the spectra whose energy scales do not yet agree.

    Each fit is seeded from the last one that worked. Neighbouring photon
    energies have nearly the same edge, so the previous answer is a far
    better starting point than a fresh guess, and it keeps the fit from
    wandering off on a spectrum where the edge is weak.

    Returns ``(ef, ok, fits)``. Where a fit failed, ``ef`` is filled in by
    interpolating the ones that worked and ``ok`` is False, rather than left
    as NaN -- one bad spectrum in the middle of a scan should not take the
    whole cube with it, and a flagged interpolated value is both usable and
    honest. If *nothing* converged there is nothing to interpolate from, and
    that raises.
    """
    cube = np.asarray(cube)
    energy = np.asarray(energy, dtype=float)
    (_angles, (e0, e1)) = index_region
    lo, hi = sorted((float(energy[e0]), float(energy[e1])))
    # One energy step of room at each end: a level that lands on the very
    # last sample of the window was not fitted, it was cornered there.
    margin = abs(float(energy[1] - energy[0])) if energy.size > 1 else 0.0

    count = cube.shape[0]
    ef = np.full(count, np.nan)
    ok = np.zeros(count, dtype=bool)
    fits = [None] * count
    seed = None

    for index in range(count):
        if progress is not None:
            progress(index, count)
        intensity = region_edc(cube[index], index_region)
        try:
            fit = fit_fermi_edge(energy, intensity, start=seed, fixed=fixed,
                                 temperature=temperature, window=(lo, hi))
        except Exception:                                   # noqa: BLE001
            continue
        if not fit.success or not np.isfinite(fit.values.get("ef", np.nan)):
            fits[index] = fit
            continue
        fits[index] = fit
        if not _is_an_edge(fit, lo, hi, margin):
            continue
        ef[index] = float(fit.values["ef"])
        ok[index] = True
        fits[index] = fit
        seed = dict(fit.values)

    if not ok.any():
        raise ValueError(
            "the Fermi edge could not be fitted in any of these spectra. "
            "Check that the picked box covers an edge -- it needs points "
            "clearly above and clearly below it -- and that the temperature "
            "is about right.")
    if not ok.all():
        ef = np.interp(np.arange(count), np.flatnonzero(ok), ef[ok])
    return ef, ok, fits


# --------------------------------------------------------------------------
# 2. Aligning
# --------------------------------------------------------------------------
def align(cube, energy, ef):
    """Shift every spectrum to put its own Fermi level at zero.

    Each spectrum moves by its own amount, so afterwards they no longer
    cover the same range: the one shifted furthest down has nothing at the
    top, and vice versa. The common axis is therefore the range *every*
    spectrum still reaches, which is the original width less the spread of
    the fitted Fermi levels. Keeping more than that would mean inventing
    data at the edges, and a cube with a ragged top is worse than a shorter
    one -- the missing corner is invisible in a slice and looks like an
    intensity drop.

    Returns ``(cube, energy, trimmed)`` with ``energy`` zero at E_F.
    """
    cube = np.asarray(cube, dtype=float)
    energy = np.asarray(energy, dtype=float)
    ef = np.asarray(ef, dtype=float)
    if cube.shape[0] != ef.size:
        raise ValueError(
            f"{ef.size} Fermi levels for {cube.shape[0]} spectra")
    if energy.size < 2:
        raise ValueError("an energy axis of one point cannot be shifted")

    ascending = energy[-1] >= energy[0]
    low = float(np.max(energy[0] - ef)) if ascending else float(np.min(energy[0] - ef))
    high = float(np.min(energy[-1] - ef)) if ascending else float(np.max(energy[-1] - ef))
    if (high - low) * (1.0 if ascending else -1.0) <= 0:
        raise ValueError(
            f"the fitted Fermi levels are spread over "
            f"{float(np.nanmax(ef) - np.nanmin(ef)):.3f} eV, which is wider "
            f"than the {abs(float(energy[-1] - energy[0])):.3f} eV the "
            f"spectra cover, so no energy range is left that all of them "
            f"reach. The fits are almost certainly wrong.")

    step = abs(float(energy[1] - energy[0]))
    points = max(2, int(abs(high - low) / step) + 1)
    axis = np.linspace(low, high, points)

    # The energy shift is the same for every detector channel of a given
    # spectrum, so the mapping from the new axis back onto the old samples is
    # computed once per spectrum and applied to all its channels at once.
    # Interpolating channel by channel with np.interp would be tens of
    # thousands of calls for a real scan; this is two fancy-index reads.
    sample = np.arange(energy.size, dtype=float)
    out = np.empty((cube.shape[0], cube.shape[1], points), dtype=float)
    for index in range(cube.shape[0]):
        wanted = axis + ef[index]
        if ascending:
            position = np.interp(wanted, energy, sample)
        else:
            position = np.interp(wanted, energy[::-1], sample[::-1])
        left = np.clip(np.floor(position).astype(int), 0, energy.size - 2)
        weight = position - left
        frame = cube[index]
        out[index] = (frame[:, left] * (1.0 - weight)
                      + frame[:, left + 1] * weight)

    trimmed = abs(float(energy[-1] - energy[0])) - abs(high - low)
    return out, axis, trimmed


# --------------------------------------------------------------------------
# 3. Normalising
# --------------------------------------------------------------------------
def normalise_totals(cube):
    """Divide each spectrum by its own total intensity.

    The photon flux at this kind of beamline varies by a large factor across
    a 40-120 eV scan, and so does the analyser transmission, so the raw
    counts in a kz map are mostly a picture of the beamline rather than of
    the sample. Dividing each spectrum by its own total removes that and
    leaves the *shape* of each spectrum, which is what a kz map is read for.

    It is done after aligning and cropping, deliberately: only then do all
    the spectra cover the same energy range, so their totals are sums over
    the same thing. Normalising first would divide each by a sum over a
    slightly different window and bias the result by exactly the
    misalignment being corrected.

    A spectrum that is entirely zero or NaN is left alone rather than
    turned into NaN by dividing by nothing.
    """
    cube = np.asarray(cube, dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        totals = np.nansum(cube, axis=(1, 2))
    scale = np.where(np.isfinite(totals) & (totals != 0.0), totals, 1.0)
    return cube / scale[:, None, None]


# --------------------------------------------------------------------------
# All three, in order
# --------------------------------------------------------------------------
def process_kz_map(cube, energy, index_region, *, temperature: float = 30.0,
                   fixed=("temperature",), normalise: bool = True,
                   progress=None) -> KzMapResult:
    """Fit, align, crop and (optionally) normalise a whole kz map.

    ``cube`` is ``(hv, angle, E)``; ``index_region`` is the box picked on the
    angle-vs-energy view, as inclusive index bounds.
    """
    cube = np.asarray(cube, dtype=float)
    ef, ok, fits = fit_levels(cube, energy, index_region,
                              temperature=temperature, fixed=fixed,
                              progress=progress)
    aligned, axis, trimmed = align(cube, energy, ef)
    if normalise:
        aligned = normalise_totals(aligned)
    return KzMapResult(aligned, axis, ef, ok, fits, trimmed, bool(normalise))


# --------------------------------------------------------------------------
# E_F by hand: points on the scan-axis cut
# --------------------------------------------------------------------------
def segment_breaks(hv_points, segments: int) -> list:
    """Photon energies that split the points into ``segments`` runs of
    about equal size: midway between neighbouring points."""
    xs = np.sort(np.asarray(hv_points, dtype=float).reshape(-1))
    segments = int(segments)
    if segments <= 1 or xs.size < 2:
        return []
    out = []
    for k in range(1, segments):
        i = int(round(k * xs.size / segments))
        i = min(max(i, 1), xs.size - 1)
        out.append(0.5 * (xs[i - 1] + xs[i]))
    return sorted(set(out))


def levels_from_points(points, hv, order: int = 1, breaks=()) -> tuple:
    """E_F at every photon energy of ``hv`` from points clicked on the
    scan-axis cut, ``[(hv, E_F), ...]``.

    One polynomial of ``order`` through all of them -- the single function
    that is the default -- or, with ``breaks`` (photon energies), one per
    segment between them, each fitted to its own points (at least
    ``order + 1``). Returns ``(ef, pieces)``, ``pieces`` being
    ``[(lo, hi, coefficients)]``, highest power first.
    """
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    hv = np.asarray(hv, dtype=float)
    order = int(order)
    if order < 0:
        raise ValueError("the polynomial order is 0 or more")
    edges = [-np.inf] + sorted(float(b) for b in (breaks or ())) + [np.inf]
    ef = np.full(hv.shape, np.nan)
    pieces = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        inside = (pts[:, 0] >= lo) & (pts[:, 0] < hi)
        if inside.sum() < order + 1:
            where = "the scan" if len(edges) == 2 else (
                f"the segment {lo:.6g} to {hi:.6g} eV")
            raise ValueError(
                f"an order-{order} fit needs at least {order + 1} points in "
                f"{where}; it has {int(inside.sum())}")
        x, y = pts[inside, 0], pts[inside, 1]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            coefficients = np.polyfit(x, y, order) if order > 0 \
                else np.array([float(np.mean(y))])
        here = (hv >= lo) & (hv < hi)
        ef[here] = np.polyval(coefficients, hv[here])
        pieces.append((float(lo), float(hi), [float(c) for c in coefficients]))
    return ef, pieces


# --------------------------------------------------------------------------
# E_F from a reference kz map
# --------------------------------------------------------------------------
def fit_record(hv, ef, ok=None, method: str = "", source: str = "",
               **extra) -> str:
    """The JSON kept under :data:`KZ_FIT_KEY`."""
    import json
    hv = np.asarray(hv, dtype=float).reshape(-1)
    ef = np.asarray(ef, dtype=float).reshape(-1)
    ok = np.ones(hv.size, bool) if ok is None else np.asarray(ok, bool).reshape(-1)
    state = {"hv": hv.tolist(), "ef": ef.tolist(), "ok": ok.tolist(),
             "method": str(method), "source": str(source)}
    state.update(extra)
    return json.dumps(state)


def fit_of(info) -> dict:
    """The kz Fermi-level fit recorded in ``info`` (a dataset's info or a
    row's properties), ``{}`` when there is none."""
    import json
    text = (info or {}).get(KZ_FIT_KEY)
    if not text:
        return {}
    try:
        state = json.loads(str(text))
    except ValueError:
        return {}
    if not isinstance(state, dict) or len(state.get("hv", ())) < 2 \
            or len(state.get("hv", ())) != len(state.get("ef", ())):
        return {}
    return state


def levels_from_reference(hv, ref_hv, ref_ef) -> tuple:
    """The reference's E_F interpolated onto ``hv``: ``(ef, inside)``,
    ``inside`` False for the photon energies outside the reference's
    range (NaN there; those spectra are cut off).

    The two energy axes must be on the same scale -- both as the loader
    put them, or both on the same kinetic axis -- since the reference's
    levels are read on its own axis."""
    hv = np.asarray(hv, dtype=float)
    ref_hv = np.asarray(ref_hv, dtype=float).reshape(-1)
    ref_ef = np.asarray(ref_ef, dtype=float).reshape(-1)
    good = np.isfinite(ref_hv) & np.isfinite(ref_ef)
    ref_hv, ref_ef = ref_hv[good], ref_ef[good]
    if ref_hv.size < 2:
        raise ValueError("the reference has fewer than two Fermi levels")
    order = np.argsort(ref_hv)
    ref_hv, ref_ef = ref_hv[order], ref_ef[order]
    step = float(np.median(np.diff(ref_hv))) if ref_hv.size > 1 else 0.0
    slack = 1e-6 * max(1.0, abs(step))
    inside = (hv >= ref_hv[0] - slack) & (hv <= ref_hv[-1] + slack)
    ef = np.full(hv.shape, np.nan)
    ef[inside] = np.interp(hv[inside], ref_hv, ref_ef)
    if inside.sum() < 1:
        raise ValueError(
            f"none of this scan's photon energies ({hv.min():.6g} to "
            f"{hv.max():.6g} eV) lies in the reference's range "
            f"({ref_hv[0]:.6g} to {ref_hv[-1]:.6g} eV)")
    return ef, inside


def align_to_levels(cube, energy, ef, *, normalise: bool = True,
                    keep=None) -> KzMapResult:
    """Align, crop and (optionally) normalise with Fermi levels found
    another way than fitting each edge (:func:`levels_from_points`,
    :func:`levels_from_reference`). ``keep`` drops the spectra marked False
    (outside a reference's range) first; the result's ``kept`` says which
    remain."""
    cube = np.asarray(cube, dtype=float)
    ef = np.asarray(ef, dtype=float)
    keep = np.isfinite(ef) if keep is None else (np.asarray(keep, bool) & np.isfinite(ef))
    if keep.sum() < 1:
        raise ValueError("no spectrum has a Fermi level to align it on")
    aligned, axis, trimmed = align(cube[keep], energy, ef[keep])
    if normalise:
        aligned = normalise_totals(aligned)
    result = KzMapResult(aligned, axis, ef[keep], np.ones(int(keep.sum()), bool),
                         [None] * int(keep.sum()), trimmed, bool(normalise))
    result.kept = keep
    return result
