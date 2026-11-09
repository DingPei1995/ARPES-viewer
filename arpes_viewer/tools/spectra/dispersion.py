"""
tools/spectra/dispersion.py
===========================
What comes out of a fitted band: the dispersion, the Fermi velocity, the
effective mass, and the self-energy. No Qt.

Three things done with care
---------------------------
**The errors are on the fitted axis.** An MDC fit measures a *momentum* at a
known energy, so its uncertainty is on k; an EDC fit measures an energy at a
known momentum. Fitting ``E(k)`` when the error is on k is an errors-in-variables
problem, and the fix is the effective-variance method: weight by
``sigma_E**2 + (dE/dk * sigma_k)**2``, iterating because the slope appears
in its own weight. On a steep band the difference is not cosmetic.

**A velocity and a mass are local.** ``v_F`` is the slope *at E_F* and ``m*``
is the curvature *at the band extremum*; a straight line or a parabola fitted
over the whole measured range returns an average over whatever else the band
was doing, and in a material with a kink those differ by tens of percent.
:func:`window_scan` fits over a family of windows and returns the value and
its error against window width, so the plateau -- if there is one -- can be
seen and quoted, and its absence can be seen too.

**The constant.** hbar^2/2m_e = 3.80998 eV*A^2 (CODATA), not the rounded
3.8155 that puts every mass 0.15 % low.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: hbar^2 / 2 m_e, in eV * A^2. E = HBAR2_OVER_2M * k^2 / (m*/m_e).
HBAR2_OVER_2M = 3.80998212
#: hbar in eV*s, for turning dE/dk in eV*A into a velocity in m/s.
HBAR_EVS = 6.582119569e-16
#: dE/dk [eV*A] * VELOCITY_FACTOR = v [m/s].
VELOCITY_FACTOR = 1e-10 / HBAR_EVS


@dataclass
class Dispersion:
    """A polynomial through a band, with what it implies."""
    coefficients: np.ndarray             # highest power first, E(k)
    errors: np.ndarray
    order: int
    k: np.ndarray
    energy: np.ndarray
    sigma: np.ndarray                    # the effective energy error used
    model: np.ndarray
    chi2: float = float("nan")
    error_axis: str = "y"
    covariance: np.ndarray = None

    def value(self, k):
        return np.polyval(self.coefficients, np.asarray(k, dtype=float))

    def slope(self, k):
        return np.polyval(np.polyder(self.coefficients),
                          np.asarray(k, dtype=float))

    def _slope_error(self, k: float) -> float:
        """Error on dE/dk at one k, from the full covariance.

        The derivative is a linear combination of the coefficients, so its
        variance needs the off-diagonal terms: for a parabola the linear and
        quadratic coefficients are strongly anticorrelated, and adding their
        variances in quadrature overestimates the error by a large factor.
        """
        if self.covariance is None or self.order < 1:
            return float("nan")
        powers = np.array([(self.order - i) * float(k) ** max(self.order - i - 1, 0)
                           for i in range(self.order)] + [0.0])
        variance = float(powers @ self.covariance @ powers)
        return float(np.sqrt(max(variance, 0.0)))

    def fermi_velocity(self, k_f: float = None):
        """``(dE/dk, error)`` at ``k_f``, in eV*A."""
        if k_f is None:
            k_f = float(np.mean(self.k))
        return float(self.slope(k_f)), self._slope_error(k_f)

    def velocity_ms(self, k_f: float = None):
        value, error = self.fermi_velocity(k_f)
        return value * VELOCITY_FACTOR, error * VELOCITY_FACTOR

    def effective_mass(self):
        """``(m*/m_e, error)`` from the quadratic term.

        Only defined for a parabola: a straight line has no curvature, and
        returning a number for it would be inventing one.
        """
        if self.order != 2:
            return float("nan"), float("nan")
        a = float(self.coefficients[0])
        if abs(a) < 1e-30:
            return float("nan"), float("nan")
        mass = HBAR2_OVER_2M / a
        error = abs(mass) * abs(float(self.errors[0]) / a)
        return mass, error

    def band_extremum(self):
        """Where a parabolic band turns over, as ``(k, E)``.

        The energy is the half that gets quoted -- the band bottom of an
        electron pocket, the top of a hole band -- so it comes back with
        the position rather than leaving the caller to evaluate the
        polynomial again and risk doing it on a different one.
        """
        if self.order != 2 or abs(self.coefficients[0]) < 1e-30:
            return float("nan"), float("nan")
        k = float(-self.coefficients[1] / (2.0 * self.coefficients[0]))
        return k, float(self.value(k))

    def crossing(self, level: float = 0.0):
        """Where the band crosses ``level`` (k_F for level = E_F)."""
        roots = np.roots(np.asarray(self.coefficients, dtype=float)
                         - np.append(np.zeros(self.order), float(level)))
        real = [float(r.real) for r in roots if abs(r.imag) < 1e-9]
        inside = [r for r in real if self.k.min() - 1e-9 <= r <= self.k.max() + 1e-9]
        return sorted(inside) if inside else sorted(real)

    def summary(self) -> str:
        lines = []
        value, error = self.fermi_velocity()
        speed, speed_error = self.velocity_ms()
        lines.append(f"dE/dk = {value:.4g} ± {error:.2g} eV·Å")
        lines.append(f"      = {speed:.4g} ± {speed_error:.2g} m/s")
        if self.order == 2:
            mass, mass_error = self.effective_mass()
            lines.append(f"m*/mₑ = {mass:.4g} ± {mass_error:.2g}")
            turn_k, turn_e = self.band_extremum()
            if np.isfinite(turn_k):
                edge = "bottom" if mass > 0 else "top"
                lines.append(f"band {edge} at k = {turn_k:.4g}, "
                             f"E = {turn_e:.4g}")
        lines.append(f"reduced χ² = {self.chi2:.3g}   "
                     f"({self.k.size} points)")
        return "\n".join(lines)


def fit_dispersion(k, energy, *, k_error=None, energy_error=None,
                   order: int = 1, iterations: int = 3) -> Dispersion:
    """Fit ``E(k)`` as a polynomial, weighted by whichever error is real.

    Give ``k_error`` for a band from MDC fits and ``energy_error`` for one
    from EDC fits. With ``k_error`` the weight is
    ``sigma_E_eff = |dE/dk| * sigma_k``, which needs the slope that is being
    fitted, so it is iterated -- three passes is far more than enough, the
    slope moves in the fourth decimal after the second.
    """
    k = np.asarray(k, dtype=float)
    energy = np.asarray(energy, dtype=float)
    good = np.isfinite(k) & np.isfinite(energy)
    if k_error is not None:
        k_error = np.asarray(k_error, dtype=float)
        good &= np.isfinite(k_error) & (k_error > 0)
    if energy_error is not None:
        energy_error = np.asarray(energy_error, dtype=float)
        good &= np.isfinite(energy_error) & (energy_error > 0)
    if good.sum() < order + 1:
        raise ValueError(f"need at least {order + 1} points for that order, "
                         f"have {int(good.sum())}")

    kf, ef = k[good], energy[good]
    design = np.vander(kf, order + 1)

    sigma = (energy_error[good] if energy_error is not None
             else np.ones(kf.shape))
    sigma = np.maximum(sigma, 0.1 * float(np.median(sigma)))   # see below
    coefficients = None
    for _ in range(max(1, int(iterations))):
        scaled = design / sigma[:, None]
        coefficients, *_ = np.linalg.lstsq(scaled, ef / sigma, rcond=None)
        if k_error is None:
            break
        slope = np.polyval(np.polyder(coefficients), kf)
        extra = np.abs(slope) * k_error[good]
        base = (energy_error[good] if energy_error is not None
                else np.zeros(kf.shape))
        sigma = np.hypot(base, extra)
        sigma = np.where(sigma > 0, sigma, np.nanmedian(sigma[sigma > 0])
                         if np.any(sigma > 0) else 1.0)
        # a peak fit that collapsed reports an error of ~1e-13: one such
        # point would take the whole weight (and make the normal matrix
        # singular), so no point counts for more than ten typical ones
        sigma = np.maximum(sigma, 0.1 * float(np.median(sigma)))

    model = design @ coefficients
    dof = max(int(kf.size - coefficients.size), 1)
    chi2 = float(np.sum(((ef - model) / sigma) ** 2) / dof)
    try:
        normal = (design / sigma[:, None]).T @ (design / sigma[:, None])
        covariance = np.linalg.inv(normal) * chi2
        errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    except np.linalg.LinAlgError:
        covariance = None
        errors = np.full(coefficients.size, np.nan)
    return Dispersion(coefficients, errors, int(order), kf, ef, sigma, model,
                      chi2, "x" if k_error is not None else "y", covariance)


def line_crossing(first: Dispersion, second: Dispersion):
    """Where two straight branches meet -- the Dirac point of a cone fitted
    as its two linear sides: ``(k, E, k_error, E_error)``.

    The errors propagate each line's coefficient covariance (the two fits
    are independent); a pair that is parallel within its errors has no
    crossing and gives NaN.
    """
    if first.order != 1 or second.order != 1:
        raise ValueError("the crossing is of two straight lines (order 1)")
    a1, b1 = (float(v) for v in first.coefficients)
    a2, b2 = (float(v) for v in second.coefficients)
    if abs(a1 - a2) < 1e-12:
        return (float("nan"),) * 4
    k = (b2 - b1) / (a1 - a2)
    energy = a1 * k + b1
    # derivatives of (k, E) with respect to (a1, b1, a2, b2)
    dk = np.array([-k, -1.0, k, 1.0]) / (a1 - a2)
    dE = np.array([k, 1.0, 0.0, 0.0]) + a1 * dk
    covariance = np.zeros((4, 4))
    for offset, fit in ((0, first), (2, second)):
        if fit.covariance is not None:
            covariance[offset:offset + 2, offset:offset + 2] = fit.covariance
        else:
            covariance[offset:offset + 2, offset:offset + 2] = np.diag(
                np.asarray(fit.errors, float) ** 2)
    k_error = float(np.sqrt(max(dk @ covariance @ dk, 0.0)))
    e_error = float(np.sqrt(max(dE @ covariance @ dE, 0.0)))
    return float(k), float(energy), k_error, e_error


@dataclass
class WindowScan:
    """How a velocity or a mass moves with the fitting window."""
    widths: np.ndarray
    values: np.ndarray
    errors: np.ndarray
    counts: np.ndarray
    quantity: str = "velocity"
    axis: str = "energy"
    centre: float = 0.0

    def plateau(self, tolerance: float = 0.05):
        """How far the window can be opened before the answer moves, as
        ``(first, last)`` indices into :attr:`widths`.

        Anchored at the **narrowest** window and extended outwards, not
        taken as the longest flat run anywhere in the scan. Both a velocity
        and a mass are local quantities -- defined at E_F and at the band
        extremum -- so the window that matters is the one closest to that
        point. Searching for the longest flat run instead finds the
        asymptote at large windows, which on a kinked band is a different
        velocity entirely and is not the one being asked for.

        A window leaves the plateau when it differs from the running median
        by more than ``tolerance`` **and** by more than ``n_sigma`` of its
        own error. Both halves are needed. The narrowest windows hold only a
        dozen points, so their velocities scatter by ten percent on noise
        alone and a bare relative test declares the plateau over
        immediately, even on a perfectly straight band; the widest hold
        hundreds, so their errors shrink to nothing and a bare statistical
        test finds a plateau nowhere.

        Returns None when even the two narrowest windows disagree, which is
        a real answer: it means the scan says nothing and a number should
        not be quoted from it.
        """
        return self._plateau(tolerance)

    def _plateau(self, tolerance: float, n_sigma: float = 2.0):
        finite = np.flatnonzero(np.isfinite(self.values))
        if finite.size < 2:
            return None
        start = int(finite[0])
        last = start
        for index in finite[1:]:
            index = int(index)
            block = self.values[start:index + 1]
            block = block[np.isfinite(block)]
            middle = float(np.median(block))
            if middle == 0:
                break
            deviation = abs(self.values[index] - middle)
            error = self.errors[index]
            allowed = tolerance * abs(middle)
            if np.isfinite(error):
                allowed = max(allowed, n_sigma * float(error))
            if deviation > allowed:
                break
            last = index
        return (start, last) if last > start else None

    def plateau_value(self, tolerance: float = 0.05):
        """``(value, error, widest_window)`` over the anchored plateau, or
        None. The error is the smallest on the plateau -- the widest window
        that is still honest -- rather than a combination that would pretend
        the windows were independent measurements."""
        found = self.plateau(tolerance)
        if found is None:
            return None
        first, last = found
        block = slice(first, last + 1)
        values = self.values[block]
        errors = self.errors[block]
        best = int(np.nanargmin(errors)) if np.isfinite(errors).any() else 0
        return float(values[best]), float(errors[best]), float(self.widths[last])


def window_scan(k, energy, *, k_error=None, energy_error=None,
                quantity: str = "velocity", centre: float = 0.0,
                widths=None, order: int = None, minimum: int = 5) -> WindowScan:
    """Refit over a family of windows and report how the answer moves.

    ``quantity`` is ``"velocity"`` -- a straight line over an energy window
    around ``centre`` (E_F) -- or ``"mass"``, a parabola over a momentum
    window around ``centre`` (the band extremum). The point is not to
    automate the choice of window but to show what it costs: a band with a
    kink gives a velocity that walks steadily with the window and no
    plateau, and that is a result about the band, not a failure of the fit.
    """
    k = np.asarray(k, dtype=float)
    energy = np.asarray(energy, dtype=float)
    if quantity == "velocity":
        axis, order = energy, 1 if order is None else order
        axis_name = "energy"
    elif quantity == "mass":
        axis, order = k, 2 if order is None else order
        axis_name = "momentum"
    else:
        raise ValueError(f"quantity {quantity!r} is not velocity or mass")

    if widths is None:
        reach = float(np.nanmax(np.abs(axis - centre)))
        widths = np.linspace(reach / 8.0, reach, 16)
    widths = np.asarray(widths, dtype=float)

    values, errors, counts = [], [], []
    for width in widths:
        inside = np.abs(axis - float(centre)) <= width
        if inside.sum() < max(order + 1, minimum):
            values.append(np.nan)
            errors.append(np.nan)
            counts.append(int(inside.sum()))
            continue
        try:
            fit = fit_dispersion(
                k[inside], energy[inside],
                k_error=None if k_error is None else np.asarray(k_error)[inside],
                energy_error=None if energy_error is None
                else np.asarray(energy_error)[inside],
                order=order)
            if quantity == "velocity":
                value, error = fit.fermi_velocity(
                    float(np.interp(centre, fit.energy[np.argsort(fit.energy)],
                                    fit.k[np.argsort(fit.energy)]))
                    if fit.energy.size > 1 else None)
            else:
                value, error = fit.effective_mass()
        except Exception:
            value, error = np.nan, np.nan
        values.append(value)
        errors.append(error)
        counts.append(int(inside.sum()))
    return WindowScan(widths, np.array(values), np.array(errors),
                      np.array(counts), quantity, axis_name, float(centre))


# ==========================================================================
# Self-energy
# ==========================================================================
#: hbar in eV*fs, for a lifetime from Im Sigma.
HBAR_EVFS = HBAR_EVS * 1e15


@dataclass
class SelfEnergy:
    """``Re Sigma`` and ``Im Sigma`` from an MDC series and a bare band.

    Signs, stated once: ``real`` is ``E - eps_bare(k)``, positive below E_F
    for a band that an interaction has flattened; ``imaginary`` is the
    magnitude ``|Im Sigma|`` (half the energy width of the quasiparticle),
    never negative. ``energy`` is as the cut has it; ``ef`` is where E_F is
    on that axis (0 for a cut on E - E_F).
    """
    energy: np.ndarray
    real: np.ndarray
    real_error: np.ndarray
    imaginary: np.ndarray
    imaginary_error: np.ndarray
    bare: Dispersion = None
    kk_real: np.ndarray = None
    k: np.ndarray = None                 # the fitted MDC centres
    width: np.ndarray = None             # their FWHM, resolution removed
    ef: float = 0.0
    k_f: float = float("nan")            # measured crossing of E_F
    v_f: float = float("nan")            # measured dE/dk there (eV*A)

    def consistency(self) -> float:
        """RMS difference between ``Re Sigma`` and the Kramers-Kronig
        transform of ``Im Sigma``, relative to the size of ``Re Sigma``.

        The two are not independent, so this is the check that decides
        whether the bare band was a defensible choice: one picked to make a
        kink look bigger fails it.
        """
        if self.kk_real is None:
            return float("nan")
        good = np.isfinite(self.kk_real) & np.isfinite(self.real)
        if not good.any():
            return float("nan")
        scale = float(np.sqrt(np.mean(self.real[good] ** 2))) or 1.0
        return float(np.sqrt(np.mean((self.kk_real[good] - self.real[good]) ** 2))
                     / scale)

    # -- what is read off the two curves ------------------------------------
    def _smooth_real(self, points: int = 5):
        """``Re Sigma`` in energy order, as a running weighted mean."""
        order = np.argsort(self.energy)
        e, re_ = self.energy[order], self.real[order]
        good = np.isfinite(re_)
        e, re_ = e[good], re_[good]
        if re_.size < points:
            return e, re_
        kernel = np.ones(points) / points
        padded = np.concatenate([np.full(points // 2, re_[0]), re_,
                                 np.full(points // 2, re_[-1])])
        return e, np.convolve(padded, kernel, mode="valid")

    def kink(self):
        """``(energy, Re Sigma there, inside)``: where ``|Re Sigma|`` is
        largest -- the energy of the mode the electrons couple to, for a
        kink. ``inside`` is False when that is the first or last point of
        the fitted range: then the range shows no maximum, and the number
        is the edge of the fit, not a kink."""
        e, re_ = self._smooth_real()
        if re_.size < 3:
            return float("nan"), float("nan"), False
        index = int(np.argmax(np.abs(re_)))
        inside = 1 <= index <= re_.size - 2
        return float(e[index]), float(re_[index]), bool(inside)

    def _near_ef(self, window: float = None):
        """The points within ``window`` of E_F; by default out to half the
        kink energy (the part where Re Sigma is a straight line), or the
        nearest third of the range when there is no kink."""
        distance = np.abs(self.energy - self.ef)
        if window is None:
            kink_e, _value, inside = self.kink()
            reach = float(np.nanmax(distance)) if distance.size else 0.0
            window = (0.5 * abs(kink_e - self.ef) if inside else reach / 3.0)
            closest = np.sort(distance[np.isfinite(distance)])
            if closest.size >= 4:                 # never fewer than 4 points
                window = max(window, float(closest[3]))
        return distance <= float(window), float(window)

    def coupling(self, window: float = None):
        """``(lambda, error, window)``: the coupling strength
        ``-d Re Sigma / dE`` at E_F, from a weighted straight line through
        the points within ``window`` of E_F. ``1 + lambda`` is the mass
        enhancement ``v_bare / v_F``."""
        take, window = self._near_ef(window)
        take &= np.isfinite(self.real)
        if take.sum() < 3:
            return float("nan"), float("nan"), window
        sigma = np.asarray(self.real_error, dtype=float)[take]
        fit = fit_dispersion(self.energy[take] - self.ef, self.real[take],
                             energy_error=sigma if np.all(
                                 np.isfinite(sigma) & (sigma > 0)) else None,
                             order=1)
        return -float(fit.coefficients[0]), float(fit.errors[0]), window

    def imaginary_at_ef(self, window: float = None):
        """``(|Im Sigma| at E_F, error)``, a straight line through the
        points near E_F read at E_F. What is left there at low temperature
        is scattering by defects (and whatever resolution was not
        removed), not the interaction."""
        take, _window = self._near_ef(window)
        take &= np.isfinite(self.imaginary)
        if take.sum() < 3:
            return float("nan"), float("nan")
        sigma = np.asarray(self.imaginary_error, dtype=float)[take]
        fit = fit_dispersion(self.energy[take] - self.ef, self.imaginary[take],
                             energy_error=sigma if np.all(
                                 np.isfinite(sigma) & (sigma > 0)) else None,
                             order=1)
        return float(fit.coefficients[1]), float(fit.errors[1])

    def mean_free_path(self, window: float = None):
        """``(l, error)`` in A: one over the MDC's FWHM at E_F."""
        if self.width is None:
            return float("nan"), float("nan")
        take, _window = self._near_ef(window)
        take &= np.isfinite(self.width) & (self.width > 0)
        if take.sum() < 3:
            return float("nan"), float("nan")
        fit = fit_dispersion(self.energy[take] - self.ef, self.width[take],
                             order=1)
        width, error = float(fit.coefficients[1]), float(fit.errors[1])
        if width <= 0:
            return float("nan"), float("nan")
        return 1.0 / width, error / width ** 2

    def lifetime_fs(self, window: float = None):
        """``(tau, error)`` in fs at E_F: ``hbar / (2 |Im Sigma|)``."""
        value, error = self.imaginary_at_ef(window)
        if not np.isfinite(value) or value <= 0:
            return float("nan"), float("nan")
        tau = HBAR_EVFS / (2.0 * value)
        return tau, tau * abs(error / value)

    def summary(self) -> list:
        """What the two curves say, as lines of text."""
        lines = []
        if self.bare is not None and np.isfinite(self.k_f):
            v_bare = float(self.bare.slope(self.k_f))
            lines.append(f"bare band: dE/dk = {v_bare:.4g} eV·Å at "
                         f"k_F = {self.k_f:.4g} Å⁻¹; measured "
                         f"v_F = {self.v_f:.4g} eV·Å, so "
                         f"v_bare/v_F − 1 = {v_bare / self.v_f - 1.0:.3g}")
        lam, lam_error, window = self.coupling()
        if np.isfinite(lam):
            lines.append(f"λ = −dReΣ/dE at E_F = {lam:.3g} ± {lam_error:.2g} "
                         f"(points within {1e3 * window:.0f} meV of E_F)")
        kink_e, kink_value, inside = self.kink()
        if np.isfinite(kink_e):
            if inside:
                lines.append(f"|Re Σ| is largest ({1e3 * kink_value:.3g} meV) "
                             f"at E − E_F = {1e3 * (kink_e - self.ef):.0f} meV")
            else:
                lines.append("Re Σ has no maximum inside the fitted range "
                             "(no kink is seen in it)")
        im0, im0_error = self.imaginary_at_ef()
        if np.isfinite(im0):
            text = (f"|Im Σ| at E_F = {1e3 * im0:.3g} ± "
                    f"{1e3 * im0_error:.2g} meV")
            tau, tau_error = self.lifetime_fs()
            if np.isfinite(tau):
                text += f", lifetime ħ/2|Im Σ| = {tau:.3g} ± {tau_error:.2g} fs"
            path, path_error = self.mean_free_path()
            if np.isfinite(path):
                text += f", mean free path 1/Δk = {path:.3g} ± {path_error:.2g} Å"
            lines.append(text)
        return lines


def kramers_kronig(energy, imaginary, *, ef: float = 0.0, tail: bool = True):
    """``Re Sigma`` from ``|Im Sigma|`` by the principal-value integral,
    in the convention of :class:`SelfEnergy` (``Re Sigma`` positive below
    E_F where ``|Im Sigma|`` rises away from E_F).

    The integral runs over all energies and the measurement covers the
    occupied side only, over a few hundred meV. Three things are assumed,
    and they are the usual ones:

    * ``|Im Sigma|`` is the same at ``E_F + x`` and ``E_F - x``
      (particle-hole symmetry), which makes ``Re Sigma`` zero at E_F. A
      point measured on both sides keeps its measured value;
    * between E_F and the first fitted energy it stays at that energy's
      value;
    * beyond the last fitted energy it stays at the last value (``tail``;
      without it, it drops to zero there, which puts a logarithmic spike
      at the end of the range).

    A constant ``|Im Sigma|`` (defect scattering) therefore gives no
    ``Re Sigma`` at all, as it must. The integral is done exactly for the
    straight lines between the points, so the spacing may be uneven and
    there is no error from the pole.
    """
    energy = np.asarray(energy, dtype=float)
    imaginary = np.asarray(imaginary, dtype=float)
    result = np.full(energy.shape, np.nan)
    good = np.isfinite(energy) & np.isfinite(imaginary)
    if good.sum() < 2:
        return result
    x, g = energy[good] - float(ef), imaginary[good]
    x, first = np.unique(x, return_index=True)
    g = g[first]
    # the other side of E_F, where it was not measured
    mirror = (-x < x[0]) | (-x > x[-1])
    nodes = np.concatenate([x, -x[mirror]])
    values = np.concatenate([g, g[mirror]])
    order = np.argsort(nodes)
    nodes, values = nodes[order], values[order]

    a, b = nodes[:-1], nodes[1:]
    slope = (values[1:] - values[:-1]) / (b - a)
    w = x[:, None]                                  # where it is evaluated
    at_w = values[:-1][None, :] + slope[None, :] * (w - a[None, :])

    def log_distance(edge):
        distance = np.abs(edge[None, :] - w)
        # the point itself: the two segments that meet there cancel
        return np.where(distance > 0, np.log(np.where(distance > 0,
                                                      distance, 1.0)), 0.0)

    integral = np.sum(slope[None, :] * (b - a)[None, :]
                      + at_w * (log_distance(b) - log_distance(a)), axis=1)
    if tail:
        left = np.abs(nodes[0] - x)
        right = np.abs(nodes[-1] - x)
        with np.errstate(divide="ignore"):
            integral += (np.where(left > 0, values[0] * np.log(left), 0.0)
                         - np.where(right > 0, values[-1] * np.log(right), 0.0))
        if values[0] != values[-1]:
            # two different tails: the difference is a constant that no
            # finite range fixes; put E_F at zero instead
            centre = np.interp(0.0, x, integral) if x[0] <= 0 <= x[-1] else 0.0
            integral = integral - centre
    out = -integral / np.pi
    placed = np.full(int(good.sum()), np.nan)
    placed[:] = np.interp(energy[good] - float(ef), x, out)
    result[good] = placed
    return result


def fermi_crossing(k, energy, *, k_error=None, ef: float = 0.0,
                   points: int = 7):
    """``(k_F, v_F, k_F error, v_F error)``: where the measured band
    crosses E_F and its slope there, from a straight line through the
    ``points`` fitted positions nearest E_F (so a band fitted only up to a
    few meV below E_F is carried the last step, not clipped)."""
    k = np.asarray(k, dtype=float)
    energy = np.asarray(energy, dtype=float)
    good = np.isfinite(k) & np.isfinite(energy)
    if good.sum() < 3:
        raise ValueError("need at least 3 fitted positions near E_F")
    index = np.flatnonzero(good)
    nearest = index[np.argsort(np.abs(energy[index] - ef))[:max(3, int(points))]]
    errors = None
    if k_error is not None:
        errors = np.asarray(k_error, dtype=float)[nearest]
        if not np.all(np.isfinite(errors) & (errors > 0)):
            errors = None
    # k(E) is what an MDC fit measures: fit it that way round
    line = fit_dispersion(energy[nearest] - ef, k[nearest],
                          energy_error=errors, order=1)
    dk_de, k_f = (float(v) for v in line.coefficients)
    if abs(dk_de) < 1e-30:
        raise ValueError("the band does not disperse near E_F")
    v_f = 1.0 / dk_de
    return (k_f, v_f, float(line.errors[1]),
            abs(v_f) * abs(float(line.errors[0]) / dk_de))


def bare_band_line(k_f: float, velocity: float, *, ef: float = 0.0) -> Dispersion:
    """A straight bare band through ``(k_F, E_F)`` with slope ``velocity``
    (eV*A) -- from a calculation, or from :func:`suggest_bare_velocity`."""
    coefficients = np.array([float(velocity), float(ef) - float(velocity) * float(k_f)])
    point = np.array([float(k_f)])
    return Dispersion(coefficients, np.zeros(2), 1, point,
                      np.array([float(ef)]), np.ones(1), np.array([float(ef)]),
                      float("nan"), "x", np.zeros((2, 2)))


def self_energy(series, bare: Dispersion, *, band: int = 0,
                resolution: float = 0.0, ef: float = 0.0,
                tail: bool = True) -> SelfEnergy:
    """Extract the self-energy from a fitted MDC series and a bare band.

    ``Re Sigma(E) = E - eps_bare(k(E))`` and
    ``|Im Sigma(E)| = (1/2) dk(E) |v_bare|``, with ``dk`` the fitted FWHM
    and ``v_bare`` the bare band's slope at the fitted k. ``resolution``
    (the momentum resolution, FWHM in A^-1) is removed from ``dk`` in
    quadrature when it was not already folded into the peak shape; when it
    was, pass 0 and do not remove it twice. ``ef`` is E_F on the cut's
    energy axis.

    ``kk_real`` is :func:`kramers_kronig` of ``|Im Sigma|``: no constant is
    fitted to it, so comparing it with ``Re Sigma`` tests the bare band.
    """
    if getattr(series, "direction", "mdc") != "mdc":
        raise ValueError("a self-energy comes from MDC widths: refit as MDCs")
    centres = np.asarray(series.centres, dtype=float)
    good = np.isfinite(centres[:, band]) & np.isfinite(series.positions)
    k = centres[good, band]
    e = np.asarray(series.positions, dtype=float)[good]
    k_error = np.asarray(series.centre_errors, dtype=float)[good, band]
    widths = np.asarray(series.widths, dtype=float)[good, band]
    width_error = np.asarray(series.width_errors, dtype=float)[good, band]

    if resolution > 0:
        widths = np.sqrt(np.maximum(widths ** 2 - float(resolution) ** 2, 0.0))

    velocity = np.abs(bare.slope(k))
    real = e - bare.value(k)
    real_error = velocity * k_error
    imaginary = 0.5 * widths * velocity
    imaginary_error = 0.5 * velocity * width_error

    kk = kramers_kronig(e, imaginary, ef=ef, tail=tail)
    result = SelfEnergy(e, real, real_error, imaginary, imaginary_error, bare,
                        kk, k, widths, float(ef))
    # The measured crossing: k_F from the few points nearest E_F (it must
    # not be pulled by the band's bend further down), the slope over the
    # same straight part near E_F that the coupling is read from (seven
    # points alone give a noisy slope).
    try:
        result.k_f, result.v_f, _dk, _dv = fermi_crossing(
            k, e, k_error=k_error, ef=ef)
        near, _window = result._near_ef()
        if near.sum() > 7:
            _kf, result.v_f, _dk, _dv = fermi_crossing(
                k, e, k_error=k_error, ef=ef, points=int(near.sum()))
    except (ValueError, np.linalg.LinAlgError):
        pass
    return result


def suggest_bare_velocity(series, *, band: int = 0, resolution: float = 0.0,
                          ef: float = 0.0, factors=(1.0, 6.0)):
    """The straight bare band through the measured ``k_F`` whose
    ``Re Sigma`` agrees best with the Kramers-Kronig transform of its own
    ``Im Sigma``: ``(velocity, mismatch, k_F, v_F)``.

    Both curves depend on the one unknown, the bare velocity: ``Re Sigma``
    is the distance of the measured band from the bare line, and
    ``Im Sigma`` is the measured width times that velocity. Requiring them
    to be a Kramers-Kronig pair fixes it, with nothing taken from a
    calculation. It rests on what :func:`kramers_kronig` assumes outside
    the fitted range, so the fitted range should reach well past the kink
    (to where ``Im Sigma`` has levelled off): on a range that stops at the
    kink the answer is not to be trusted. ``factors`` is the range searched,
    in units of the measured v_F.
    """
    from scipy import optimize
    centres = np.asarray(series.centres, dtype=float)[:, band]
    positions = np.asarray(series.positions, dtype=float)
    errors = np.asarray(series.centre_errors, dtype=float)[:, band]
    k_f, v_f, _dk, _dv = fermi_crossing(centres, positions, k_error=errors, ef=ef)
    def mismatch(factor):
        result = self_energy(series, bare_band_line(k_f, factor * v_f, ef=ef),
                             band=band, resolution=resolution, ef=ef)
        good = np.isfinite(result.real) & np.isfinite(result.kk_real)
        if good.sum() < 3:
            return np.inf
        return float(np.sqrt(np.mean((result.real[good]
                                      - result.kk_real[good]) ** 2)))

    grid = np.linspace(float(factors[0]), float(factors[1]), 41)
    scores = np.array([mismatch(f) for f in grid])
    best = int(np.argmin(scores))
    lo, hi = grid[max(best - 1, 0)], grid[min(best + 1, grid.size - 1)]
    found = optimize.minimize_scalar(mismatch, bounds=(lo, hi), method="bounded")
    factor = float(found.x) if found.fun <= scores[best] else float(grid[best])
    result = self_energy(series, bare_band_line(k_f, factor * v_f, ef=ef),
                         band=band, resolution=resolution, ef=ef)
    return factor * v_f, result.consistency(), k_f, v_f


def bare_band_from_anchors(k, energy, anchors, *, order: int = 1,
                           average: int = 5) -> Dispersion:
    """A bare band through chosen anchor points.

    The bare band is an assumption, not a measurement, and the usual way to
    state it is "a straight line through the dispersion far from the kink
    and through E_F". ``anchors`` is a list of energies; the measured k at
    each is read off a straight line through the ``average`` fitted
    positions nearest to it (one noisy point does not tilt the bare band,
    and an anchor at E_F, just beyond the last fitted energy, is reached
    by that line rather than clipped to the last point), and a polynomial
    is put through those points. Keeping it explicit means the assumption
    is recorded rather than buried in whichever range happened to be fitted.
    """
    k = np.asarray(k, dtype=float)
    energy = np.asarray(energy, dtype=float)
    good = np.isfinite(k) & np.isfinite(energy)
    k, energy = k[good], energy[good]
    picked_k, picked_e = [], []
    for anchor in anchors:
        nearest = np.argsort(np.abs(energy - float(anchor)))[:max(2, int(average))]
        if nearest.size < 2 or np.ptp(energy[nearest]) == 0:
            raise ValueError("not enough fitted positions near the anchor "
                             f"at {float(anchor):.4g}")
        slope, offset = np.polyfit(energy[nearest] - float(anchor), k[nearest], 1)
        picked_k.append(float(offset))
        picked_e.append(float(anchor))
    if len(picked_k) < order + 1:
        raise ValueError(f"need at least {order + 1} anchors for that order")
    return fit_dispersion(np.array(picked_k), np.array(picked_e), order=order)
