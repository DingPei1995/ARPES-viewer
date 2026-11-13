"""
tools/spectra/fermi.py
======================
Fermi-edge fitting, as plain numpy/scipy with no Qt -- the same split as
``tools.momentum.kspace`` and ``tools.processing.analysis``.

Model (all in eV, energies as the axis carries them):

    I(E) = [ (a0 + a1*(E-EF)) * f(E; EF, T) + (b0 + b1*(E-EF)) ] (*) G(FWHM)

    f(E) = 1 / (exp((E-EF)/kT) + 1)

so the occupied density of states is a straight line through EF, the
background (dark counts, secondaries, higher-order light) is a straight line
that is *not* multiplied by the occupation, and the whole thing is smeared
by the analyser's Gaussian resolution.

How it is fitted, and why:

- **The convolution is a quadrature, not a padded grid.** Integrating
  ``m(E - t) G(t) dt`` at each requested energy needs no extended uniform
  grid, so the axis can be uneven or descending and no bin can slip.
  (Gauss-Hermite quadrature would be the elegant version and is what this
  module first tried, but it under-resolves the edge whenever kT is small
  compared with the resolution -- exactly the nano-ARPES case -- so the
  integral is taken on a fine grid whose step follows the *narrower* of the
  two widths.)
- **Poisson weighting.** Counts have variance ~ counts, so an unweighted
  least squares over-weights the occupied side. This biases the width, and
  the width is the whole point.
- **Uncertainties.** ``least_squares`` gives a Jacobian, so every parameter
  comes back with an error bar and the fit with a reduced chi-squared.
- **T and the resolution are degenerate** on a single edge: the measured
  width is roughly sqrt((3.53 kT)^2 + FWHM^2), so fitting both freely gives
  two numbers neither of which means anything on its own. The temperature
  is therefore *held* by default (the cryostat reading is in the file), and
  when both are free the fit reports their correlation so the degeneracy is
  visible rather than silent.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

try:
    from scipy.optimize import least_squares
    from scipy.special import expit, ndtr
except ImportError as exc:      # pragma: no cover - scipy is a hard dependency
    raise ImportError("arpes_viewer.tools.spectra.fermi needs scipy") from exc


#: Boltzmann's constant in eV/K.
K_B = 8.617333262e-5
#: FWHM = SIGMA_TO_FWHM * sigma for a Gaussian.
SIGMA_TO_FWHM = 2.0 * np.sqrt(2.0 * np.log(2.0))
#: The parameters of the model, in the order the fitter uses.
PARAMETERS = ("ef", "temperature", "resolution", "dos0", "dos1", "bkg0", "bkg1")
#: How each one is labelled in the interface, with its unit.
PARAMETER_LABELS = {
    "ef": "E_F (eV)",
    "temperature": "Temperature (K)",
    "resolution": "Resolution FWHM (eV)",
    "dos0": "DOS at E_F",
    "dos1": "DOS slope (/eV)",
    "bkg0": "Background",
    "bkg1": "Background slope (/eV)",
}


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------
def fermi_function(energy, ef: float, temperature: float) -> np.ndarray:
    """Fermi-Dirac occupation. ``expit(-x)`` rather than ``1/(exp(x)+1)``:
    same function, but it does not overflow when the exponent is large."""
    energy = np.asarray(energy, dtype=float)
    kt = K_B * max(float(temperature), 1e-6)
    return expit(-(energy - float(ef)) / kt)


def _unbroadened(energy, ef, temperature, dos0, dos1, bkg0, bkg1):
    shifted = np.asarray(energy, dtype=float) - float(ef)
    return ((dos0 + dos1 * shifted) * fermi_function(energy, ef, temperature)
            + bkg0 + bkg1 * shifted)


def _convolution_offsets(sigma: float, kt: float, n_sigma: float = 6.0,
                         max_points: int = 1201):
    """Offsets and weights for integrating against a Gaussian of width
    ``sigma``.

    The step follows the *narrower* of the two scales in the problem -- the
    resolution and the thermal width -- because a step tuned to the
    resolution alone walks straight over a cold Fermi edge.
    """
    scale = min(sigma, kt) if kt > 0 else sigma
    step = max(scale / 6.0, 2.0 * n_sigma * sigma / (max_points - 1))
    half = int(np.ceil(n_sigma * sigma / step))
    offsets = np.arange(-half, half + 1) * step
    weights = np.exp(-0.5 * (offsets / sigma) ** 2)
    return offsets, weights / weights.sum()


def fermi_edge_model(energy, ef: float, temperature: float, resolution: float,
                     dos0: float, dos1: float = 0.0, bkg0: float = 0.0,
                     bkg1: float = 0.0) -> np.ndarray:
    """The full model above, evaluated at ``energy`` (any order, any
    spacing). ``resolution`` is the Gaussian **FWHM**.

    The convolution is done by parts, so that only the *narrow* function is
    ever sampled: the Gaussian against the linear DOS has a closed form
    (``K`` below, with the error function), and what is left is an average
    of it over the derivative of the Fermi function, a bell of width kT,
    sampled on a few dozen points. Sampling the Gaussian instead, finely
    enough for a cold edge, took a thousand points whenever the resolution
    was much wider than kT (soft X-rays: hundreds of meV against 2.6 meV at
    30 K) -- a thousand times the work on every evaluation, and a
    channel-by-channel fit that ran for minutes.
    """
    energy = np.asarray(energy, dtype=float)
    sigma = float(resolution) / SIGMA_TO_FWHM
    if not np.isfinite(sigma) or sigma <= 0:
        return _unbroadened(energy, ef, temperature, dos0, dos1, bkg0, bkg1)
    kt = K_B * max(float(temperature), 1e-6)
    offsets, weights = _thermal_offsets(kt, sigma)
    # z = (E' - E) / sigma, E' = ef + t: the Gaussian's argument at each
    # point of the thermal bell, for each energy
    shifted = energy - float(ef)
    z = (offsets[None, :] - shifted[:, None]) / sigma
    cdf = ndtr(z)
    pdf = np.exp(-0.5 * z * z) / np.sqrt(2.0 * np.pi)
    # K(E') = int_{-inf}^{E'} G(E - u) (dos0 + dos1 (u - ef)) du
    k = (dos0 + dos1 * shifted[:, None]) * cdf - dos1 * sigma * pdf
    return k @ weights + bkg0 + bkg1 * shifted


def _thermal_offsets(kt: float, sigma: float, n_kt: float = 14.0,
                     max_points: int = 801):
    """Points and weights for averaging over the Fermi function's
    derivative (``-dF/dE``, a bell of width ``kt``): spaced at a quarter of
    the narrower of kT and the resolution, over +/- ``n_kt`` kT."""
    step = max(min(kt, sigma) / 4.0, 2.0 * n_kt * kt / (max_points - 1))
    half = max(int(np.ceil(n_kt * kt / step)), 10)
    offsets = np.arange(-half, half + 1) * step
    x = offsets / kt
    weights = expit(x) * expit(-x)
    return offsets, weights / weights.sum()


def broadened_fermi(energy, ef: float, temperature: float,
                    resolution: float) -> np.ndarray:
    """Just the occupation, resolution-broadened and normalised to 1 well
    below E_F. This -- not the whole model -- is what dividing a spectrum by
    the Fermi cut-off should divide by."""
    return fermi_edge_model(energy, ef, temperature, resolution,
                            dos0=1.0, dos1=0.0, bkg0=0.0, bkg1=0.0)


# --------------------------------------------------------------------------
# Starting values
# --------------------------------------------------------------------------
def _smooth(values: np.ndarray, width: int) -> np.ndarray:
    """Moving average, the ends padded with the end values -- padding with
    zeros (``np.convolve(..., "same")``) makes every spectrum fall at its
    high-energy end, which the steepest-fall guess then took for the
    Fermi edge."""
    width = max(3, int(width) | 1)
    if values.size < width:
        return values
    kernel = np.ones(width) / width
    padded = np.pad(values, width // 2, mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def initial_guess(energy, intensity, temperature: float = 30.0) -> dict:
    """Starting values read off the data itself, so nothing has to be typed.

    E_F is the steepest fall of the smoothed spectrum; the background and
    the density of states are the levels well above and well below it; the
    resolution comes from the 16-84 % width of the edge with the thermal
    part taken out in quadrature (an edge is 3.32 kT wide between those two
    levels, a Gaussian 2 sigma, and the two add in quadrature).
    """
    energy = np.asarray(energy, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    order = np.argsort(energy)
    e, i = energy[order], intensity[order]
    finite = np.isfinite(i)
    if finite.sum() < 5:
        raise ValueError("not enough finite points to guess from")
    e, i = e[finite], i[finite]

    width = max(3, e.size // 50)
    smoothed = _smooth(i, width)
    # A noisy spectrum (the counts of one channel, or a weak edge) needs
    # more smoothing before its steepest fall means anything.
    noise = float(np.std(i - smoothed))
    if noise > 0 and float(np.ptp(smoothed)) / noise < 10:
        width = max(5, e.size // 10)
        smoothed = _smooth(i, width)
    slope = np.gradient(smoothed, e)
    # Only where the average is over the data alone: near the ends it leans
    # on the padding, and one noisy end point there looks like a cliff.
    margin = min(width // 2 + 1, max(0, (e.size - 3) // 2))
    inner = slope[margin:e.size - margin] if e.size - 2 * margin >= 3 else slope
    ef = float(e[int(np.argmin(inner)) + (margin if inner is not slope else 0)])

    kt = K_B * max(float(temperature), 1e-6)
    above = e > ef + 10 * kt
    below = e < ef - 10 * kt
    bkg0 = float(np.median(i[above])) if above.sum() > 2 else float(np.min(i))
    level = float(np.median(i[below])) if below.sum() > 2 else float(np.max(i))
    dos0 = max(level - bkg0, 1e-12)

    # 16-84 % width of the edge, minus the thermal part
    lo_target, hi_target = bkg0 + 0.16 * dos0, bkg0 + 0.84 * dos0
    crossings = []
    for target in (hi_target, lo_target):
        idx = np.argmin(np.abs(smoothed - target))
        crossings.append(float(e[idx]))
    width = abs(crossings[1] - crossings[0])
    thermal = 3.32 * kt
    sigma = np.sqrt(max(width ** 2 - thermal ** 2, 0.0)) / 2.0
    resolution = max(sigma * SIGMA_TO_FWHM, float(np.mean(np.diff(e))) if e.size > 1 else 1e-3)

    dos1 = 0.0
    if below.sum() > 3:                       # slope of the occupied states
        dos1 = float(np.polyfit(e[below] - ef, i[below] - bkg0, 1)[0])
    bkg1 = 0.0
    if above.sum() > 3:
        bkg1 = float(np.polyfit(e[above] - ef, i[above], 1)[0])

    return {"ef": ef, "temperature": float(temperature), "resolution": float(resolution),
            "dos0": dos0, "dos1": dos1, "bkg0": bkg0, "bkg1": bkg1}


def steepest_drop(energy, intensity) -> float:
    """Where the intensity falls fastest -- a starting E_F for a window
    that holds more than the edge.

    :func:`initial_guess` reads E_F off the half-height crossing, which is
    right for a window around the edge but can land at the window's top when
    a band rises just below E_F. The steepest *drop* of the lightly smoothed
    curve is where the edge is, whatever sits beside it. The two points at
    each end are left out, where the smoothing runs off the data.
    """
    e = np.asarray(energy, dtype=float)
    i = np.asarray(intensity, dtype=float)
    order = np.argsort(e)
    e, i = e[order], i[order]
    if e.size < 7:
        return float(e[e.size // 2])
    smooth = np.convolve(i, np.ones(3) / 3.0, mode="same")
    slope = np.gradient(smooth, e)
    slope[:2] = slope[-2:] = 0.0
    return float(e[int(np.argmin(slope))])


def edge_candidates(energy, intensity, *, smooth_points: int = 7,
                    half_window: float = 0.15, max_candidates: int = 4) -> list:
    """The drops in an EDC that could be the Fermi edge, highest energy
    first -- for choosing a fit window on data whose axis is not known yet.

    The steepest drop is not a safe answer: a band edge, or the strong drop
    of a pass-energy-20 spectrum below a weak tail, can be steeper than the
    edge itself. The Fermi edge is the *last* drop on the axis: after it the
    intensity stays at the floor (dark counts, second order). So every drop
    clearly above the noise is listed, each with

    * ``energy``: where the lightly smoothed curve falls fastest;
    * ``step``: the height of the drop over +-``half_window``/2, as a
      fraction of the curve's maximum;
    * ``after``: the level just above it, as a fraction of the maximum
      (near 0 for the Fermi edge);
    * ``window``: a fit window of +-``half_window`` around it, cut at the
      axis's ends;
    * ``highest``: True for the highest-energy drop -- the usual Fermi edge.

    Fit each with :func:`fit_fermi_edge` on its ``window``; when two
    candidates are both plausible (a weak tail above a strong drop), the
    data alone cannot decide which is E_F: compare with a reference (gold,
    another scan at the same photon and pass energy) or ask.
    """
    e = np.asarray(energy, dtype=float)
    y = np.asarray(intensity, dtype=float)
    keep = np.isfinite(e) & np.isfinite(y)
    e, y = e[keep], y[keep]
    order = np.argsort(e)
    e, y = e[order], y[order]
    if e.size < 9:
        return []
    width = max(3, int(smooth_points) | 1)
    smooth = _smooth(y, width)
    pad = width // 2
    smooth[:pad] = y[:pad]
    smooth[-pad:] = y[-pad:]
    residual = y - smooth
    top = float(np.max(smooth)) or 1.0
    slope = -np.gradient(smooth, e)
    slope[:pad] = slope[-pad:] = 0.0
    step_e = float(np.median(np.diff(e))) or 1e-3
    reach = max(2, int(round(0.5 * half_window / step_e)))
    merged = []
    for i in range(1, e.size - 1):
        lo, hi = max(0, i - reach), min(e.size - 1, i + reach)
        # the fastest fall within its own neighbourhood: one point per drop
        if slope[i] <= 0 or slope[i] < np.max(slope[lo:hi + 1]):
            continue
        step = float(smooth[lo] - smooth[hi])
        # the noise where the drop is (Poisson noise is far larger on the
        # strong signal below a weak edge than on the edge itself)
        noise = float(np.std(residual[max(pad, lo):min(e.size - pad, hi + 1)]))
        if step <= max(5.0 * noise, 0.01 * top):
            continue
        merged.append((i, step))
    merged.sort(key=lambda t: -e[t[0]])
    out = []
    for rank, (i, step) in enumerate(merged[:int(max_candidates)]):
        hi = min(e.size - 1, i + reach)
        out.append({"energy": float(e[i]),
                    "step": round(step / top, 4),
                    "after": round(float(smooth[hi]) / top, 4),
                    "window": [float(max(e[0], e[i] - half_window)),
                               float(min(e[-1], e[i] + half_window))],
                    "highest": rank == 0})
    return out


# --------------------------------------------------------------------------
# The fit
# --------------------------------------------------------------------------
@dataclass
class FermiFit:
    """What a fit produced: values, their uncertainties, and enough about
    the fit itself to judge whether to believe them."""
    values: dict
    errors: dict
    fixed: tuple = ()
    reduced_chi2: float = float("nan")
    correlation: dict = field(default_factory=dict)
    window: tuple = (None, None)
    n_points: int = 0
    success: bool = False
    message: str = ""

    def model(self, energy) -> np.ndarray:
        return fermi_edge_model(energy, **{k: self.values[k] for k in PARAMETERS})

    @property
    def thermal_width(self) -> float:
        """The 10-90 % width the temperature alone would give (eV)."""
        return 3.53 * K_B * self.values["temperature"]

    @property
    def combined_width(self) -> float:
        """Thermal and instrumental widths added in quadrature -- the width
        actually measured, and the only one determined when both are free."""
        return float(np.hypot(self.thermal_width, self.values["resolution"]))

    def summary(self) -> str:
        ef, def_ = self.values["ef"], self.errors.get("ef", float("nan"))
        res, dres = self.values["resolution"], self.errors.get("resolution", float("nan"))
        text = (f"E_F = {ef:.5g} ± {def_:.2g} eV\n"
                f"resolution (FWHM) = {res * 1000:.4g} ± {dres * 1000:.2g} meV\n"
                f"T = {self.values['temperature']:.4g} K"
                f"{' (held)' if 'temperature' in self.fixed else ''}, "
                f"thermal width {self.thermal_width * 1000:.3g} meV\n"
                f"reduced chi2 = {self.reduced_chi2:.4g} over {self.n_points} points")
        pair = self.correlation.get(("temperature", "resolution"))
        if pair is not None:
            text += (f"\ncorrelation(T, resolution) = {pair:+.2f}"
                     + ("  -- they are trading off; hold one of them"
                        if abs(pair) > 0.9 else ""))
        return text

    def problems(self) -> list:
        """Why this fit should not be believed, in words; empty if none.

        See :func:`edge_problems`."""
        return edge_problems(self)

    @property
    def found_edge(self) -> bool:
        """True if the fit found a Fermi edge rather than merely converged."""
        return not self.problems()


def edge_problems(fit, lo: float = None, hi: float = None,
                  margin: float = None) -> list:
    """Reasons a converged fit is not a Fermi edge; an empty list if none.

    ``fit_fermi_edge`` reports success on data with no edge in it at all --
    it is a least-squares fit, and a model with a step in it can describe
    featureless data by putting the step where it does no harm. That is
    what a self-normalised map gives (every spectrum divided by its own
    level, so the step from occupied to empty states is gone), and the
    number that comes back looks like an answer either way. Three things
    give it away, none of them a threshold tuned by hand:

    * **E_F is pinned to the end of the window.** On flat data the step
      slides off the fitted range and stops at its bound; a real edge sits
      inside the window with data on both sides.
    * **There is no step worth speaking of.** ``dos0``, the height of the
      step down, is positive and large next to its own error bar for an
      edge; featureless data fits about zero, and noise fits one going up.
    * **E_F is not determined.** An error on E_F larger than a quarter of
      the window means the window does not fix where the edge is.

    ``lo``/``hi`` default to the fit's own window and ``margin`` to two
    energy steps of it.
    """
    reasons = []
    w_lo, w_hi = fit.window if fit.window else (None, None)
    lo = w_lo if lo is None else lo
    hi = w_hi if hi is None else hi
    level = float(fit.values.get("ef", np.nan))
    if not np.isfinite(level):
        return ["E_F is not a number"]
    if lo is not None and hi is not None:
        span = float(hi) - float(lo)
        if margin is None:
            margin = 2.0 * span / max(int(fit.n_points) - 1, 1)
        if not (lo + margin <= level <= hi - margin):
            reasons.append(f"E_F = {level:.5g} eV is at the end of the fit "
                           f"window ({lo:.5g}..{hi:.5g} eV): no edge inside it")
        error = float(fit.errors.get("ef", np.nan))
        if np.isfinite(error) and span > 0 and error > 0.25 * span:
            reasons.append(f"E_F is not determined (± {error:.3g} eV over a "
                           f"{span:.3g} eV window)")
    step = float(fit.values.get("dos0", 0.0))
    step_error = float(fit.errors.get("dos0", float("nan")))
    if step <= 0.0:
        reasons.append("there is no step down at E_F in the data")
    elif np.isfinite(step_error) and step_error > 0.0 and step <= 2.0 * step_error:
        reasons.append(f"the step at E_F ({step:.3g}) is not larger than "
                       f"twice its error ({step_error:.3g})")
    if reasons:
        reasons.append("was the data normalised before the fit? Fit the raw "
                       "data, put it on E - E_F, then normalise")
    return reasons


def _weights(intensity: np.ndarray, weighting: str) -> np.ndarray:
    if weighting == "uniform":
        return np.ones_like(intensity)
    # Poisson: sigma = sqrt(counts), with a floor so empty channels do not
    # get infinite weight.
    floor = max(1.0, float(np.nanmax(intensity)) * 1e-6)
    return 1.0 / np.sqrt(np.maximum(intensity, floor))


def fit_fermi_edge(energy, intensity, *, start: dict = None,
                   fixed=("temperature",), temperature: float = 30.0,
                   window=(None, None), weighting: str = "poisson",
                   max_nfev: int = 2000) -> FermiFit:
    """Fit the model to one EDC.

    ``fixed`` names the parameters to hold at their starting values; the
    temperature is held by default, because on a single edge it cannot be
    separated from the resolution. ``window`` restricts the fit to an energy
    range, which keeps band structure far from E_F out of it.
    """
    energy = np.asarray(energy, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    if energy.shape != intensity.shape:
        raise ValueError("energy and intensity must have the same shape")

    keep = np.isfinite(energy) & np.isfinite(intensity)
    lo, hi = window
    if lo is not None:
        keep &= energy >= float(lo)
    if hi is not None:
        keep &= energy <= float(hi)
    e, i = energy[keep], intensity[keep]
    if e.size < 8:
        raise ValueError(f"only {e.size} points inside the fit window")

    start = dict(start or initial_guess(e, i, temperature=temperature))
    start.setdefault("temperature", temperature)
    fixed = tuple(name for name in fixed if name in PARAMETERS)
    free = [name for name in PARAMETERS if name not in fixed]
    if not free:
        raise ValueError("every parameter is held -- nothing to fit")

    span = float(np.ptp(e)) or 1.0
    step = float(np.mean(np.abs(np.diff(np.sort(e))))) if e.size > 1 else span / 100
    scale = float(np.nanmax(np.abs(i))) or 1.0
    limits = {
        "ef": (float(e.min()), float(e.max())),
        "temperature": (0.1, 2000.0),
        # A resolution finer than a fraction of the sampling cannot be seen,
        # and zero would divide by zero in the kernel.
        "resolution": (step / 10.0, span),
        "dos0": (-10 * scale, 10 * scale),
        "dos1": (-1e4 * scale / span, 1e4 * scale / span),
        "bkg0": (-10 * scale, 10 * scale),
        "bkg1": (-1e4 * scale / span, 1e4 * scale / span),
    }
    x0 = np.array([np.clip(start[name], *limits[name]) for name in free], dtype=float)
    lower = np.array([limits[name][0] for name in free])
    upper = np.array([limits[name][1] for name in free])
    weights = _weights(i, weighting)

    def residuals(x):
        values = dict(start)
        values.update(dict(zip(free, x)))
        model = fermi_edge_model(e, **{k: values[k] for k in PARAMETERS})
        return (model - i) * weights

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = least_squares(residuals, x0, bounds=(lower, upper),
                               x_scale="jac", max_nfev=max_nfev)

    values = dict(start)
    values.update(dict(zip(free, result.x)))

    # Uncertainties from the Jacobian, scaled by the fit's own scatter (the
    # convention curve_fit uses by default): trustworthy relative to each
    # other whether or not the absolute weights are right.
    dof = max(e.size - len(free), 1)
    chi2 = float(2 * result.cost)
    reduced = chi2 / dof
    errors = {name: float("nan") for name in PARAMETERS}
    correlation = {}
    try:
        _, s, vt = np.linalg.svd(result.jac, full_matrices=False)
        good = s > max(result.jac.shape) * np.finfo(float).eps * s[0]
        cov = (vt[good].T / s[good] ** 2) @ vt[good] * reduced
        for index, name in enumerate(free):
            errors[name] = float(np.sqrt(abs(cov[index, index])))
        for a in range(len(free)):
            for b in range(a + 1, len(free)):
                denom = np.sqrt(abs(cov[a, a] * cov[b, b]))
                if denom > 0:
                    correlation[(free[a], free[b])] = float(cov[a, b] / denom)
    except (np.linalg.LinAlgError, IndexError, ValueError):
        pass
    for name in fixed:
        errors[name] = 0.0

    return FermiFit(values=values, errors=errors, fixed=fixed,
                    reduced_chi2=reduced, correlation=correlation,
                    window=(float(e.min()), float(e.max())), n_points=int(e.size),
                    success=bool(result.success), message=str(result.message))


# --------------------------------------------------------------------------
# Channel by channel, for a Fermi-surface correction from a reference
# --------------------------------------------------------------------------
def measured_channels(frame, fraction: float = 0.05):
    """``slice`` of the channels of ``frame`` (angle first, energy last;
    any axes between are summed) that hold a measurement: the blank borders
    some detectors leave on either side of a cut -- channels that are all
    NaN, all zero, or nearly empty -- cut off.

    Only the two ends are trimmed: a weak channel in the middle is still a
    channel. "Nearly empty" is a total under ``fraction`` of the median
    total of the channels that have counts.
    """
    values = np.asarray(frame, dtype=float)
    if values.ndim < 2 or values.shape[0] == 0:
        return slice(0, values.shape[0] if values.ndim else 0)
    flat = values.reshape(values.shape[0], -1)
    finite = np.isfinite(flat).any(axis=1)
    totals = np.where(finite, np.nansum(np.abs(flat), axis=1), 0.0)
    positive = totals[totals > 0]
    if positive.size == 0:
        return slice(0, 0)
    measured = totals > float(fraction) * float(np.median(positive))
    first = int(np.argmax(measured))
    last = int(measured.size - np.argmax(measured[::-1]))
    return slice(first, last)


#: What a channel fit holding the seed's line shape keeps fixed: only E_F,
#: the height of the edge and the background level are fitted per channel.
SHAPE_HELD = ("temperature", "resolution", "dos1", "bkg1")


def fit_channels(angles, energy, frame, *, half_width: int = 0, step: int = 1,
                 temperature: float = 30.0, fixed=("temperature",),
                 window=(None, None), weighting: str = "poisson",
                 start: dict = None, progress=None, hold_shape: bool = False,
                 max_nfev: int = 300):
    """Fit the edge in every (Nth) detector channel of ``frame`` (angle,
    energy).

    ``half_width`` adds that many neighbouring channels on each side to the
    EDC before fitting -- the usual answer to a spectrum too thin to fit
    channel by channel. The channel's own position is unchanged; only its
    statistics improve. ``step`` fits only every Nth channel (with ``step``
    = 2 ``half_width`` + 1 the fits share no channel). See
    :func:`plan_channel_fit` for both, chosen from the data.

    ``start`` is where every fit starts -- the fit of the summed EDC (the
    seed). With ``hold_shape`` the seed's line shape is kept
    (:data:`SHAPE_HELD`: temperature, resolution, the slopes, scaled to the
    channel's counts) and only E_F, the edge's height and the background
    are fitted: on a noisy channel, the six-parameter fit wanders; three
    parameters it can still pin down.

    ``progress(done, total)`` is called after each fit; returning False
    stops, keeping what has been fitted.

    Returns ``(ef, ef_error, ok)``, all the length of ``angles``: the edge
    position per channel, its uncertainty, and whether that channel's fit is
    worth using (converged, E_F inside the fit window, and an uncertainty
    smaller than the resolution). Channels that were skipped or failed are
    NaN with ``ok`` false.
    """
    angles = np.asarray(angles, dtype=float)
    frame = np.asarray(frame, dtype=float)
    energy = np.asarray(energy, dtype=float)
    if frame.shape != (angles.size, energy.size):
        raise ValueError(f"frame {frame.shape} does not match "
                         f"({angles.size}, {energy.size})")

    half_width = max(0, int(half_width))
    ef = np.full(angles.size, np.nan)
    err = np.full(angles.size, np.nan)
    ok = np.zeros(angles.size, dtype=bool)
    guess = dict(start) if start else None
    lo_e = float(np.min(energy)) if window[0] is None else float(window[0])
    hi_e = float(np.max(energy)) if window[1] is None else float(window[1])
    inside_window = (energy >= lo_e) & (energy <= hi_e)
    held = tuple(fixed)
    seed_model = None
    if hold_shape and start:
        held = tuple(dict.fromkeys(tuple(fixed) + SHAPE_HELD))
        seed_model = fermi_edge_model(energy[inside_window],
                                      **{k: start[k] for k in PARAMETERS})

    wanted = list(range(min(half_width, angles.size - 1), angles.size,
                        max(1, int(step))))
    if wanted and wanted[-1] < angles.size - 1 - half_width:
        wanted.append(angles.size - 1 - half_width)   # reach the far end
    for count, index in enumerate(wanted):
        lo = max(0, index - half_width)
        hi = min(angles.size, index + half_width + 1)
        edc = np.nansum(frame[lo:hi], axis=0)
        begin = guess
        if seed_model is not None:
            # the seed's shape, scaled to this channel's counts
            total = float(np.nansum(seed_model))
            scale = float(np.nansum(edc[inside_window])) / total if total else 1.0
            begin = dict(start)
            for name in ("dos0", "dos1", "bkg0", "bkg1"):
                begin[name] = start[name] * scale
        try:
            fit = fit_fermi_edge(energy, edc, start=begin, fixed=held,
                                 temperature=temperature, window=window,
                                 weighting=weighting, max_nfev=max_nfev)
        except Exception:
            if progress is not None and progress(count + 1, len(wanted)) is False:
                break
            continue
        ef[index] = fit.values["ef"]
        err[index] = fit.errors.get("ef", np.nan)
        inside = lo_e < ef[index] < hi_e
        ok[index] = bool(fit.success and inside
                         and (not np.isfinite(err[index])
                              or err[index] < max(fit.values["resolution"], 1e-9)))
        if ok[index] and seed_model is None:
            # Walk along the detector: the next channel starts from this
            # one's answer, which is both faster and steadier than starting
            # every channel from scratch.
            guess = dict(fit.values)
        if progress is not None and progress(count + 1, len(wanted)) is False:
            break                           # the caller asked us to stop
    return ef, err, ok


def plan_channel_fit(angles, energy, frame, seed: dict, *, window=(None, None),
                     temperature: float = 30.0, target: float = None,
                     min_fits: int = 10, max_fits: int = 200,
                     trial_fits: int = 15, progress=None) -> dict:
    """Settings for a channel-by-channel fit, measured on the data -- and
    whether the data allow one at all.

    How many channels each fit has to sum is a question about the data's
    noise, which no default answers: one detector's single channel gives
    E_F to a few meV, another's to a few hundred. So it is measured. For a
    series of widths (1, 3, 7, 15 ... channels, up to a ``min_fits``-th of
    the detector), ``trial_fits`` fits spread across the detector, each
    starting from the ``seed`` (the fit of the summed EDC) and keeping its
    line shape; the scatter of their E_F about a parabola (median absolute
    deviation, so a stray fit does not decide it), or the fits' own error
    if that is larger, is what that width achieves. Counting statistics
    make it fall as 1/sqrt(width), so each trial says the same thing --
    ``c = scatter * sqrt(width)``, the E_F error of one channel -- and their
    median is the measurement.

    The **channels needed** per fit to reach ``target`` -- by default the
    larger of 10 meV, two energy steps and a tenth of the seed's resolution,
    finer than which the energy axis or the resolution cannot follow -- is
    then ``(c / target)**2``. Compared with the **channels measured**: if
    fewer than ``min_fits`` fits of that many channels fit across the
    detector, a channel-by-channel fit cannot follow the edge across it and
    the data are not suited to one (``suitable`` False). Otherwise the fits
    are spaced one width apart (no channel shared, so their errors are
    independent), at most ``max_fits`` of them.

    Returns ``{"suitable", "needed", "total", "possible", "half_width",
    "step", "fits", "error", "per_channel", "target", "hold_shape",
    "trials": [(width, scatter), ...]}``: a proposal, which the person may
    change.
    """
    angles = np.asarray(angles, dtype=float)
    energy = np.asarray(energy, dtype=float)
    frame = np.asarray(frame, dtype=float)
    n = angles.size
    step_e = float(np.median(np.abs(np.diff(energy)))) if energy.size > 1 else 0.01
    if target is None:
        target = max(0.010, 2.0 * step_e, 0.1 * abs(float(seed.get("resolution", 0.0))))
    widths, width = [], 1
    while width <= max(1, n // max(1, min_fits)):
        widths.append(width)
        width = 2 * width + 1
    trials = []
    for count, width in enumerate(widths):
        half = (width - 1) // 2
        centres = np.unique(np.linspace(half, n - 1 - half, trial_fits).round().astype(int))
        ef = np.full(centres.size, np.nan)
        reported = np.full(centres.size, np.nan)
        for k, centre in enumerate(centres):
            sub = slice(centre - half, centre + half + 1)
            values, errors, ok = fit_channels(
                angles[sub], energy, frame[sub], half_width=half, step=width,
                temperature=temperature, window=window, start=seed,
                hold_shape=True)
            index = min(half, values.size - 1)
            if ok[index]:
                ef[k] = values[index]
                reported[k] = errors[index]
        good = np.isfinite(ef)
        scatter = float("inf")              # the fits failed at this width
        if good.sum() >= max(4, centres.size // 2):
            x = angles[centres][good]
            fitted = np.polyval(np.polyfit(x, ef[good], 2), x)
            # 1.4826 MAD: the standard deviation, for Gaussian scatter
            scatter = float(1.4826 * np.median(np.abs(ef[good] - fitted))
                            * np.sqrt(good.sum() / max(good.sum() - 3, 1)))
            # Fits that hardly move from the seed scatter little and mean
            # little: their own error says so.
            known = np.isfinite(reported) & good
            if known.any():
                scatter = max(scatter, float(np.median(reported[known])))
        trials.append((int(width), scatter))
        if progress is not None and progress(count + 1, len(widths)) is False:
            break

    per_channel = [s * np.sqrt(w) for w, s in trials if np.isfinite(s)]
    c = float(np.median(per_channel)) if per_channel else float("inf")
    needed = (int(np.ceil((c / float(target)) ** 2)) if np.isfinite(c)
              else n + 1)
    needed = max(1, needed)
    width = needed if needed % 2 else needed + 1        # odd: centred
    possible = n // width if width <= n else 0
    suitable = possible >= min_fits
    width = min(width, n)
    step = max(width, int(np.ceil(n / max_fits)))
    fits = max(1, int(np.ceil((n - width) / step)) + 1)
    return {"suitable": bool(suitable), "needed": int(needed), "total": int(n),
            "possible": int(possible), "half_width": (width - 1) // 2,
            "step": int(step), "fits": int(fits),
            "error": c / np.sqrt(width) if np.isfinite(c) else float("inf"),
            "per_channel": c, "target": float(target), "hold_shape": True,
            "trials": trials, "min_fits": int(min_fits)}


def channel_fit_error(per_channel: float, width: int) -> float:
    """The E_F error expected of a fit summing ``width`` channels, from one
    channel's (``per_channel``; counting statistics)."""
    return float(per_channel) / np.sqrt(max(1, int(width)))


# --------------------------------------------------------------------------
# Dividing the Fermi cut-off out
# --------------------------------------------------------------------------
def levels_along(axis, positions, levels):
    """The Fermi level at every point of ``axis``, from edges fitted at
    ``positions``: linear between neighbouring fits, and held at the
    nearest fit beyond the first and the last -- a straight line carried
    past the data would invent a trend nobody measured.

    How a map whose E_F drifts with the deflector (or photon energy) gets
    one level per slice from fits on a few of them.
    """
    axis = np.asarray(axis, dtype=float)
    positions = np.asarray(positions, dtype=float)
    levels = np.asarray(levels, dtype=float)
    keep = np.isfinite(positions) & np.isfinite(levels)
    if not keep.any():
        raise ValueError("no fitted Fermi level to interpolate from")
    order = np.argsort(positions[keep])
    return np.interp(axis, positions[keep][order], levels[keep][order])


def divide_fermi(energy, values, ef: float, temperature: float,
                 resolution: float, *, energy_dim: int = -1,
                 cutoff_kt: float = 4.0, background=None):
    """Divide a spectrum by the resolution-broadened Fermi function.

    Only the **occupation** is divided out -- not the fitted density of
    states, which would remove real spectral weight along with the
    cut-off.

    ``background`` is the fitted ``(b0, b1)``, and if it is given it is taken
    out before the division and put back afterwards. That matters: dark
    counts and secondaries are not modulated by the occupation, so dividing
    them by it inflates them near E_F by exactly the factor the division is
    meant to remove from the signal.

    Everything above ``ef + cutoff_kt * kT`` is set to NaN: the divisor there
    is a small number known only to within the noise, and dividing by it
    produces spikes, not spectra. The viewer draws NaN as missing, which is
    what it is.
    """
    energy = np.asarray(energy, dtype=float)
    values = np.asarray(values, dtype=float)
    divisor = broadened_fermi(energy, ef, temperature, resolution)
    cut = float(ef) + float(cutoff_kt) * K_B * max(float(temperature), 1e-6)
    divisor = np.where(energy <= cut, divisor, np.nan)
    shape = [1] * values.ndim
    shape[energy_dim] = energy.size
    with np.errstate(invalid="ignore", divide="ignore"):
        divisor = np.where(np.abs(divisor) > 1e-6, divisor, np.nan).reshape(shape)
        if background is None:
            return values / divisor
        b0, b1 = (float(v) for v in background)
        bkg = (b0 + b1 * (energy - float(ef))).reshape(shape)
        return (values - bkg) / divisor + bkg
