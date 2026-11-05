"""
loader/incomplete.py
====================
A map whose acquisition was stopped before its last step, read as far as it
went.

Every beamline has this case. A scan is stopped by hand, the beam is lost,
the control software crashes -- and the file that is left still has the
size the scan *planned*. At ANTARES the HDF5 datasets are created at full
length and the steps never measured keep the fill value: the image is all
zeros and the deflector readback 0 or NaN. At CASSIOPEE the last spectrum
may be written without its parameter file. Elsewhere the steps not reached
are NaN. And the step that was being measured when the scan stopped can be
there with only part of its sweeps: present, but clearly weaker than the
ones before it.

None of these frames is a measurement. Shown as one, a frame of zeros or
NaN gives an image with no intensity range (the cut viewer stopped with
"Cannot set range [nan, nan]"), and a half-measured frame is a stripe in
every constant-energy map. So :func:`trim_incomplete`, called by
:func:`loader.registry.load` for every beamline, cuts them off the end of the
scanned axis -- and says so in ``info`` -- under one rule:

* **Empty** -- no counts (all zero or all NaN), or no finite value of the
  scanned axis -- from the end backwards: the steps never reached.
* **Then clearly weaker** -- a last frame whose total intensity is below
  :data:`WEAK_FRACTION` of the median of the :data:`REFERENCE_FRAMES` frames
  before it: the step that was running when the scan stopped. Repeated, so
  more than one can go, each judged against the frames before *it*.

Only the end of the scan is looked at. A weak frame in the middle is the
sample (an edge of the deflector range, a cross-section minimum in a
photon-energy scan) and is never touched; and the comparison is with the
neighbouring frames, not the whole scan, so a slow intensity trend across a
map is not mistaken for an interruption. At least :data:`MIN_KEPT` frames
are always kept. A dataset this program saved is never trimmed: what it
holds is what someone chose to keep.

Nothing is read whole: on a map left in its file only the frames looked at
are read, one at a time.
"""
from __future__ import annotations

import numpy as np

__all__ = ["WEAK_FRACTION", "REFERENCE_FRAMES", "MIN_KEPT", "TRIMMED_KINDS",
           "frame_total", "incomplete_tail", "trim_incomplete"]

#: A last frame with less than this fraction of the median total of the
#: frames before it is taken as stopped part-way. A half is "clearly lower":
#: real intensity does not halve from one step to the next of a deflector
#: or photon-energy scan, while a frame cut short by an interruption usually
#: holds a small part of its sweeps.
WEAK_FRACTION = 0.5

#: How many frames before a candidate its total is compared with (their
#: median). Few, so that a gradual trend across the scan is followed.
REFERENCE_FRAMES = 5

#: Never trim a scan below this many frames.
MIN_KEPT = 2

#: The kinds whose first axis is a scanned (acquisition) axis.
TRIMMED_KINDS = ("map", "kz_map")


def frame_total(array, index: int) -> float:
    """The summed intensity of frame ``index`` along the first axis; NaN
    when the frame holds no finite value. Reads only that frame from a lazy
    (on-disk) array."""
    frame = np.asarray(array[index], dtype=float)
    finite = np.isfinite(frame)
    if not finite.any():
        return float("nan")
    return float(frame[finite].sum())


def incomplete_tail(array, axis0=None, weak_fraction: float = WEAK_FRACTION,
                    reference_frames: int = REFERENCE_FRAMES,
                    min_kept: int = MIN_KEPT):
    """How many frames at the end of ``array`` (along its first axis) were
    not measured, or not measured to the end, and why.

    Returns ``(dropped, reasons, totals)``: the number of trailing frames to
    cut, one short reason per cut frame (last frame first), and the totals
    that were read (``{index: total}``) for the record. ``axis0`` is the
    scanned axis' values, if known; a frame whose value is not finite was
    not reached.
    """
    n = int(np.shape(array)[0]) if np.ndim(array) else 0
    totals = {}

    def total(i):
        if i not in totals:
            totals[i] = frame_total(array, i)
        return totals[i]

    def axis_missing(i):
        if axis0 is None:
            return False
        values = np.asarray(axis0, dtype=float).ravel()
        return values.size == n and not np.isfinite(values[i])

    reasons = []
    last = n - 1
    # The steps never reached: nothing counted, or no axis value.
    while last >= min_kept:
        t = total(last)
        if axis_missing(last):
            reasons.append("no value of the scanned axis")
        elif not np.isfinite(t):
            reasons.append("no finite counts (NaN)")
        elif t == 0:
            reasons.append("no counts")
        else:
            break
        last -= 1
    # The step running when the scan stopped: clearly weaker than the ones
    # before it.
    while last >= min_kept:
        first = max(0, last - int(reference_frames))
        before = [total(i) for i in range(first, last)]
        before = [b for b in before if np.isfinite(b)]
        if not before:
            break
        reference = float(np.median(before))
        t = total(last)
        if reference <= 0 or t >= weak_fraction * reference:
            break
        reasons.append(f"{t / reference:.0%} of the frames before it")
        last -= 1
    return n - 1 - last, reasons, totals


def _trim_info(info: dict, n: int, keep: int) -> None:
    """Cut the per-frame arrays a loader put in ``info`` (the readbacks of
    the scanned axis) to the frames kept."""
    for key, value in list(info.items()):
        if "axis0" in key and isinstance(value, np.ndarray) \
                and value.ndim == 1 and value.size == n:
            info[key] = value[:keep]


def _describe_steps(n: int, reasons) -> str:
    """``"steps 101-151 (no counts)"``: the cut steps, numbered from 1 as a
    scan counts them, runs of the same reason told once."""
    runs = []                                  # [first step, last step, reason]
    for i, reason in enumerate(reasons):       # last frame first
        step = n - i
        if runs and runs[-1][2] == reason and runs[-1][0] == step + 1:
            runs[-1][0] = step
        else:
            runs.append([step, step, reason])
    parts = [(f"step {a}" if a == b else f"steps {a}-{b}") + f" ({reason})"
             for a, b, reason in reversed(runs)]
    return ", ".join(parts)


def trim_incomplete(scan, weak_fraction: float = WEAK_FRACTION):
    """Cut the frames at the end of ``scan`` that were not, or not fully,
    measured (see the module's docstring), in place, and return the scan.

    What was done is written into ``scan.info``: ``incomplete.frames_dropped``
    (how many), ``incomplete.frames_kept`` and ``incomplete.note`` (which
    steps and why, in words). A scan with nothing to cut is returned as it
    came, with nothing added.
    """
    if getattr(scan, "kind", None) not in TRIMMED_KINDS:
        return scan
    info = scan.info if isinstance(scan.info, dict) else {}
    if info.get("_case") == 5:
        return scan                 # this program's own dataset, in a .nxs
    array = scan.value
    if array is None or np.ndim(array) != 3:
        return scan
    n = int(np.shape(array)[0])
    axis0 = scan.x
    if axis0 is not None and np.size(axis0) != n:
        axis0 = None
    dropped, reasons, totals = incomplete_tail(array, axis0,
                                               weak_fraction=weak_fraction)
    if not dropped:
        return scan
    keep = n - dropped
    # A map left in its file stays there: ``head`` cuts it without reading.
    scan.value = array.head(keep) if hasattr(array, "head") else array[:keep]
    if scan.x is not None and np.size(scan.x) == n:
        scan.x = np.asarray(scan.x)[:keep]
    if scan.kx is not None and np.ndim(scan.kx) >= 1 and np.shape(scan.kx)[0] == n:
        scan.kx = np.asarray(scan.kx)[:keep]
    _trim_info(info, n, keep)
    steps = _describe_steps(n, reasons)
    info["incomplete.frames_dropped"] = dropped
    info["incomplete.frames_kept"] = keep
    info["incomplete.frames_planned"] = n
    info["incomplete.note"] = (
        f"the scan was stopped before its end: the last {dropped} of {n} "
        f"steps were left out -- {steps}")
    return scan
