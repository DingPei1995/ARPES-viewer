"""
tools/spectra/pocket.py
=======================
A Fermi pocket of a **quasi-two-dimensional** sample, from a k-map: its
contour, its area, and what the area says. No Qt. Under test (new in 1.3.3).

Only for quasi-two-dimensional samples
--------------------------------------
Everything here turns the *area* a contour encloses in the (kx, ky) plane
into a carrier density, a quantum-oscillation frequency and a cyclotron
mass. That is right when the bands do not disperse along k_z -- a surface
state, a single layer, a layered material whose Fermi surface is a
cylinder: then one map is the whole Fermi surface, the carriers are counted
per unit cell of the *plane*, and every orbit has the same area. For a
three-dimensional Fermi surface a map is one curved sheet through it, at a
k_z that depends on the photon energy and the inner potential and is
smeared by the escape depth; the contour it shows is not an extremal
orbit, and its area is not a density. The functions cannot tell the two
cases apart: the caller has to.

How a contour is found
----------------------
From a point inside the pocket, rays go out at equal angles. Along each the
intensity of the constant-energy plane is a peak where the ray crosses the
band, and a Lorentzian on a straight background is fitted to it inside the
ring the caller allows: its centre is ``k_F`` along that ray, with an error.
A ray whose answer jumps away from its neighbours is fitted again near
them, and dropped if it still disagrees (a second band, a gap in the
data). The radius against angle is then a short Fourier series, weighted
by the errors -- with only the harmonics a stated rotational symmetry
allows, if one is given -- and the area follows from its coefficients
exactly, with an error from their covariance:

    A = (1/2) \\oint r^2 d\\phi = pi a_0^2 + (pi/2) sum_m (a_m^2 + b_m^2)

The centre need only be inside the pocket, with every ray crossing the
contour once: the area does not depend on where it is.

What the area gives (quasi-2D)
------------------------------
* carrier density ``n = g N A / (2 pi)^2`` (``g`` spin degeneracy, ``N``
  equivalent pockets in the zone), and per in-plane unit cell
  ``g N A / A_BZ`` -- the number Luttinger's theorem counts;
* the frequency of quantum oscillations, ``F = (hbar / 2 pi e) A``;
* from the area at several energies, the cyclotron mass
  ``m_c = (hbar^2 / 2 pi) dA/dE``, positive for an electron pocket (it
  grows with energy) and negative for a hole pocket.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import optimize

from arpes_viewer.tools.processing.process import _bilinear
from arpes_viewer.tools.spectra.dispersion import HBAR2_OVER_2M, fit_dispersion

__all__ = ["energy_plane", "radial_profiles", "fit_ray", "trace", "Contour",
           "FourierContour", "numbers", "cell_area", "series", "PocketSeries",
           "FREQUENCY_FACTOR", "MASS_FACTOR", "NOTICE"]

#: What every window, table and result of this module says about itself.
NOTICE = ("Under test (new in 1.3.3). Valid only for quasi-two-dimensional "
          "samples (surface states, layered materials with negligible k_z "
          "dispersion): for a three-dimensional Fermi surface the area of "
          "a contour in one map is not a carrier density.")

#: F [T] = FREQUENCY_FACTOR * A [A^-2]: hbar / (2 pi e), with A^-2 -> m^-2.
FREQUENCY_FACTOR = 1.054571817e-34 / (2.0 * np.pi * 1.602176634e-19) * 1e20
#: m_c / m_e = MASS_FACTOR * dA/dE [A^-2 / eV]: hbar^2 / (2 pi m_e).
MASS_FACTOR = HBAR2_OVER_2M / np.pi


# ==========================================================================
# The plane and its rays
# ==========================================================================
def energy_plane(values, axes, energy: float, half_width: float = 0.0):
    """The constant-energy plane of a k-map ``values[kx, ky, E]`` at
    ``energy``, averaged over ``energy +- half_width``: ``(plane, (lo, hi))``
    with the energies actually used (the nearest one, at least).

    At E_F itself the Fermi cut-off empties the upper half of the window,
    so the plane is that of an energy a little below the one asked for --
    by about a quarter of the window's width. Keep the window narrow there,
    or take the area at E_F from :func:`series`, which follows it up to E_F
    from below.
    """
    values = np.asarray(values)
    if values.ndim != 3:
        raise ValueError("a Fermi pocket is traced on a map (kx, ky, E), "
                         f"not on {values.ndim}-D data")
    e = np.asarray(axes[2], dtype=float)
    inside = np.flatnonzero(np.abs(e - float(energy)) <= abs(float(half_width)))
    if inside.size == 0:
        inside = np.array([int(np.argmin(np.abs(e - float(energy))))])
    block = np.asarray(values[:, :, inside.min():inside.max() + 1], dtype=float)
    with np.errstate(invalid="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            plane = np.nanmean(block, axis=2)
    return plane, (float(e[inside].min()), float(e[inside].max()))


def radial_profiles(plane, kx, ky, centre, angles, radii, *,
                    sector: float = None, samples: int = 3):
    """The intensity along rays from ``centre``: ``profiles[angle, radius]``.

    Each ray is the mean of ``samples`` lines spread over ``sector``
    radians (by default the step between the angles), so that every pixel
    of the ring is used once rather than only those a thin line happens to
    cross. Points outside the map, or where it has no data, are NaN.
    """
    angles = np.asarray(angles, dtype=float)
    radii = np.asarray(radii, dtype=float)
    if sector is None:
        sector = 2.0 * np.pi / max(angles.size, 1)
    samples = max(1, int(samples))
    offsets = (np.linspace(-0.5, 0.5, samples + 2)[1:-1] * float(sector)
               if samples > 1 else np.zeros(1))
    total = np.zeros((angles.size, radii.size))
    count = np.zeros_like(total)
    for offset in offsets:
        phi = angles[:, None] + offset
        x = float(centre[0]) + radii[None, :] * np.cos(phi)
        y = float(centre[1]) + radii[None, :] * np.sin(phi)
        sampled = _bilinear(plane, np.asarray(kx, float), np.asarray(ky, float),
                            x, y).reshape(x.shape)
        good = np.isfinite(sampled)
        total += np.where(good, sampled, 0.0)
        count += good
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan)


def _lorentzian_line(r, centre, width, height, offset, slope):
    return (height / (1.0 + ((r - centre) / (0.5 * width)) ** 2)
            + offset + slope * (r - centre))


def fit_ray(radii, profile, lo: float, hi: float, guess: float = None,
            reach: float = None, floor: float = 0.0):
    """The peak of one ray between ``lo`` and ``hi``: a Lorentzian on a
    straight background. Returns a dict with ``k`` (the centre),
    ``k_error``, ``width`` (FWHM), ``height``, ``ok`` and, when not ok,
    ``why``; ``model`` is the fitted curve on ``radii`` (NaN outside the
    points fitted).

    With ``guess`` (and ``reach``) the peak is looked for only within
    ``reach`` of ``guess`` -- how a ray that jumped to another band is
    brought back to its neighbours. A peak lower than ``floor`` is not
    one (see :func:`trace`), nor is one under five times the ray's own
    point-to-point noise.
    """
    radii = np.asarray(radii, dtype=float)
    profile = np.asarray(profile, dtype=float)
    out = {"k": np.nan, "k_error": np.nan, "width": np.nan, "height": np.nan,
           "ok": False, "why": "", "model": np.full(radii.shape, np.nan)}
    lo, hi = float(min(lo, hi)), float(max(lo, hi))
    if guess is not None and reach is not None and np.isfinite(guess):
        lo, hi = max(lo, guess - reach), min(hi, guess + reach)
    take = np.isfinite(profile) & (radii >= lo) & (radii <= hi)
    if take.sum() < 7:
        out["why"] = "no data in the ring"
        return out
    r, y = radii[take], profile[take]
    step = float(np.median(np.diff(r))) or 1e-6
    smooth = np.convolve(np.pad(y, 1, mode="edge"), np.ones(3) / 3.0,
                         mode="valid")
    top = int(np.argmax(smooth))
    base = float(np.percentile(y, 10))
    height = float(smooth[top] - base)
    if height <= 0:
        out["why"] = "no peak"
        return out
    above = smooth - base >= 0.5 * height
    left = top
    while left > 0 and above[left - 1]:
        left -= 1
    right = top
    while right < r.size - 1 and above[right + 1]:
        right += 1
    width = max(float(r[right] - r[left]), 2.0 * step)
    width = min(width, 0.6 * (hi - lo))

    start = np.array([r[top], width, height, base, 0.0])
    lower = np.array([lo, step, 0.0, -np.inf, -np.inf])
    upper = np.array([hi, hi - lo, np.inf, np.inf, np.inf])
    start = np.clip(start, lower + 1e-12, upper - 1e-12)

    def residual(p):
        return _lorentzian_line(r, *p) - y

    try:
        found = optimize.least_squares(residual, start, bounds=(lower, upper),
                                       x_scale=[width, width, height or 1.0,
                                                height or 1.0,
                                                (height or 1.0) / (hi - lo)])
    except (ValueError, np.linalg.LinAlgError) as exc:
        out["why"] = f"the fit failed ({exc})"
        return out
    centre, width, height = (float(v) for v in found.x[:3])
    dof = max(r.size - 5, 1)
    noise = float(np.sqrt(np.sum(found.fun ** 2) / dof))
    # the scatter of each point about its two neighbours: a noise the fit
    # cannot have absorbed into its five parameters
    jitter = 1.4826 * float(np.median(np.abs(
        y[1:-1] - 0.5 * (y[:-2] + y[2:])))) / np.sqrt(1.5)
    try:
        covariance = np.linalg.inv(found.jac.T @ found.jac) * noise ** 2
        error = float(np.sqrt(max(covariance[0, 0], 0.0)))
    except np.linalg.LinAlgError:
        error = np.nan
    out.update({"k": centre, "k_error": error, "width": width,
                "height": height})
    out["model"][take] = _lorentzian_line(r, *found.x)
    if not found.success:
        out["why"] = "the fit did not converge"
    elif min(centre - r[0], r[-1] - centre) < max(step, 0.5 * width):
        # both sides of the peak have to be there: half a peak at the end
        # of the ring, or of the data, is a slope and not a band
        out["why"] = ("the peak is at the edge of the ring"
                      if min(centre - lo, hi - centre) < max(step, 0.5 * width)
                      else "the peak is at the edge of the data")
    elif height < 5.0 * max(noise, jitter):
        out["why"] = "no peak above the noise"
    elif height < floor:
        out["why"] = "too weak beside the rest of the map"
    elif width > 0.8 * (hi - lo):
        out["why"] = "wider than the ring"
    elif not np.isfinite(error):
        out["why"] = "no error could be worked out"
    else:
        out["ok"] = True
    return out


# ==========================================================================
# The contour
# ==========================================================================
@dataclass
class FourierContour:
    """``r(phi) = a_0 + sum_m [a_m cos(m phi) + b_m sin(m phi)]`` through
    the fitted radii, and the area inside it."""
    harmonics: np.ndarray                # the m > 0 kept
    coefficients: np.ndarray             # a_0, then (a_m, b_m) per harmonic
    covariance: np.ndarray
    chi2: float = float("nan")
    points: int = 0

    def radius(self, angles):
        angles = np.asarray(angles, dtype=float)
        return _design(angles, self.harmonics) @ self.coefficients

    def area(self):
        """``(A, error)`` in the units of k squared."""
        c = self.coefficients
        area = np.pi * c[0] ** 2 + 0.5 * np.pi * float(np.sum(c[1:] ** 2))
        gradient = np.concatenate([[2.0 * np.pi * c[0]], np.pi * c[1:]])
        variance = float(gradient @ self.covariance @ gradient)
        return float(area), float(np.sqrt(max(variance, 0.0)))

    def extremes(self, samples: int = 720):
        """``(r_min, angle, r_max, angle)`` of the contour (angles in rad)."""
        phi = np.linspace(0.0, 2.0 * np.pi, samples, endpoint=False)
        r = self.radius(phi)
        low, high = int(np.argmin(r)), int(np.argmax(r))
        return float(r[low]), float(phi[low]), float(r[high]), float(phi[high])

    def centroid(self, centre=(0.0, 0.0), samples: int = 720):
        """The centre of area of the contour, in the map's coordinates."""
        phi = np.linspace(0.0, 2.0 * np.pi, samples, endpoint=False)
        r = self.radius(phi)
        area = 0.5 * np.mean(r ** 2)
        if area <= 0:
            return float(centre[0]), float(centre[1])
        return (float(centre[0] + np.mean(r ** 3 * np.cos(phi)) / (3.0 * area)),
                float(centre[1] + np.mean(r ** 3 * np.sin(phi)) / (3.0 * area)))


def _design(angles, harmonics):
    columns = [np.ones(angles.shape)]
    for m in harmonics:
        columns += [np.cos(m * angles), np.sin(m * angles)]
    return np.stack(columns, axis=-1)


@dataclass
class Contour:
    """A pocket traced ray by ray."""
    centre: tuple
    angles: np.ndarray                   # rad, 0 along +kx, counter-clockwise
    radius: np.ndarray                   # k_F along each ray; NaN if none
    radius_error: np.ndarray
    width: np.ndarray                    # FWHM of the peak along the ray
    height: np.ndarray
    ok: np.ndarray                       # the rays kept
    why: list = field(default_factory=list)
    ring: tuple = (0.0, 0.0)
    radii: np.ndarray = None             # the rays themselves, for a picture
    profiles: np.ndarray = None
    models: np.ndarray = None
    energy: float = float("nan")

    def enough(self) -> bool:
        """Whether enough rays found the band for a contour to be believed:
        a third of them, and six at least. Fewer is a ring that misses the
        band, or noise taken for one."""
        return int(self.ok.sum()) >= max(6, self.ok.size // 3)

    def xy(self, only_ok: bool = True):
        take = self.ok if only_ok else np.isfinite(self.radius)
        return (self.centre[0] + self.radius[take] * np.cos(self.angles[take]),
                self.centre[1] + self.radius[take] * np.sin(self.angles[take]))

    def polygon_area(self) -> float:
        """The area of the polygon through the rays kept (no smoothing):
        the check on :meth:`fourier`'s area."""
        x, y = self.xy()
        if x.size < 3:
            return float("nan")
        return float(0.5 * abs(np.sum(x * np.roll(y, -1) - y * np.roll(x, -1))))

    def scatter(self, fitted: "FourierContour") -> float:
        """The RMS distance of the rays kept from the contour ``fitted``,
        in units of their median peak width. Well under a quarter when the
        contour describes them; near one when it runs *between* two
        populations of rays -- two bands inside the ring, each taking some
        of them -- or cannot follow the shape (too few harmonics, a centre
        far from the middle)."""
        take = self.ok & np.isfinite(self.radius)
        if take.sum() < 3:
            return float("nan")
        residual = self.radius[take] - fitted.radius(self.angles[take])
        width = float(np.median(self.width[take]))
        return float(np.sqrt(np.mean(residual ** 2)) / width) if width > 0 \
            else float("nan")

    def fourier(self, order: int = 6, fold: int = 1) -> FourierContour:
        """The radius against angle as a Fourier series up to harmonic
        ``order``, weighted by the fitted errors. ``fold`` > 1 keeps only
        the harmonics an n-fold rotation axis through the centre allows
        (``fold``, ``2 fold``, ...): fewer parameters, and a contour with
        the symmetry -- only right when the centre is on that axis."""
        take = self.ok & np.isfinite(self.radius)
        count = int(take.sum())
        fold = max(1, int(fold))
        harmonics = np.arange(fold, max(int(order), 0) + 1, fold)
        # never more parameters than a third of the rays
        harmonics = harmonics[:max((count // 3 - 1) // 2, 0)]
        if count < 3:
            raise ValueError("fewer than three rays found the band: check "
                             "the centre and the ring")
        phi, r = self.angles[take], self.radius[take]
        sigma = np.asarray(self.radius_error, dtype=float)[take]
        usable = np.isfinite(sigma) & (sigma > 0)
        typical = float(np.median(sigma[usable])) if usable.any() else 1.0
        sigma = np.where(usable, sigma, typical)
        # one collapsed fit must not take the whole weight
        sigma = np.maximum(sigma, 0.2 * typical)
        design = _design(phi, harmonics)
        scaled = design / sigma[:, None]
        coefficients, *_ = np.linalg.lstsq(scaled, r / sigma, rcond=None)
        dof = max(count - coefficients.size, 1)
        chi2 = float(np.sum(((r - design @ coefficients) / sigma) ** 2) / dof)
        try:
            covariance = np.linalg.inv(scaled.T @ scaled) * max(chi2, 1e-12)
        except np.linalg.LinAlgError:
            covariance = np.full((coefficients.size,) * 2, np.nan)
        return FourierContour(harmonics, coefficients, covariance, chi2, count)


def trace(plane, kx, ky, centre, r_min: float, r_max: float, *,
          n_angles: int = 72, n_radii: int = None, guess=None,
          reach: float = None, contrast: float = 0.02) -> Contour:
    """Trace the pocket around ``centre`` on a constant-energy ``plane``
    (``plane[kx, ky]``): one fitted ``k_F`` per ray, looked for between
    ``r_min`` and ``r_max`` from the centre.

    ``guess`` (a radius, or one per ray, or a function of the angle) with
    ``reach`` confines every ray to ``guess +- reach`` -- how a contour is
    followed from one energy to the next. A peak is taken for the band
    only if it stands at least ``contrast`` times the plane's own range
    (its brightest half percent above its median) high: in a ring that
    holds no band, the bumps of the noise are not a contour.
    """
    kx, ky = np.asarray(kx, dtype=float), np.asarray(ky, dtype=float)
    r_min, r_max = float(min(r_min, r_max)), float(max(r_min, r_max))
    if r_max - r_min <= 0:
        raise ValueError("the ring has no width: give two different radii")
    n_angles = max(8, int(n_angles))
    step = min(abs(kx[-1] - kx[0]) / max(kx.size - 1, 1),
               abs(ky[-1] - ky[0]) / max(ky.size - 1, 1)) or 1e-3
    if n_radii is None:
        n_radii = int(np.clip(np.ceil((r_max - r_min) / (0.5 * step)), 16, 600))
    radii = np.linspace(r_min, r_max, int(n_radii))
    angles = np.arange(n_angles) * 2.0 * np.pi / n_angles
    profiles = radial_profiles(plane, kx, ky, centre, angles, radii)

    if callable(guess):
        guesses = np.asarray(guess(angles), dtype=float)
    elif guess is None:
        guesses = np.full(n_angles, np.nan)
    else:
        guesses = np.broadcast_to(np.asarray(guess, dtype=float),
                                  (n_angles,)).astype(float)
    if reach is None and np.isfinite(guesses).any():
        reach = 0.25 * (r_max - r_min)

    finite = np.asarray(plane, dtype=float)
    finite = finite[np.isfinite(finite)]
    floor = (float(contrast) * float(np.percentile(finite, 99.5)
                                     - np.median(finite))
             if finite.size else 0.0)

    def one(index, near=None, within=None):
        return fit_ray(radii, profiles[index], r_min, r_max,
                       guess=near, reach=within, floor=floor)

    fits = [one(i, guesses[i] if np.isfinite(guesses[i]) else None, reach)
            for i in range(n_angles)]

    # A ray that disagrees with its neighbours found something else: look
    # again near them, and drop it if it still disagrees.
    def neighbours(index, values, good):
        picked = [values[(index + d) % n_angles] for d in (-3, -2, -1, 1, 2, 3)
                  if good[(index + d) % n_angles]]
        return float(np.median(picked)) if len(picked) >= 2 else np.nan

    for _pass in range(2):
        values = np.array([f["k"] for f in fits])
        good = np.array([f["ok"] for f in fits])
        if good.sum() < 4:
            break
        widths = np.array([f["width"] for f in fits])
        typical = float(np.median(widths[good]))
        changed = False
        for i in range(n_angles):
            near = neighbours(i, values, good)
            if not np.isfinite(near):
                continue
            if good[i] and abs(values[i] - near) <= max(typical, 3.0 * step):
                continue
            again = one(i, near, max(1.5 * typical, 4.0 * step))
            if again["ok"] and abs(again["k"] - near) <= max(typical, 3.0 * step):
                changed = changed or not good[i] or again["k"] != values[i]
                fits[i] = again
            elif good[i]:
                fits[i] = dict(fits[i], ok=False,
                               why="away from the neighbouring rays")
                changed = True
        if not changed:
            break

    return Contour(
        (float(centre[0]), float(centre[1])), angles,
        np.array([f["k"] for f in fits]),
        np.array([f["k_error"] for f in fits]),
        np.array([f["width"] for f in fits]),
        np.array([f["height"] for f in fits]),
        np.array([bool(f["ok"]) for f in fits]),
        [f["why"] for f in fits], (r_min, r_max), radii, profiles,
        np.array([f["model"] for f in fits]))


# ==========================================================================
# What the area says (quasi-2D only)
# ==========================================================================
def cell_area(a: float, b: float = None, gamma_deg: float = 90.0) -> float:
    """The area of the in-plane unit cell (A^2); its Brillouin zone has
    the area ``(2 pi)^2`` over this."""
    b = a if not b else b
    return float(abs(a * b * np.sin(np.radians(gamma_deg))))


def numbers(area: float, area_error: float = 0.0, *, spin: int = 2,
            pockets: int = 1, cell: float = None) -> dict:
    """What an area ``A`` (A^-2) enclosed by a Fermi contour means **for a
    quasi-two-dimensional sample** (see the module's notes):

    ``k_f``: the radius of the circle of that area; ``density`` (cm^-2):
    ``spin * pockets * A / (2 pi)^2``; ``frequency`` (T): of quantum
    oscillations, ``(hbar / 2 pi e) A`` per pocket; and with ``cell`` (the
    in-plane cell's area, A^2, see :func:`cell_area`) ``zone_fraction``
    (``A / A_BZ``, one pocket) and ``per_cell`` (carriers per cell, all
    pockets and spins). Each with ``<name>_error`` from ``area_error``.
    """
    area, area_error = float(area), abs(float(area_error))
    spin, pockets = int(spin), int(pockets)
    relative = area_error / area if area > 0 else float("nan")
    density = spin * pockets * area / (2.0 * np.pi) ** 2 * 1e16
    out = {"area": area, "area_error": area_error,
           "k_f": float(np.sqrt(max(area, 0.0) / np.pi)),
           "density": density, "density_error": density * relative,
           "frequency": FREQUENCY_FACTOR * area,
           "frequency_error": FREQUENCY_FACTOR * area_error,
           "spin": spin, "pockets": pockets}
    out["k_f_error"] = 0.5 * out["k_f"] * relative
    if cell:
        zone = (2.0 * np.pi) ** 2 / float(cell)
        out.update({"zone_area": zone, "zone_fraction": area / zone,
                    "zone_fraction_error": area_error / zone,
                    "per_cell": spin * pockets * area / zone,
                    "per_cell_error": spin * pockets * area_error / zone})
    return out


@dataclass
class PocketSeries:
    """The area of one pocket at several energies."""
    energies: np.ndarray
    areas: np.ndarray
    area_errors: np.ndarray
    contours: list = field(default_factory=list)
    ef: float = 0.0

    def line(self):
        """The straight line ``A(E)`` through the areas found, weighted by
        their errors (a ``Dispersion`` of order 1, in E - E_F), or None
        with fewer than three."""
        good = np.isfinite(self.areas) & np.isfinite(self.energies)
        if good.sum() < 3:
            return None
        sigma = self.area_errors[good]
        weighted = np.all(np.isfinite(sigma) & (sigma > 0))
        return fit_dispersion(self.energies[good] - self.ef, self.areas[good],
                              energy_error=sigma if weighted else None, order=1)

    def mass(self):
        """``(m_c / m_e, error)``: ``(hbar^2 / 2 pi) dA/dE``. Positive: the
        pocket grows with energy, an electron pocket; negative: a hole
        pocket. The mass of a parabolic band, and the cyclotron mass of
        any (quasi-2D) one."""
        line = self.line()
        if line is None:
            return float("nan"), float("nan")
        return (MASS_FACTOR * float(line.coefficients[0]),
                MASS_FACTOR * float(line.errors[0]))

    def carrier(self) -> str:
        """``"electron"``, ``"hole"`` or ``""`` when the slope is not
        significant (less than twice its error)."""
        mass, error = self.mass()
        if not np.isfinite(mass) or not np.isfinite(error) or abs(mass) < 2 * error:
            return ""
        return "electron" if mass > 0 else "hole"

    def area_at_ef(self):
        """``(A, error)`` at E_F, read off the line: free of the bias the
        Fermi cut-off gives a plane taken at E_F itself."""
        line = self.line()
        if line is None:
            return float("nan"), float("nan")
        return float(line.coefficients[1]), float(line.errors[1])

    def band_edge(self) -> float:
        """The energy (as the map has it) at which the line reaches zero
        area: the bottom of an electron band, the top of a hole band, if
        it is parabolic that far."""
        line = self.line()
        if line is None or abs(line.coefficients[0]) < 1e-30:
            return float("nan")
        return float(self.ef - line.coefficients[1] / line.coefficients[0])

    def fermi_velocity(self):
        """``(v_F, error)`` in eV*A, averaged round the pocket:
        ``hbar k_F / m_c`` with ``k_F`` the radius of the circle of the
        area at E_F."""
        mass, mass_error = self.mass()
        area, _error = self.area_at_ef()
        if not np.isfinite(mass) or mass == 0 or not area > 0:
            return float("nan"), float("nan")
        velocity = 2.0 * HBAR2_OVER_2M * np.sqrt(area / np.pi) / abs(mass)
        return float(velocity), float(velocity * abs(mass_error / mass))


def series(values, axes, centre, energies, r_min: float, r_max: float, *,
           half_width: float = 0.0, n_angles: int = 72, order: int = 6,
           fold: int = 1, ef: float = 0.0, follow: bool = True,
           progress=None) -> PocketSeries:
    """The pocket's area at each of ``energies``: the contour traced on
    each plane, and -- with ``follow`` -- each looked for near the one
    before, so that the same band is followed where another comes close.
    Start from the energy where the pocket is clearest (the first given).
    An energy at which no contour is found has NaN."""
    energies = np.asarray(energies, dtype=float)
    areas = np.full(energies.size, np.nan)
    errors = np.full(energies.size, np.nan)
    contours = [None] * energies.size
    previous = None
    for index, energy in enumerate(energies):
        if progress is not None:
            progress(index / max(energies.size, 1), f"E = {energy:.4g}")
        plane, _used = energy_plane(values, axes, energy, half_width)
        try:
            contour = trace(plane, axes[0], axes[1], centre, r_min, r_max,
                            n_angles=n_angles,
                            guess=previous.radius if previous is not None else None,
                            reach=0.2 * (r_max - r_min) if previous is not None
                            else None)
            fitted = contour.fourier(order, fold)
        except ValueError:
            continue
        contour.energy = float(energy)
        if not contour.enough():
            continue                     # too little of it left to believe
        areas[index], errors[index] = fitted.area()
        contours[index] = contour
        if follow:
            previous = fitted
    return PocketSeries(energies, areas, errors, contours, float(ef))
