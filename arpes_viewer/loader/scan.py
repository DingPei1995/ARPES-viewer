"""
loader/scan.py
==============
What every reader hands back, and what keeps a measurement on disk.

* :class:`NxsScan` -- one dataset: its ``kind``, its axes in the slots that
  kind names (:data:`AXIS_SLOTS`), the array, the labels with their units,
  and the metadata. Every loader returns one.
* The kinds: :data:`AXIS_SLOTS`, :data:`CUBE_KINDS`, :data:`CURVE_KINDS`,
  :data:`MOMENTUM_KINDS`, :data:`KIND_LABELS`, :func:`axis_slots`,
  :func:`energy_slot`.
* :class:`LazyArray` and :class:`LazyCube` -- an HDF5 dataset left in the
  file and read as it is looked at, and :data:`HANDLES`, the one place open
  HDF5 files are counted and closed.
* Axis helpers shared by the HDF5 readers: :func:`resolve_axis_order`,
  :func:`align_and_transpose` (which raw axis is which, matched by length
  against the axis vectors), :func:`scalar0`, :func:`squeeze_to_1d`.

Nothing here imports Qt.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
import warnings
from dataclasses import dataclass, field
from typing import Optional
import h5py
import numpy as np


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _decode(x):
    """Decode bytes / numpy bytes_ scalars & arrays to str, pass through else."""
    if isinstance(x, (bytes, np.bytes_)):
        return x.decode("utf-8", errors="replace")
    if isinstance(x, np.ndarray) and x.dtype.kind == "S":
        return np.char.decode(x, "utf-8")
    return x


def _read(f: h5py.File, path: str):
    """Read a dataset, decoding strings, tolerant of a trailing '/'."""
    path = path.rstrip("/")
    return _decode(f[path][()])


def _read_opt(f: h5py.File, path: str, default=None):
    path = path.rstrip("/")
    if path not in f:
        return default
    return _decode(f[path][()])


def scalar0(arr, name: str = "value") -> float:
    """The first stored element of a calibration dataset, whatever its
    shape.

    On real files these "single-value" calibration datasets (escalemin,
    xscalemult, ...) are sometimes logged as 2D arrays (one row per
    acquisition frame), where plain ``arr[0]`` would return a sub-array. So
    the array is flattened first, and a warning is given if the values are
    not all (approximately) equal.
    """
    a = np.asarray(arr)
    flat = a.ravel()
    if flat.size == 0:
        raise ValueError(f"{name}: empty array, cannot extract a scalar (shape={a.shape}).")
    v0 = flat[0]
    if flat.size > 1 and np.issubdtype(flat.dtype, np.number):
        spread = float(np.ptp(flat.astype(float)))
        if spread > 1e-6 * (abs(float(v0)) + 1e-12):
            warnings.warn(
                f"{name}: expected a constant-valued calibration array but "
                f"values span "
                f"{spread:.6g} across shape {a.shape}; using the first "
                f"element ({v0!r}). If this file's calibration genuinely "
                f"drifts, treating it as constant is wrong -- inspect it by hand."
            )
    return float(v0)


def squeeze_to_1d(arr, name: str = "array") -> np.ndarray:
    """Collapse a nominally-1D scan-axis array (e.g. an actuator readback)
    to a true 1D array, tolerating harmless extra singleton dimensions
    (shape (N,1), (1,N), ...) that show up on some real files. Warns
    (rather than silently guessing) if a genuinely multi-valued extra
    dimension is found, since flattening that would silently interleave
    unrelated data."""
    a = np.asarray(arr)
    squeezed = np.squeeze(a)
    if squeezed.ndim == 0:
        return squeezed.reshape(1).astype(float)
    if squeezed.ndim != 1:
        warnings.warn(
            f"{name}: expected a 1D scan axis, got shape {a.shape} (still "
            f"{squeezed.ndim}D after squeezing singleton dims); flattening "
            f"in C order -- verify this is meaningful for your file with "
            f"inspect_nxs()."
        )
        squeezed = squeezed.reshape(-1)
    return squeezed.astype(float)


# --------------------------------------------------------------------------
# Axis labels and units
# --------------------------------------------------------------------------
#: The analyser's slit-direction axis and the deflector axis are both
#: reported in degrees, and energies in eV, throughout these files.
ANGLE_UNIT = "\u00b0"


ENERGY_UNIT = "eV"


# --------------------------------------------------------------------------
def resolve_axis_order(shape, axis_lengths: "dict[str, int]", order: "list[str]",
                       what: str = "array") -> "tuple[int, ...]":
    """Work out which raw axis is which named axis, by matching lengths.

    Split out of :func:`align_and_transpose` so the same reasoning can be
    applied to a dataset that is never read into memory (see
    :class:`LazyCube`): only ``shape`` is needed, not the data.
    """
    if len(shape) != len(order):
        raise ValueError(
            f"resolve_axis_order: {what} has {len(shape)} dims but {len(order)} "
            f"named axes were requested ({order}). Raw shape={tuple(shape)}. "
            f"Use inspect_nxs() to look at the file and adjust the parsing."
        )
    remaining = list(range(len(shape)))
    perm = []
    for name in order:
        target = axis_lengths[name]
        candidates = [ax for ax in remaining if shape[ax] == target]
        if not candidates:
            raise ValueError(
                f"resolve_axis_order: no remaining raw axis of length {target} "
                f"for '{name}'. Raw shape={tuple(shape)}, remaining={remaining}, "
                f"expected lengths={axis_lengths}."
            )
        if len(candidates) > 1:
            warnings.warn(
                f"resolve_axis_order: axis '{name}' (length {target}) is ambiguous "
                f"-- {len(candidates)} raw axes share that length ({candidates}). "
                f"Picking axis {candidates[0]}; verify with inspect_nxs() if this "
                f"looks wrong."
            )
        perm.append(candidates[0])
        remaining.remove(candidates[0])
    return tuple(perm)


class _HandleRegistry:
    """One open HDF5 handle per file path, reference counted.

    Two reasons this is not left to `h5py.File` per caller:

    * A file often holds several measurements (six Cuts or Maps is normal),
      and the user may have several of them open at once. One handle serves
      them all instead of one per window.
    * HDF5 keeps a single underlying handle per path per process, so two
      `h5py.File` objects for the same file are not independent: on some
      builds, closing either one invalidates datasets held by the other
      (which is exactly what a LazyCube holds). Routing every open through
      here means the file is closed once, when the last user lets go.
    """

    def __init__(self):
        self._open = {}          # abspath -> [h5py.File, refcount]

    def acquire(self, path: str) -> h5py.File:
        key = os.path.abspath(path)
        entry = self._open.get(key)
        if entry is not None and entry[0].id.valid:
            entry[1] += 1
            return entry[0]
        handle = h5py.File(path, "r")
        self._open[key] = [handle, 1]
        return handle

    def release(self, path: str, handle=None) -> None:
        """Give back one claim on ``path``. ``handle`` is the File the claim
        was made on: if the registry has since had to replace it (it was
        found invalid), a release for the old one must not count against
        the new one's users -- that would close a file they are reading."""
        key = os.path.abspath(path)
        entry = self._open.get(key)
        if entry is None:
            return
        if handle is not None and entry[0] is not handle:
            return
        entry[1] -= 1
        if entry[1] <= 0:
            self._open.pop(key, None)
            try:
                entry[0].close()
            except Exception:
                pass

    def close_under(self, folder: str) -> int:
        """Close every handle on a file inside ``folder``, whoever holds it.
        Only for shutting down, when the folder is about to be deleted (a
        file still open cannot be removed on Windows). Returns how many."""
        root = os.path.join(os.path.abspath(folder), "")
        closed = 0
        for key in [k for k in self._open if k.startswith(root)]:
            handle, _count = self._open.pop(key)
            try:
                handle.close()
            except Exception:
                pass
            closed += 1
        return closed

    def open_count(self) -> int:
        """Number of files currently held open (used by the tests)."""
        return len(self._open)

    def is_open(self, path: str) -> bool:
        return os.path.abspath(path) in self._open

    @contextmanager
    def borrow(self, path: str):
        """``with HANDLES.borrow(path) as f:`` -- read a file *through* the
        registry for the length of a block.

        Every short look at a file (is it ours? what entries does it hold?)
        used to open a second ``h5py.File`` on it and close it again. With
        a viewer reading the same file, that close can invalidate the
        viewer's datasets on some HDF5 builds -- "Can't synchronously read
        data (identifier is not of specified type)" on the next read. A
        borrowed handle is the shared one, and giving it back never closes
        a file somebody else still holds."""
        handle = self.acquire(path)
        try:
            yield handle
        finally:
            self.release(path, handle)


HANDLES = _HandleRegistry()


class LazyCube:
    """A 4D cube that stays on disk, presented in (y, x, k, E) order.

    A real spatial scan is 46x91x96x941 -- around a gigabyte, and often on a
    network share. Reading it whole just to open a file froze the GUI for
    many seconds (long enough that clicks were dropped, so the window seemed
    to need several double-clicks). Almost nothing needs the whole cube: a
    cursor move needs one (k, E) frame, and the spatial overview comes from
    the reduced ``data_11``/``data_01`` datasets the file already carries.

    Indexing works exactly as on the equivalent numpy array -- ints and
    slices in (y, x, k, E) order -- and reads only the selection. The file
    handle stays open, so the owning :class:`NxsScan` must be closed when
    finished with (``NxsData`` does this).
    """

    def __init__(self, dataset, perm: "tuple[int, ...]"):
        self._dset = dataset
        self._perm = perm
        self.shape = tuple(dataset.shape[ax] for ax in perm)
        self.dtype = dataset.dtype
        self.ndim = len(self.shape)

    def __len__(self):
        return self.shape[0]

    def _normalise(self, key):
        if not isinstance(key, tuple):
            key = (key,)
        # `Ellipsis in key` and `key.index(Ellipsis)` both compare with ==,
        # which on an array index returns an array and then raises "the
        # truth value of an array ... is ambiguous". Identity is what is
        # meant anyway -- there is only one Ellipsis object.
        positions = [i for i, sel in enumerate(key) if sel is Ellipsis]
        if positions:
            i = positions[0]
            key = key[:i] + (slice(None),) * (self.ndim - len(key) + 1) + key[i + 1:]
        return key + (slice(None),) * (self.ndim - len(key))

    def __getitem__(self, key):
        key = self._normalise(key)
        # Reorder the selection into the dataset's own axis order, read, then
        # put the surviving axes back into (y, x, k, E) order.
        src_key = [None] * self.ndim
        for out_ax, sel in enumerate(key):
            src_key[self._perm[out_ax]] = sel
        data = self._dset[tuple(src_key)]

        surviving_src = [ax for ax in range(self.ndim)
                         if not isinstance(src_key[ax], (int, np.integer))]
        wanted_src = [self._perm[out_ax] for out_ax, sel in enumerate(key)
                      if not isinstance(sel, (int, np.integer))]
        if len(wanted_src) < 2:
            return data
        return np.transpose(data, [surviving_src.index(ax) for ax in wanted_src])

    @property
    def size(self) -> int:
        return int(np.prod(self.shape)) if self.shape else 1

    @property
    def nbytes(self) -> int:
        return self.size * self.dtype.itemsize

    def materialise(self) -> np.ndarray:
        """Read the whole cube into memory, in this object's axis order.
        Only for callers that genuinely need every point; everything in the
        GUI avoids this."""
        return self[(slice(None),) * self.ndim]

    def __array__(self, dtype=None):
        """So ``np.asarray(cube)`` works -- see :class:`LazyArray`."""
        data = self.materialise()
        return data if dtype is None else data.astype(dtype)


class LazyArray:
    """An array of any rank that stays in its HDF5 file until indexed.

    :class:`LazyCube` above does this for the 4-D spatial scan with an axis
    permutation; this is the same idea without the permutation and for any
    rank, which is what a map, a cut and a saved dataset need. The two are
    kept separate rather than merged because the permutation is the whole
    point of the one and dead weight in the other.

    It exposes ``shape``/``dtype``/``ndim`` and passes indexing straight
    through to h5py, so slicing code cannot tell the difference. The one
    addition that makes it safe to drop in everywhere is ``__array__``:
    ``np.asarray(lazy)`` reads the whole thing, so any routine that really
    does need every point -- an operation in ``tools.processing.process``, a save, a
    fit -- keeps working unchanged, and only pays for what it asked for.

    The file handle belongs to the owning :class:`NxsScan`; once that is
    closed this can no longer be read.
    """

    def __init__(self, dataset):
        self._dset = dataset
        self.shape = tuple(dataset.shape)
        self.dtype = dataset.dtype
        self.ndim = len(self.shape)
        self.size = int(np.prod(self.shape)) if self.shape else 1
        self.nbytes = self.size * self.dtype.itemsize

    def __len__(self):
        return self.shape[0] if self.shape else 0

    def __getitem__(self, key):
        return self._dset[key]

    def materialise(self) -> np.ndarray:
        return self._dset[()]

    def __array__(self, dtype=None):
        data = self.materialise()
        return data if dtype is None else data.astype(dtype)

    def __repr__(self):
        return f"LazyArray(shape={self.shape}, dtype={self.dtype})"


def align_and_transpose(arr: np.ndarray, axis_lengths: "dict[str, int]", order: "list[str]") -> np.ndarray:
    """Reorder ``arr``'s axes to match ``order`` by matching each named
    axis's expected length (``axis_lengths[name]``) against ``arr.shape``.

    Raises ValueError if ``arr.ndim != len(order)``. Warns (does not raise)
    if two candidate axes share the same length -- in that case the first
    unused match is taken and the ambiguity is reported, since it cannot be
    resolved from lengths alone.
    """
    return np.transpose(arr, resolve_axis_order(arr.shape, axis_lengths, order,
                                               what="array"))


# --------------------------------------------------------------------------
# Momentum conversion (only needed for the deflector-scanned angle axis --
# the analyzer's own slit-direction scale, "xscale" below, is already
# delivered in k by the MBS acquisition software).
# --------------------------------------------------------------------------
def deflector_angle_to_k(angle_deg: np.ndarray, kinetic_energy_eV) -> np.ndarray:
    """Standard free-electron final-state small-angle ARPES conversion::

        k_parallel [A^-1] = 0.5123 * sqrt(KE[eV]) * sin(angle[rad])

    ``kinetic_energy_eV`` may be a scalar (single reference KE, e.g. center
    kinetic energy) or an array broadcastable against ``angle_deg`` (e.g. one
    KE per energy channel, to convert a whole (angle, E) plane at once).

    Caveats (verify against your own calibration before publishing numbers):
    - assumes normal-incidence / zero inner-potential correction (no k_z
      refraction correction at the sample surface),
    - assumes ``angle_deg`` is the true emission angle in degrees (this
      matches the ANTARES "DeflX" deflector convention, but was not
      independently verified against a real data file),
    - the analyzer slit-direction axis is NOT passed through this function
      -- it is already in k according to the acquisition software.
    """
    angle_rad = np.deg2rad(np.asarray(angle_deg, dtype=float))
    KE = np.asarray(kinetic_energy_eV, dtype=float)
    return 0.5123 * np.sqrt(KE) * np.sin(angle_rad)


# --------------------------------------------------------------------------
# Result container
# --------------------------------------------------------------------------
#: Which of :class:`NxsScan`'s axis slots hold each kind's array dimensions,
#: **in the array's own order**, and which slot holds its constructor's.
#:
#: This is the one authority for the question "what are this dataset's
#: axes?". It used to be answered in five places -- ``tools.processing.dataops``'s two
#: tables, the loader's ``_axis_slots``, ``loader.session.scan_to_dict``, the
#: launcher's ``_dataset_for_saving`` and ``_MemScan.__init__`` -- which is
#: four chances for a new kind to be half-supported, and exactly the kind of
#: duplication that makes adding a fifth axis (photon energy, delay, kz) a
#: survey of the whole program rather than an edit.
#:
#: ``array`` is the order the dimensions are stored in; ``constructor`` is
#: the order :class:`ui.viewers.widgets.MemoryData` takes them in. They differ
#: for a 4-D spatial scan, whose cube is stored (y, x, k, E) because that is
#: the order the file's own dataset is in, and constructed (x, y, k, E).
AXIS_SLOTS = {
    "cut": {"array": ("x", "y"), "constructor": ("x", "y")},
    "map": {"array": ("x", "k", "z"), "constructor": ("x", "k", "z")},
    "k_map": {"array": ("x", "k", "z"), "constructor": ("x", "k", "z")},
    "kz_map": {"array": ("x", "k", "z"), "constructor": ("x", "k", "z")},
    "kz_map_k": {"array": ("x", "k", "z"), "constructor": ("x", "k", "z")},
    "spem_1d": {"array": ("x", "y", "z"), "constructor": ("x", "y", "z")},
    "spem_4d": {"array": ("y", "x", "k", "z"),
                "constructor": ("x", "y", "k", "z")},
    # One-dimensional data, as a table: ``x`` is the physical axis (energy,
    # or angle/momentum for an MDC), ``y`` numbers the channels -- one for a
    # plain EDC, one per spin channel, or a curve with its uncertainty
    # beside it. Channel names travel in ``info["curve.channels"]``; see
    # :mod:`tools.spectra.curves`.
    "edc": {"array": ("x", "y"), "constructor": ("x", "y")},
    "mdc": {"array": ("x", "y"), "constructor": ("x", "y")},
    "spin_edc": {"array": ("x", "y"), "constructor": ("x", "y")},
}


#: The one-dimensional kinds: curves against one axis, several channels
#: each, drawn by the curve viewer rather than as an image.
CURVE_KINDS = ("edc", "mdc", "spin_edc")


#: Which axis of a curve kind is the energy. An MDC has none; that is the
#: one kind for which "the last axis is the energy" does not hold.
_CURVE_ENERGY = {"edc": "x", "spin_edc": "x", "mdc": None}


#: The kinds that are a three-axis cube of (scanned axis, analyser angle or
#: momentum, energy). They share a viewer, a 3-D view and a processing
#: panel, and differ only in what their first axis *means* -- which is
#: exactly the distinction the program is otherwise careless about, so it is
#: worth having the set written down once:
#:
#: ``map``     deflector or polar angle, and so convertible to momentum
#: ``k_map``   already converted: in-plane momentum
#: ``kz_map``  photon energy, i.e. an out-of-plane (k_z) scan. Not
#:             convertible by the in-plane formula -- turning a photon
#:             energy into k_z needs the inner potential, which is a
#:             property of the sample and not of the measurement.
#: ``kz_map_k`` that scan after the k_z conversion: (k_z, k_par, E), both
#:             momenta in A^-1. k_z leads because it is the axis the
#:             measurement is about, and the viewers put the first axis
#:             across the image.
CUBE_KINDS = ("map", "k_map", "kz_map", "kz_map_k")


#: The cube kinds whose first two axes are already momentum. Nothing that
#: converts angles should be offered for these, and anything that draws a
#: Brillouin zone needs one of them.
MOMENTUM_KINDS = ("k_map", "kz_map_k")


#: What each kind is called in the file browser's "kind" column. A kind with
#: no entry shows its internal name, which is better than showing nothing.
KIND_LABELS = {
    "cut": "Cut",
    "map": "Map",
    "k_map": "k-map",
    "kz_map": "kz map",
    "kz_map_k": "kz map (k)",
    "spem_4d": "SPEM",
    "spem_1d": "SPEM",
    "edc": "EDC",
    "mdc": "MDC",
    "spin_edc": "Spin EDC",
}


def axis_slots(kind: str, order: str = "array") -> tuple:
    """The axis slot names for ``kind``; ``()`` for one with no plain
    axes-and-array form (``unsupported``). ``order`` is "array" or
    "constructor" -- see :data:`AXIS_SLOTS`."""
    return AXIS_SLOTS.get(kind, {}).get(order, ())


def energy_slot(kind: str):
    """Which axis of ``kind`` is the energy, or ``None`` if it has none.

    Derived rather than tabulated. Energy is the last axis a dataset is
    constructed with, for every kind there is: a cut is (angle, energy), a
    cube is (scanned, angle, energy), a 4-D scan is (x, y, angle, energy).
    Two panels each carried their own hand-written ``{"cut": "y", "map":
    "z", ...}`` copy of that, which is two more places to forget when a kind
    is added -- and both would have silently refused to shift the energy
    axis of a ``kz_map`` with "has no energy axis to shift".
    """
    if kind in _CURVE_ENERGY:
        return _CURVE_ENERGY[kind]
    slots = axis_slots(kind, "constructor")
    return slots[-1] if slots else None


@dataclass
class NxsScan:
    kind: str                       # 'spem_4d' | 'spem_1d' | 'cut' | 'map' | 'unsupported'
    filename_prefix: str = ""
    info: dict = field(default_factory=dict)
    fourd_info: dict = field(default_factory=dict)

    # axes (only the ones relevant to `kind` are populated)
    x: Optional[np.ndarray] = None   # spatial x, or deflector angle (Map), or k/angle (Cut)
    y: Optional[np.ndarray] = None   # spatial y, or analyzer k axis (Map), or Energy (Cut)
    k: Optional[np.ndarray] = None   # analyzer momentum axis (spem_4d, map)
    z: Optional[np.ndarray] = None   # Energy axis
    kx: Optional[np.ndarray] = None  # converted deflector-angle -> k (map only, see .to_kspace())

    value: Optional[np.ndarray] = None     # main 2D/3D array for this `kind`
    #: spem_4d only: the (y, x, k, E) cube. A :class:`LazyCube` reading from
    #: the still-open file, not a numpy array -- index it as usual.
    value4d: object = None
    #: spem_4d only: {name: (dataset, perm)} for the reduced preview cubes,
    #: left unread; see NxsData.spatial_overview.
    previews: dict = field(default_factory=dict)
    #: open file handle when the scan reads lazily; released by close().
    _h5file: object = None
    #: the path that handle belongs to, for releasing it in the registry.
    _h5path: object = None

    def axis_slots(self, order: str = "array") -> tuple:
        """The names of the axis attributes this scan's dimensions live in
        (see :data:`AXIS_SLOTS`)."""
        return axis_slots(self.kind, order)

    def axes(self, order: str = "array") -> list:
        """This scan's axis vectors, in the array's order.

        Asking the scan rather than looking the kind up in a table is what
        lets a caller be written once for every kind: ``for axis in
        scan.axes()`` works for a 2-D cut and a 4-D spatial scan alike.
        """
        return [getattr(self, slot) for slot in self.axis_slots(order)]

    def array(self):
        """The dataset's own array -- the 4-D cube for a spatial scan, the
        value for everything else. May be lazy; ``np.asarray`` it if every
        point is needed."""
        if self.kind == "spem_4d" and self.value4d is not None:
            return self.value4d
        return self.value

    def close(self):
        """Release this scan's claim on the file. Safe to call more than
        once. The file itself is only closed when the last scan using it
        lets go, so other entries of the same file keep working. After this
        a LazyCube in ``value4d`` can no longer be indexed."""
        if self._h5file is not None:
            handle, self._h5file = self._h5file, None
            if self._h5path is not None:
                HANDLES.release(self._h5path, handle)
                self._h5path = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    #: Display labels (including units) for each axis this scan populates,
    #: keyed 'x', 'y', 'k', 'z'. Filled by the parsers; the GUI uses these
    #: verbatim for its axis titles so units live in one place.
    labels: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Metadata helpers
# --------------------------------------------------------------------------
def _scalarize(value):
    """Collapse a 1-element array to a plain scalar for display; leave real
    arrays and strings alone. Metadata datasets in these files are usually
    shape-(1,) rather than true scalars, which displays as '[3.5]' unless
    unwrapped."""
    if isinstance(value, np.ndarray):
        if value.size == 1:
            return value.reshape(-1)[0]
        if value.size == 0:
            return None
    return value


def to_kspace_cube(scan: NxsScan, kinetic_energy_eV=None, work_function_eV: float = 4.5):
    """For a ``kind == "map"`` scan, convert the raw deflector-angle axis
    (``scan.x``, in degrees) into momentum ``kx`` using
    :func:`deflector_angle_to_k`, returning ``(kx, ky, E, cube)`` where
    ``ky`` is the analyzer's own (already-in-k) axis and ``cube`` has shape
    ``(len(kx), len(ky), len(E))``.

    ``kinetic_energy_eV``: reference kinetic energy for the conversion.
        - If None, uses ``scan.info["center_ke"]`` if available.
        - May be a scalar (one KE for the whole cube -- an approximation,
          fine for a narrow energy window) or an array of length
          ``len(scan.z)`` (one KE per energy channel, for a wide window
          where KE varies non-negligibly across it).
    ``work_function_eV``: only used if you pass binding energies instead of
        kinetic energies for ``scan.z`` and want KE = hv - BE - work
        function; unused by default. Provided for convenience/consistency
        checks, not applied automatically.

    This function does not resample onto a rectilinear (kx, ky) grid -- kx
    is energy-dependent in general (kx = f(angle, KE)) and a proper
    rectilinear (kx, ky, E) volume requires per-slice interpolation. For a
    single representative slice this is usually a fine approximation; for
    quantitative work across a wide energy range, interpolate per-E-slice
    before treating this as a uniform-grid volume.
    """
    if scan.kind != "map":
        raise ValueError(f"to_kspace_cube expects kind=='map', got '{scan.kind}'")
    if kinetic_energy_eV is None:
        # 'MBS.center_ke' is the current namespaced key; 'center_ke' is the
        # older flat one, still accepted so existing scripts keep working.
        kinetic_energy_eV = scan.info.get("MBS.center_ke", scan.info.get("center_ke"))
        if kinetic_energy_eV is None:
            raise ValueError(
                "No kinetic_energy_eV given and neither scan.info['MBS.center_ke'] "
                "nor scan.info['center_ke'] is available in this file.")
    kx = deflector_angle_to_k(scan.x, kinetic_energy_eV)
    return kx, scan.k, scan.z, scan.value
