"""
tools/momentum/kzconv.py
========================
A photon-energy scan into momentum: (hv, angle, E) -> (k_z, k_par, E).

The physics
-----------
Inside the crystal the photoemission final state is taken to be free-electron
like, with an effective mass ``m*`` and its band bottom an inner potential
``V0`` below the vacuum level. The in-plane momentum is conserved across the
surface, the perpendicular one is not, and what is left is

    k_par = sqrt(A E_kin) sin(alpha)
    k_z   = sqrt(A m* (E_kin + V0) - k_par^2)          A = 2 m_e e / hbar^2

with ``A = 0.262466`` when k is in inverse angstroms and energies in eV.
Sweeping the photon energy sweeps ``E_kin`` and so sweeps ``k_z``, which is
the whole point of the measurement. ``V0`` is not measured by the experiment
and has to be chosen -- :func:`scan_inner_potential` is the aid for that.

Why this is inverted rather than projected
------------------------------------------
The obvious implementation walks the measured grid forwards, computes where
each sample lands in ``(k_z, k_par)``, and interpolates that scattered cloud
onto a regular grid. On a real cube (41 photon energies, 664 angles, 629
energies) that costs about 200 s, and the usual shortcut -- triangulate one
energy slice and reuse it with a rigid shift in ``k_z`` -- leaves the
``k_par`` axis wrong for every slice but the first.

None of that is necessary, because the map inverts in closed form. Given a
target ``(k_z, k_par)`` and a binding energy, there is exactly one photon
energy and one emission angle that produced it:

    E_kin = [k_z^2 + k_par^2 cos^2(theta_p) - A m* V0] / [A (m* - sin^2(theta_p))]
    hv    = E_kin + W - E
    sin(alpha) = k_par / sqrt(A E_kin)

So the conversion is a resampling of the original regular grid: one
``map_coordinates`` call per energy slice. It is exact for every slice, about
120x faster than the scattered route, needs no triangulation, and points the
measurement never reached come back as NaN by construction rather than as
whatever the nearest triangle happened to hold.

Angles and geometry
-------------------
``alpha`` is the analyser's slit angle; ``angle_offset`` is where normal
emission sits on it. ``theta_position`` is the manipulator's polar angle,
which tilts the whole detector arc out of the plane containing the slit. It
contributes a second in-plane component

    k_x = sqrt(A E_kin) sin(theta_p) cos(alpha)

which must be subtracted inside the square root along with ``k_par``.
Leaving it out of ``k_z`` would be, at a manipulator angle of 20 degrees, a
0.26 A^-1 error -- a quarter of a zone for c = 6 A.

Nothing here imports Qt.
"""
from __future__ import annotations

import warnings

import numpy as np

__all__ = ["A_CONST", "forward", "inverse", "kz_bounds", "to_kz_cube",
           "photon_arc", "scan_inner_potential", "PeriodScan",
           "edge_flatness", "calibrated_photon_axis", "measured_work_functions",
           "default_grid", "inner_potential_for_gamma"]

#: ``2 m_e e / hbar^2`` with k in A^-1 and energies in eV, so that
#: ``k = sqrt(A_CONST * E) * sin(theta)``. ``sqrt(A_CONST) = 0.512315``, the
#: familiar 0.5123 prefactor.
A_CONST = 2 * 9.1093837015e-31 * 1.602176634e-19 / (1.054571817e-34 ** 2) * 1e-20


# --------------------------------------------------------------------------
# The map, both ways
# --------------------------------------------------------------------------
def forward(kinetic_energy, alpha, *, inner_potential: float,
            effective_mass: float = 1.0, theta_position: float = 0.0):
    """``(E_kin, alpha)`` -> ``(k_par, k_z)``, both in A^-1.

    ``alpha`` and ``theta_position`` are in radians, and ``alpha`` is the
    emission angle -- the slit angle with its offset already taken off.

    Returns ``(k_par, k_z)``; ``k_z`` is NaN wherever the in-plane momentum
    exceeds what the final state can hold, which is a real region of any wide
    scan and not an error.
    """
    kinetic_energy = np.asarray(kinetic_energy, dtype=float)
    alpha = np.asarray(alpha, dtype=float)
    radius = np.sqrt(np.clip(A_CONST * kinetic_energy, 0.0, None))
    k_par = radius * np.sin(alpha)
    k_out = radius * np.sin(theta_position) * np.cos(alpha)
    inside = (A_CONST * effective_mass * (kinetic_energy + inner_potential)
              - k_par ** 2 - k_out ** 2)
    with np.errstate(invalid="ignore"):
        k_z = np.sqrt(np.where(inside > 0, inside, np.nan))
    return k_par, k_z


def inverse(k_z, k_par, *, inner_potential: float,
            effective_mass: float = 1.0, theta_position: float = 0.0):
    """``(k_z, k_par)`` -> ``(E_kin, alpha)``. The exact inverse of
    :func:`forward`, in closed form.

    ``alpha`` is NaN where no emission angle could have produced that pair,
    which is the curved boundary of the measured region.
    """
    denominator = A_CONST * (effective_mass - np.sin(theta_position) ** 2)
    if abs(denominator) < 1e-12:
        raise ValueError(
            f"an effective mass of {effective_mass:g} cannot be used at a "
            f"manipulator angle of {np.degrees(theta_position):g} degrees: "
            f"the two cancel and the conversion has no unique solution")
    k_z = np.asarray(k_z, dtype=float)
    k_par = np.asarray(k_par, dtype=float)
    kinetic_energy = ((k_z ** 2 + k_par ** 2 * np.cos(theta_position) ** 2
                       - A_CONST * effective_mass * inner_potential)
                      / denominator)
    with np.errstate(invalid="ignore", divide="ignore"):
        sine = k_par / np.sqrt(np.where(kinetic_energy > 0,
                                        A_CONST * kinetic_energy, np.nan))
        alpha = np.arcsin(np.where(np.abs(sine) <= 1.0, sine, np.nan))
    return kinetic_energy, alpha


def kz_bounds(photon_energy, angle, energy, *, inner_potential: float,
              work_function: float, effective_mass: float = 1.0,
              angle_offset: float = 0.0, theta_position: float = 0.0):
    """The rectangle in ``(k_z, k_par)`` that this measurement covers.

    Evaluated at the two ends of the energy window only: ``k`` grows
    monotonically with kinetic energy, so the extremes are there.
    """
    photon_energy = np.asarray(photon_energy, dtype=float)
    alpha = np.radians(np.asarray(angle, dtype=float)) - angle_offset
    energy = np.asarray(energy, dtype=float)

    kz_lo = kz_hi = par_lo = par_hi = None
    for binding in (float(energy.min()), float(energy.max())):
        kinetic = photon_energy - work_function + binding
        grid_e, grid_a = np.meshgrid(kinetic, alpha, indexing="ij")
        k_par, k_z = forward(grid_e, grid_a, inner_potential=inner_potential,
                             effective_mass=effective_mass,
                             theta_position=theta_position)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            values = (np.nanmin(k_z), np.nanmax(k_z),
                      np.nanmin(k_par), np.nanmax(k_par))
        if kz_lo is None:
            kz_lo, kz_hi, par_lo, par_hi = values
        else:
            kz_lo = min(kz_lo, values[0]); kz_hi = max(kz_hi, values[1])
            par_lo = min(par_lo, values[2]); par_hi = max(par_hi, values[3])
    if not np.isfinite([kz_lo, kz_hi, par_lo, par_hi]).all():
        raise ValueError(
            "no part of this scan has a real k_z. The inner potential is "
            "probably far too small for these photon energies.")
    return (float(kz_lo), float(kz_hi)), (float(par_lo), float(par_hi))


# --------------------------------------------------------------------------
# Converting
# --------------------------------------------------------------------------
def _fractional_index(axis, wanted):
    """Where ``wanted`` falls on ``axis``, in (fractional) index units.

    A regular axis by a division; an irregular one -- the photon energies
    after a per-hv calibration, which moves each by its own amount -- by
    interpolation, NaN outside it. ``axis`` must be monotonic."""
    axis = np.asarray(axis, dtype=float)
    steps = np.diff(axis)
    if np.allclose(steps, steps[0], rtol=1e-6, atol=1e-9):
        return (wanted - axis[0]) / steps[0]
    index = np.arange(axis.size, dtype=float)
    if steps[0] < 0:
        axis, index = axis[::-1], index[::-1]
    return np.interp(wanted, axis, index, left=np.nan, right=np.nan)


def calibrated_photon_axis(photon_energy, work_function):
    """``(axis, work_function)`` to hand the conversion.

    A single work function is the usual case and passes through unchanged.
    One per photon energy -- the calibration, ``hv - E_kin(E_F)`` measured
    at each -- is folded into the photon-energy axis instead: the conversion
    only ever needs ``hv - W``, the kinetic energy of the Fermi level, so
    with ``axis = hv - W(hv)`` and a work function of zero every formula
    stays as it is. The folded axis has to stay monotonic, which a
    calibration that moves neighbouring photon energies past each other
    would break; that is refused.
    """
    photon_energy = np.asarray(photon_energy, dtype=float)
    if np.ndim(work_function) == 0:
        return photon_energy, float(work_function)
    phi = np.asarray(work_function, dtype=float)
    if phi.shape != photon_energy.shape:
        raise ValueError(f"{phi.size} work functions for "
                         f"{photon_energy.size} photon energies")
    if not np.isfinite(phi).all():
        raise ValueError("the calibration has photon energies without a "
                         "fitted Fermi level")
    axis = photon_energy - phi
    steps = np.diff(axis)
    if not (np.all(steps > 0) or np.all(steps < 0)):
        raise ValueError("the calibrated photon energies are not in order: "
                         "the per-hv Fermi levels move by more than the hv "
                         "step. Check the Fermi fits.")
    return axis, 0.0


def measured_work_functions(info) -> "np.ndarray | None":
    """``hv - E_kin(E_F)`` at each photon energy of a kz map, or None.

    Needs the Fermi level fitted per photon energy (the kz map's "align"
    step, ``kz.fermi_level_eV``) and each member's own kinetic-energy axis
    (recorded by the CASSIOPEE loader). The fitted level is on the cube's
    first energy axis, which was member one's kinetic axis referred by its
    own photon energy and tabulated work function; undoing that reference
    gives each member's measured kinetic energy of E_F.

    This is the number a photon-energy calibration needs: when the
    monochromator's hv is off, or the analyser's work function differs from
    the table, ``hv - E_kin(E_F)`` is not the tabulated work function and
    differs from one photon energy to the next.
    """
    info = info or {}
    try:
        ef = np.asarray(info["kz.fermi_level_eV"], dtype=float)
        hv = np.asarray(info["cassiopee.member_photon_energy_eV"], dtype=float)
        phi = np.asarray(info["cassiopee.member_work_function_eV"], dtype=float)
        start = np.asarray(info["cassiopee.member_kinetic_start_eV"], dtype=float)
    except (KeyError, TypeError, ValueError):
        return None
    if not (ef.shape == hv.shape == phi.shape == start.shape) or hv.size < 2:
        return None
    first_binding = start[0] - hv[0] + phi[0]
    kinetic_of_ef = start + (ef - first_binding)
    return hv - kinetic_of_ef


def default_grid(photon_energy, angle, energy, *, inner_potential: float,
                 work_function, effective_mass: float = 1.0,
                 angle_offset: float = 0.0, theta_position: float = 0.0,
                 limit: int = 2048):
    """``(n_kz, n_kpar)`` that keep the measurement's own detail.

    ``k_par`` gets as many points as the analyser has angle channels -- the
    finest thing measured -- and ``k_z`` the number that makes its step the
    same, so a pixel is square in momentum and nothing measured along the
    slit is averaged away. Each is held between 16 and ``limit``.
    """
    axis, phi = calibrated_photon_axis(photon_energy, work_function)
    (kz_lo, kz_hi), (par_lo, par_hi) = kz_bounds(
        axis, angle, energy, inner_potential=inner_potential,
        work_function=phi, effective_mass=effective_mass,
        angle_offset=np.radians(angle_offset),
        theta_position=np.radians(theta_position))
    n_kpar = int(np.clip(np.asarray(angle).size, 16, limit))
    step = (par_hi - par_lo) / max(n_kpar - 1, 1)
    n_kz = int(np.clip(round((kz_hi - kz_lo) / step) + 1 if step > 0 else 16,
                       16, limit))
    return n_kz, n_kpar


def inner_potential_for_gamma(photon_energy: float, period: float, *,
                              work_function: float, effective_mass: float = 1.0,
                              binding_energy: float = 0.0, order: int = None,
                              near: float = 12.0):
    """The inner potential that puts Γ at normal emission at ``photon_energy``.

    At normal emission ``k_par = 0`` and ``k_z^2 = A m* (E_kin + V0)``; Γ
    points sit at ``k_z = n * period``. So ``V0 = (n period)^2 / (A m*) -
    E_kin``. Which ``n`` is not known from one photon energy; given
    ``order`` it is that one, otherwise the ``n`` whose V0 is nearest
    ``near`` (eV). Returns ``(V0, n)``; V0 may come out negative, which is
    unusual for a free-electron final state and worth a second look.
    """
    kinetic = float(photon_energy) - float(work_function) + float(binding_energy)
    scale = A_CONST * float(effective_mass)
    if order is None:
        k = np.sqrt(max(scale * (kinetic + near), 0.0))
        order = max(1, int(round(k / float(period))))
        candidates = [n for n in (order - 1, order, order + 1) if n >= 1]
        order = min(candidates, key=lambda n: abs(
            (n * period) ** 2 / scale - kinetic - near))
    v0 = (int(order) * float(period)) ** 2 / scale - kinetic
    return float(v0), int(order)


def _sample_plane(cube_slice, photon_energy, alpha_axis, hv_wanted,
                  alpha_wanted):
    """Bilinear sample of one ``(hv, angle)`` plane at the asked positions.

    ``cube_slice`` is indexed ``[hv, angle]`` on its own regular axes, so the
    lookup is a coordinate transform and a ``map_coordinates`` call rather
    than any kind of scattered interpolation.
    """
    from scipy.ndimage import map_coordinates

    n_hv, n_alpha = cube_slice.shape
    hv_index = _fractional_index(photon_energy, hv_wanted)
    alpha_index = (alpha_wanted - alpha_axis[0]) / (alpha_axis[1] - alpha_axis[0])

    outside = (~np.isfinite(hv_index) | ~np.isfinite(alpha_index)
               | (hv_index < 0) | (hv_index > n_hv - 1)
               | (alpha_index < 0) | (alpha_index > n_alpha - 1))
    safe_hv = np.where(outside, 0.0, hv_index)
    safe_alpha = np.where(outside, 0.0, alpha_index)
    out = map_coordinates(cube_slice, [safe_hv, safe_alpha], order=1,
                          mode="nearest", output=float)
    out[outside] = np.nan
    return out


def to_kz_cube(photon_energy, angle, energy, cube, *, inner_potential: float,
               work_function, effective_mass: float = 1.0,
               angle_offset: float = 0.0, theta_position: float = 0.0,
               n_kz: int = 256, n_kpar: int = 256, kz_range=None,
               kpar_range=None, progress=None):
    """Convert a whole photon-energy scan into ``(k_z, k_par, E)``.

    ``photon_energy`` in eV, ``angle`` in degrees, ``energy`` the binding
    energy (zero at the Fermi level, which is what makes ``work_function`` a
    single number rather than one per spectrum). ``cube`` is
    ``(hv, angle, E)``. ``angle_offset`` and ``theta_position`` are in
    degrees. ``work_function`` is one number, or one per photon energy for
    a calibrated scan (:func:`calibrated_photon_axis`).

    ``k_z`` comes first in the output because it is the axis the measurement
    is *about*, and the viewers put the first axis across the image.

    NaN in, NaN out: the Fermi-surface correction pads the ends of its energy
    axis, and those pads must stay holes rather than being smeared into the
    result. Bilinear sampling propagates them, which is the behaviour wanted.
    """
    photon_energy = np.asarray(photon_energy, dtype=float)
    angle = np.asarray(angle, dtype=float)
    energy = np.asarray(energy, dtype=float)
    # Promoted to float64 a plane at a time below, not as a whole-cube copy.
    cube = np.asarray(cube)
    if cube.shape != (photon_energy.size, angle.size, energy.size):
        raise ValueError(
            f"cube is {cube.shape} but the axes say "
            f"({photon_energy.size}, {angle.size}, {energy.size})")
    if photon_energy.size < 2 or angle.size < 2:
        raise ValueError("the conversion needs at least two photon energies "
                         "and two angles to interpolate between")

    photon_energy, work_function = calibrated_photon_axis(photon_energy,
                                                          work_function)
    offset = np.radians(angle_offset)
    theta_p = np.radians(theta_position)
    alpha_axis = np.radians(angle) - offset

    if kz_range is None or kpar_range is None:
        found_kz, found_par = kz_bounds(
            photon_energy, angle, energy, inner_potential=inner_potential,
            work_function=work_function, effective_mass=effective_mass,
            angle_offset=offset, theta_position=theta_p)
        kz_range = kz_range or found_kz
        kpar_range = kpar_range or found_par

    kz_axis = np.linspace(float(kz_range[0]), float(kz_range[1]), int(n_kz))
    kpar_axis = np.linspace(float(kpar_range[0]), float(kpar_range[1]),
                            int(n_kpar))
    grid_kz, grid_par = np.meshgrid(kz_axis, kpar_axis, indexing="ij")

    # The (k_z, k_par) -> (E_kin, alpha) half of the map does not depend on
    # the binding energy, so it is solved once for the whole cube. Only the
    # photon energy that E_kin corresponds to moves from slice to slice.
    kinetic, alpha_wanted = inverse(
        grid_kz, grid_par, inner_potential=inner_potential,
        effective_mass=effective_mass, theta_position=theta_p)

    from arpes_viewer.tools.momentum.kspace import result_dtype
    out = np.empty((kz_axis.size, kpar_axis.size, energy.size),
                   dtype=result_dtype(cube.dtype))
    for index in range(energy.size):
        if progress is not None:
            progress(index, energy.size)
        hv_wanted = kinetic + work_function - float(energy[index])
        plane = np.asarray(cube[:, :, index], dtype=float)
        out[:, :, index] = _sample_plane(plane, photon_energy,
                                         alpha_axis, hv_wanted, alpha_wanted)
    return kz_axis, kpar_axis, energy, out


# --------------------------------------------------------------------------
# The inner potential
# --------------------------------------------------------------------------
def photon_arc(photon_energy: float, angle, *, inner_potential: float,
               work_function: float, effective_mass: float = 1.0,
               angle_offset: float = 0.0, theta_position: float = 0.0,
               binding_energy: float = 0.0):
    """The locus one photon energy traces in ``(k_z, k_par)`` as the
    detector angle sweeps.

    Drawn over a Brillouin zone this is how you see which photon energies
    reach which high-symmetry planes, with ``theta_position`` in ``k_z``.
    """
    alpha = np.radians(np.asarray(angle, dtype=float)) - np.radians(angle_offset)
    kinetic = float(photon_energy) - work_function + binding_energy
    k_par, k_z = forward(np.full(alpha.shape, kinetic), alpha,
                         inner_potential=inner_potential,
                         effective_mass=effective_mass,
                         theta_position=np.radians(theta_position))
    return k_z, k_par


class PeriodScan:
    """What :func:`scan_inner_potential` found, and how much to trust it."""

    def __init__(self, inner_potentials, periods, target, best):
        #: The inner potentials tried, eV.
        self.inner_potentials = inner_potentials
        #: The k_z period the data shows at each of them, A^-1.
        self.periods = periods
        #: The period the lattice demands, 2*pi/spacing, A^-1.
        self.target = target
        #: Where the two cross, eV, or None if they never do.
        self.best = best

    @property
    def sensitivity(self) -> float:
        """d(period)/d(V0), A^-1 per eV. How sharply the scan distinguishes
        one inner potential from another -- small means it barely does."""
        good = np.isfinite(self.periods)
        if good.sum() < 3:
            return 0.0
        return float(np.polyfit(self.inner_potentials[good],
                                self.periods[good], 1)[0])

    def uncertainty(self, period_error: float = 0.02) -> float:
        """How well V0 is pinned, in eV, if the period can be measured to
        ``period_error`` (a fraction).

        Worth reporting next to the answer. A photon-energy scan covering
        only a couple of zones constrains the inner potential to a few eV at
        best, and that is a property of the measurement rather than of the
        software -- but it is invisible unless someone puts a number on it.
        """
        slope = self.sensitivity
        if not slope:
            return float("inf")
        return abs(period_error * self.target / slope)


def _dominant_period(axis, profile, target, span=(0.5, 2.0), samples=600):
    """The period the profile actually shows, searched around ``target``."""
    good = np.isfinite(profile)
    if good.sum() < 16:
        return float("nan")
    a = axis[good]
    p = profile[good] - profile[good].mean()
    trial = np.linspace(span[0] * target, span[1] * target, samples)
    phase = 2 * np.pi * a[None, :] / trial[:, None]
    amplitude = np.hypot((p * np.cos(phase)).sum(axis=1),
                         (p * np.sin(phase)).sum(axis=1))
    return float(trial[int(np.argmax(amplitude))])


def scan_inner_potential(photon_energy, angle, energy, cube, *, spacing: float,
                         work_function: float, effective_mass: float = 1.0,
                         angle_offset: float = 0.0, theta_position: float = 0.0,
                         binding_energy: float = 0.0, kpar_halfwidth: float = 0.3,
                         inner_potentials=None, n_kz: int = 400,
                         progress=None) -> PeriodScan:
    """Find the inner potential whose conversion makes the k_z pattern
    repeat with the lattice's own period.

    One energy slice is converted at each trial ``V0`` -- a few milliseconds
    each -- the intensity is averaged over a narrow band of ``k_par`` around
    normal emission, and the period of that profile is measured. The right
    ``V0`` is where it equals ``2*pi/spacing``.

    ``spacing`` is the repeat distance along the surface normal, in A: ``c``
    for a simple stack, but ``c/2`` or an interplanar spacing for anything
    else, which is exactly the ambiguity :func:`tools.crystal.cleavage.candidates`
    is for.

    This is a weak measurement and the result says so: see
    :meth:`PeriodScan.uncertainty`. It narrows the search; it does not settle
    it. What settles it is the pattern lining up with the zone boundaries,
    which is a thing to look at rather than a number.
    """
    if inner_potentials is None:
        inner_potentials = np.arange(2.0, 30.5, 0.5)
    inner_potentials = np.asarray(inner_potentials, dtype=float)
    target = 2.0 * np.pi / float(spacing)

    slice_index = int(np.argmin(np.abs(np.asarray(energy, dtype=float)
                                       - binding_energy)))
    plane = np.asarray(cube, dtype=float)[:, :, slice_index]
    one_energy = np.asarray([float(np.asarray(energy)[slice_index])])

    periods = np.full(inner_potentials.size, np.nan)
    for position, v0 in enumerate(inner_potentials):
        if progress is not None:
            progress(position, inner_potentials.size)
        try:
            kz_axis, kpar_axis, _e, small = to_kz_cube(
                photon_energy, angle, one_energy, plane[:, :, None],
                inner_potential=float(v0), work_function=work_function,
                effective_mass=effective_mass, angle_offset=angle_offset,
                theta_position=theta_position, n_kz=n_kz,
                n_kpar=64,
                kpar_range=(-kpar_halfwidth, kpar_halfwidth))
        except ValueError:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            profile = np.nanmean(small[:, :, 0], axis=1)
        periods[position] = _dominant_period(kz_axis, profile, target)

    difference = periods - target
    best = None
    finite = np.isfinite(difference)
    if finite.sum() >= 2:
        values = inner_potentials[finite]
        delta = difference[finite]
        crossings = np.flatnonzero(np.diff(np.sign(delta)) != 0)
        if crossings.size:
            i = int(crossings[0])
            best = float(values[i] - delta[i] * (values[i + 1] - values[i])
                         / (delta[i + 1] - delta[i]))
    return PeriodScan(inner_potentials, periods, target, best)


# --------------------------------------------------------------------------
# Is the Fermi surface flat enough to convert?
# --------------------------------------------------------------------------
def edge_flatness(cube, angle, energy, *, binding_energy: float = 0.0,
                  window: float = 0.35, groups: int = 24):
    """How far the Fermi edge bends across the analyser angle, in eV.

    A curved edge is an artefact of the analyser, not of the sample, and the
    conversion cannot know the difference: it reads the energy axis
    literally, so a bend of a tenth of an electronvolt becomes a bend in
    ``k_z`` that looks like dispersion. Straightening it first is the Fermi
    surface correction, and this is the cheap check that says whether it is
    still needed.

    A screening number, not a calibration, and it has to be one the eye
    agrees with. The steepest fall of each single channel does not do: the
    weak channels at the ends of the slit, and a band crossing E_F inside
    the window, each throw one channel tens of meV away, and the largest
    minus the smallest of all channels is then set by the worst one. So:

    * the channels are summed in ``groups`` blocks of neighbours, and each
      block's EDC is smoothed over about 15 meV, before its steepest fall
      is taken;
    * blocks whose step down at E_F is under a third of the median step
      (the slit ends, a dead stretch of detector) are left out;
    * a parabola is fitted through the remaining edge positions, with the
      points more than three robust deviations off it dropped once, and the
      spread reported is the parabola's range over the angles measured --
      the analyser's bend is smooth, which a stray block is not.

    Returns ``(spread_eV, positions, angles)``: the edge position of each
    block kept, and the block's mean angle.
    """
    cube = np.asarray(cube, dtype=float)
    angle = np.asarray(angle, dtype=float)
    energy = np.asarray(energy, dtype=float)
    empty = (0.0, np.zeros(0), np.zeros(0))

    near = np.abs(energy - binding_energy) <= window
    if near.sum() < 8:
        near = np.ones(energy.size, dtype=bool)
    band = energy[near]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        frame = np.nanmean(cube[:, :, near], axis=0)        # (angle, E)
    usable = np.isfinite(frame).all(axis=1)
    if usable.sum() < 2 or band.size < 5:
        return empty
    frame, angles_used = frame[usable], angle[usable]

    blocks = np.array_split(np.arange(angles_used.size),
                            min(int(groups), angles_used.size))
    step = float(np.mean(np.abs(np.diff(band))))
    width = max(1, int(round(0.015 / step / 2.355)))          # sigma, samples
    kernel = np.exp(-0.5 * (np.arange(-3 * width, 3 * width + 1) / width) ** 2)
    kernel /= kernel.sum()
    order = np.argsort(band)
    band = band[order]

    positions, centres, heights = [], [], []
    for block in blocks:
        edc = frame[block].sum(axis=0)[order]
        padded = np.pad(edc, kernel.size // 2, mode="edge")
        smooth = np.convolve(padded, kernel, mode="valid")
        slope = np.gradient(smooth, band)
        trim = min(kernel.size // 2 + 1, band.size // 4)
        if trim:
            slope[:trim] = slope[-trim:] = 0.0
        at = int(np.argmin(slope))
        positions.append(float(band[at]))
        centres.append(float(np.mean(angles_used[block])))
        quarter = max(2, band.size // 8)
        heights.append(float(np.mean(smooth[:quarter]) - np.mean(smooth[-quarter:])))
    positions, centres, heights = map(np.asarray, (positions, centres, heights))

    median = float(np.median(heights))
    keep = heights >= (median / 3.0 if median > 0 else -np.inf)
    positions, centres = positions[keep], centres[keep]
    if positions.size < 2:
        return empty
    if positions.size < 4:
        return float(np.ptp(positions)), positions, centres

    def parabola(x, y):
        return np.polyval(np.polyfit(x, y, 2), x)

    fitted = parabola(centres, positions)
    residual = positions - fitted
    scale = 1.4826 * float(np.median(np.abs(residual - np.median(residual))))
    good = np.abs(residual) <= max(3.0 * scale, 2.0 * step)
    if good.sum() >= 4 and not good.all():
        fitted = parabola(centres[good], positions[good])
        positions, centres = positions[good], centres[good]
    grid = np.linspace(centres.min(), centres.max(), 101)
    curve = np.polyval(np.polyfit(centres, positions, 2), grid)
    return float(np.ptp(curve)), positions, centres
