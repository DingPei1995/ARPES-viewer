"""
tools/processing/analysis.py
============================
Two analysis operations, as plain numpy/scipy functions with no Qt anywhere -- the same split as
``tools/momentum/kspace.py``, so both can be tested (and reused) without a display.

- **Arbitrary-direction cut** (``arbitrary_cut``): sample a cube along a path of up to six points
  picked on the constant-energy contour and return intensity against
  distance along that path.
- **Fermi-surface correction** (``fs_correction``): fit a polynomial through points picked along a feature that should be
  flat (a Fermi edge, a band bottom) and shift every angle column in energy
  so that it is.
"""
from __future__ import annotations

import numpy as np

try:
    from scipy.interpolate import RegularGridInterpolator
except ImportError as exc:      # pragma: no cover - scipy is a hard dependency
    raise ImportError("arpes_viewer.tools.processing.analysis needs scipy (RegularGridInterpolator)") from exc


# --------------------------------------------------------------------------
# Arbitrary-direction cut
# --------------------------------------------------------------------------
def _axis_step(axis) -> float:
    axis = np.asarray(axis, dtype=float)
    if axis.size < 2:
        return 1.0
    return float(abs(np.mean(np.diff(axis))))


def line_samples(x_axis, y_axis, p0, p1):
    """Points along the segment p0 -> p1, sampled at the grid's own spacing.

    Returns ``(xs, ys, r)`` with ``r`` the distance from ``p0``.

    Sampling along the segment itself (not along x, which degenerates as
    the line steepens) gives evenly spaced points for every direction.
    """
    x0, y0 = (float(v) for v in p0)
    x1, y1 = (float(v) for v in p1)
    length = float(np.hypot(x1 - x0, y1 - y0))
    step = min(_axis_step(x_axis), _axis_step(y_axis))
    if length <= 0 or step <= 0:
        return np.array([x0]), np.array([y0]), np.array([0.0])
    n = int(np.ceil(length / step)) + 1
    t = np.linspace(0.0, 1.0, n)
    return x0 + t * (x1 - x0), y0 + t * (y1 - y0), t * length


def arbitrary_cut(x_axis, y_axis, z_axis, cube, points):
    """Intensity along a path of 2..6 points through an (x, y, z) cube.

    ``cube`` is indexed ``[x, y, z]`` -- for a deflector map, (deflector
    angle, slit angle, energy). ``points`` is a list of (x, y) corners; the
    path runs through them in order.

    Returns ``(distance, z_axis, values, joints)``:
    ``values`` has shape ``(len(distance), len(z_axis))``, ``distance`` is
    cumulative along the whole path (so the segments are laid end to end),
    and ``joints`` gives the distance at each corner between two segments,
    for drawing boundary markers.

    Segments are joined by dropping each one's first sample, which is the
    previous segment's last sample, so no point is duplicated and no joint
    needs repair.
    """
    x_axis = np.asarray(x_axis, dtype=float)
    y_axis = np.asarray(y_axis, dtype=float)
    z_axis = np.asarray(z_axis, dtype=float)
    cube = np.asarray(cube, dtype=float)
    pts = [(float(px), float(py)) for px, py in points]
    if len(pts) < 2:
        raise ValueError("an arbitrary cut needs at least two points")
    if cube.shape[:2] != (x_axis.size, y_axis.size):
        raise ValueError(f"cube {cube.shape} does not match axes "
                         f"({x_axis.size}, {y_axis.size})")

    # NaNs would poison every interpolated sample around them, so they are
    # carried as weights instead: interpolate the values and the mask, then
    # divide, exactly as the display-side smoothing does.
    finite = np.isfinite(cube)
    interp = RegularGridInterpolator((x_axis, y_axis), np.where(finite, cube, 0.0),
                                     bounds_error=False, fill_value=np.nan)
    weight = RegularGridInterpolator((x_axis, y_axis), finite.astype(float),
                                     bounds_error=False, fill_value=np.nan)

    chunks, dists, joints = [], [], []
    offset = 0.0
    for i in range(len(pts) - 1):
        xs, ys, r = line_samples(x_axis, y_axis, pts[i], pts[i + 1])
        if i:                       # drop the duplicated corner sample
            xs, ys, r = xs[1:], ys[1:], r[1:]
            joints.append(offset)
        sample = np.column_stack([np.clip(xs, x_axis.min(), x_axis.max()),
                                  np.clip(ys, y_axis.min(), y_axis.max())])
        num = interp(sample)
        den = weight(sample)
        with np.errstate(invalid="ignore", divide="ignore"):
            values = num / den
        chunks.append(np.where(den > 1e-9, values, np.nan))
        dists.append(offset + r)
        offset += float(r[-1]) if r.size else 0.0

    return (np.concatenate(dists), z_axis, np.concatenate(chunks, axis=0),
            np.asarray(joints, dtype=float))


# --------------------------------------------------------------------------
# Fermi-surface correction
# --------------------------------------------------------------------------
def fit_feature(points, order: int = 2):
    """Least-squares polynomial through the picked (angle, energy) points,
    Returns the coefficients,
    highest power first, ready for ``np.polyval``."""
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("points must be a list of (angle, energy) pairs")
    order = int(order)
    if pts.shape[0] < order + 1:
        raise ValueError(f"an order-{order} fit needs at least {order + 1} points")
    return np.polyfit(pts[:, 0], pts[:, 1], order)


def shift_bins(angle_axis, energy_axis, coeffs):
    """How many energy bins each angle column has to move so the fitted
    feature comes out flat.

    The column where the fit is highest keeps its energies (shift 0) and
    every other column moves down by the fit's deficit there, whichever
    way the curve bends.
    """
    angle_axis = np.asarray(angle_axis, dtype=float)
    step = _axis_step(energy_axis)
    if step <= 0:
        raise ValueError("the energy axis has no usable step")
    fitted = np.polyval(coeffs, angle_axis)
    return np.round((fitted.max() - fitted) / step).astype(int), fitted


def fs_correction(values, angle_axis, energy_axis, coeffs, *,
                  angle_dim: int = 0, energy_dim: int = -1):
    """Straighten a curved feature by shifting each angle column in energy.

    Works on a 2D frame (angle, energy) and on a 3D cube alike: ``angle_dim``
    names the axis the fit was made along and every other axis is carried
    through untouched, which is how a fit made on one slit cut corrects a
    whole (deflector, slit, energy) map.

    Returns ``(corrected, new_energy_axis)``. The energy axis grows by the
    span of the fit, so nothing is cropped; the bins that no column reaches
    are NaN, and are left NaN rather than filled -- there is no measurement
    there, and the display already treats NaN as missing.

    The bin width is taken from the axis itself (``mean(diff(E))``).
    """
    values = np.asarray(values, dtype=float)
    energy_axis = np.asarray(energy_axis, dtype=float)
    shifts, fitted = shift_bins(angle_axis, energy_axis, coeffs)

    moved = np.moveaxis(values, (angle_dim, energy_dim), (0, -1))
    n_angle, n_energy = moved.shape[0], moved.shape[-1]
    if shifts.size != n_angle:
        raise ValueError(f"{shifts.size} shifts for {n_angle} angle points")
    new_n = int(n_energy + shifts.max())
    out = np.full(moved.shape[:-1] + (new_n,), np.nan)
    for i, s in enumerate(shifts):
        out[i, ..., s:s + n_energy] = moved[i, ...]

    # Trim energy bins no column reached (belt and braces: with this shift
    # convention the first and last are always covered).
    used = np.any(np.isfinite(out), axis=tuple(range(out.ndim - 1)))
    if used.any():
        lo, hi = int(np.argmax(used)), int(len(used) - np.argmax(used[::-1]))
        out = out[..., lo:hi]
    else:
        lo, hi = 0, new_n

    step = _axis_step(energy_axis)
    new_axis = float(energy_axis[0]) + (np.arange(lo, hi) * step)
    return np.moveaxis(out, (0, -1), (angle_dim, energy_dim)), new_axis


def offset_per_channel(values, angle_axis, energy_axis, ref_angles, ref_levels,
                       *, angle_dim: int = 0, energy_dim: int = -1,
                       measured: slice = None):
    """Put every angle channel on its own E - E_F: the Fermi edge fitted
    channel by channel (``ref_levels`` at ``ref_angles``, from this data or
    from a reference measured with the same analyser) is subtracted from
    each channel's energies, and the channels are resampled (linearly) onto
    one energy axis they all cover.

    Channels outside the fitted ones -- the blank borders the fit left out,
    and anything the reference did not reach -- are cut off rather than
    extrapolated, as are those outside ``measured`` (this data's own
    measured channels, see :func:`tools.spectra.fermi.measured_channels`).
    Between fitted channels the level is interpolated linearly.

    Works on a 2D frame and on a cube alike (``angle_dim``/``energy_dim``
    name the axes; the rest are carried through). Returns ``(values,
    angle_axis, energy_axis)``, the first two cropped to the kept channels.
    """
    values = np.asarray(values, dtype=float)
    angle_axis = np.asarray(angle_axis, dtype=float)
    energy_axis = np.asarray(energy_axis, dtype=float)
    ref_angles = np.asarray(ref_angles, dtype=float)
    ref_levels = np.asarray(ref_levels, dtype=float)
    good = np.isfinite(ref_angles) & np.isfinite(ref_levels)
    if good.sum() < 1:
        raise ValueError("no fitted channel to offset by")
    order = np.argsort(ref_angles[good])
    ref_angles, ref_levels = ref_angles[good][order], ref_levels[good][order]

    span = max(abs(float(np.median(np.diff(angle_axis)))) if angle_axis.size > 1
               else 0.0, 1e-12)
    keep = ((angle_axis >= ref_angles[0] - 0.5 * span)
            & (angle_axis <= ref_angles[-1] + 0.5 * span))
    if measured is not None:
        inside = np.zeros(angle_axis.size, dtype=bool)
        inside[measured] = True
        keep &= inside
    if not keep.any():
        raise ValueError("none of this data's channels lies inside the "
                         "fitted ones")
    first = int(np.argmax(keep))
    last = int(keep.size - np.argmax(keep[::-1]))
    kept = slice(first, last)
    levels = np.interp(angle_axis[kept], ref_angles, ref_levels)

    moved = np.moveaxis(values, (angle_dim, energy_dim), (0, -1))[kept]
    ascending = energy_axis.size < 2 or energy_axis[-1] >= energy_axis[0]
    energy = energy_axis if ascending else energy_axis[::-1]
    if not ascending:
        moved = moved[..., ::-1]
    step = _axis_step(energy)
    lo = float(energy[0] - levels.min())
    hi = float(energy[-1] - levels.max())
    if hi <= lo:
        raise ValueError("the channels' Fermi levels differ by more than "
                         "the energy range: no energy is common to all")
    count = int(np.floor((hi - lo) / step + 1e-9)) + 1
    new_energy = lo + step * np.arange(count)

    out = np.empty(moved.shape[:-1] + (count,), dtype=float)
    for i, level in enumerate(levels):
        position = (new_energy + level - energy[0]) / step
        position = np.clip(position, 0.0, energy.size - 1.0)
        below = np.minimum(np.floor(position).astype(int), energy.size - 2)
        below = np.maximum(below, 0)
        frac = position - below
        block = moved[i]
        upper = np.minimum(below + 1, energy.size - 1)
        out[i] = block[..., below] * (1.0 - frac) + block[..., upper] * frac
    if not ascending:
        out = out[..., ::-1]
        new_energy = new_energy[::-1]
    return (np.moveaxis(out, (0, -1), (angle_dim, energy_dim)),
            angle_axis[kept], new_energy)
