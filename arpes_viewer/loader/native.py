"""
loader/native.py
================
This program's own saved format: the one every derived dataset is written
in (see :mod:`loader.session`) and the one "Save..." produces -- writing it
(:func:`save_dataset`), reading an entry back (:func:`_parse_native`), and
the loader that recognises it.

The loader **never needs to be chosen**. The format marks its entries with
:data:`NATIVE_ATTR`, so recognising one is reading an attribute rather than
guessing from a layout. That is why its priority sits above every beamline
loader: a file this program wrote should never be mistaken for a beamline
file whose structure it happens to resemble, and reopening yesterday's
session must not ask the user which synchrotron it came from.

Listing and opening go through :func:`list_native` and :func:`load_native`.
A saved entry and an ANTARES entry can sit in one file, so both walk the
file's entries with the ANTARES reader's dispatcher, which hands each saved
entry back here.
"""
from __future__ import annotations

import os
from typing import Optional
import h5py
import numpy as np

from arpes_viewer.loader.scan import (HANDLES, LazyArray, NxsScan, _decode)

#: Marks an entry written by :func:`save_dataset`, so it is recognised on
#: the way back in regardless of what the user named it.
NATIVE_ATTR = "nxsloader_kind"
NATIVE_FORMAT_ATTR = "nxsloader_format"


#: 1: gzip-4, arrays written as whatever was handed in (in practice float64,
#:    since every caller promoted first), axes named axis_x/y/z only.
#: 2: gzip-4 **with the shuffle filter**, the array's own dtype preserved,
#:    and a fourth axis (axis_w) for a 4-D spatial scan. Measured on a
#:    120x941x96 map: 11.1 -> 8.8 MB at the same write time (shuffle
#:    re-orders the bytes of each value so that the high bytes of
#:    neighbouring numbers, which are nearly always equal, end up adjacent,
#:    which is what gzip is good at). Version 1 files still read.
NATIVE_FORMAT_VERSION = 2


#: How arrays are written. Chosen by measurement rather than by taste, on
#: ARPES-shaped data (smooth bands plus Poisson noise):
#:
#:   raw                 86.7 MB   write 0.04 s
#:   gzip 4              11.1 MB   write 0.70 s     <- version 1
#:   gzip 1 + shuffle     9.5 MB   write 0.47 s
#:   gzip 4 + shuffle     8.8 MB   write 0.70 s     <- version 2
#:   gzip 9 + shuffle     8.4 MB   write 9.87 s
#:   lzf + shuffle       13.5 MB   write 0.33 s
#:
#: Level 9 costs 14x the write time for 5% -- no. lzf is faster to write but
#: half as effective. Chunking is left to h5py: a hand-tuned "whole plane"
#: chunk reads constant-energy slices 4x faster but the orthogonal cuts 20x
#: slower, and the viewer does both, while h5py's own guess is within a few
#: per cent of the best balanced choice.
NATIVE_COMPRESSION = dict(compression="gzip", compression_opts=4,
                          shuffle=True, chunks=True)


def _first_string(f: h5py.File, path: str) -> Optional[str]:
    """A short string dataset's value, or None if absent/unreadable."""
    try:
        if path not in f:
            return None
        value = _decode(f[path][()])
        if isinstance(value, np.ndarray):
            value = value.reshape(-1)[0] if value.size else None
        return None if value is None else str(value).strip() or None
    except Exception:
        return None


def _parse_native(f: h5py.File, g: str) -> NxsScan:
    """Read back an entry written by :func:`save_dataset`.

    Deliberately simple and self-describing: the axes, the cube, the axis
    labels and the metadata are all stored under plain names, so nothing has
    to be inferred the way a beamline file's ``data_09`` does. That also
    means a saved k-map keeps its momentum axes labelled as momenta instead
    of being mistaken for angles.
    """
    grp = f[g]
    kind = _decode(grp.attrs[NATIVE_ATTR])
    if isinstance(kind, np.ndarray):
        kind = str(kind.reshape(-1)[0])
    kind = str(kind)

    scan = NxsScan(kind=kind, filename_prefix="")
    # Left on disk behind a LazyArray, and in the dtype it was written in:
    # a saved dataset is opened exactly like a beamline file, so a session's
    # worth of them can sit in the list without any of them being resident.
    # Axes are small and always read.
    scan.value = LazyArray(f[f"{g}/value"])
    scan.x = np.asarray(f[f"{g}/axis_x"][()], dtype=float)

    if kind == "spem_4d":
        # (x, y, k, E): the cube belongs in value4d, where the viewer looks
        # for it, and value mirrors it as MemoryData does.
        scan.y = np.asarray(f[f"{g}/axis_y"][()], dtype=float)
        scan.k = np.asarray(f[f"{g}/axis_z"][()], dtype=float)
        if f"{g}/axis_w" in f:
            scan.z = np.asarray(f[f"{g}/axis_w"][()], dtype=float)
        scan.value4d = scan.value
    elif f"{g}/axis_z" in f:
        # 3-D: a map or k-map (x, k, E), or a 1-D spatial scan (x, y, E).
        if kind == "spem_1d":
            scan.y = np.asarray(f[f"{g}/axis_y"][()], dtype=float)
        else:
            scan.k = np.asarray(f[f"{g}/axis_y"][()], dtype=float)
        scan.z = np.asarray(f[f"{g}/axis_z"][()], dtype=float)
    else:
        scan.y = np.asarray(f[f"{g}/axis_y"][()], dtype=float)

    labels = {}
    for axis in ("x", "y", "k", "z"):
        name = f"{g}/label_{axis}"
        if name in f:
            value = _first_string(f, name)
            if value:
                labels[axis] = value
    scan.labels = labels

    info_group = f"{g}/info"
    if info_group in f:
        for key, value in f[info_group].attrs.items():
            scan.info[key] = _decode(value)
    motors_group = f"{g}/motors"
    if motors_group in f:
        for key, value in f[motors_group].attrs.items():
            scan.fourd_info[key] = _decode(value)
    return scan


def save_dataset(path: str, datasets: "list[dict]", progress=None,
                 compress: bool = True) -> None:
    """Write datasets to a ``.nxs`` file this program can open again.

    ``datasets`` is a list of ``{"name", "kind", "axes", "labels", "value",
    "info", "motors"}`` dicts, one per entry; ``axes`` is ``(x, y)`` for a
    cut and ``(x, y, z)`` otherwise, up to four for a spatial scan. Several
    datasets go into one file as several top-level entries, exactly like a
    beamline file holding several measurements -- so saving a selection and
    reopening it gives the same rows back.

    The entries are marked with :data:`NATIVE_ATTR`, which is what
    :func:`_classify_entry` keys on, so the name of the entry is free to be
    whatever the user called the dataset, and a file written here is
    recognised on sight without anyone having to say which beamline it came
    from.

    ``progress`` is an optional ``callable(done, total, label)`` for a
    caller showing a progress bar; it is called once per dataset. Raising
    from it (which is how a Cancel button reports itself) aborts the write.

    The array is stored in **its own dtype**. Earlier versions wrote
    whatever the caller had promoted to float64, which doubled the file for
    data that arrived as float32 or as integer counts, and lost nothing by
    doing so.

    ``compress=False`` writes the array as it is, with no gzip filter: what
    the session folder's working copies use, since they are written on the
    GUI thread after every operation and deleted again at a normal close, so
    the seconds gzip costs on a large cube buy nothing.

    Returns the entry names it actually used, in the order given. They are
    not always the names asked for -- HDF5 group names cannot contain "/",
    and two datasets may be called the same thing -- and the caller needs
    the real ones to be able to point a list row at what was just written.
    """
    used = set()
    written = []
    total = len(datasets)
    if HANDLES.is_open(path):
        # Overwriting a file a viewer is reading from would pull the data out
        # from under it (and Windows refuses the write anyway, less clearly).
        raise OSError(
            f"{os.path.basename(path)} is open in a viewer (or listed and "
            f"being read); close what uses it, or save under another name")
    with h5py.File(path, "w") as f:
        for index, item in enumerate(datasets):
            if progress is not None:
                progress(index, total, str(item.get("name", "")))
            # HDF5 group names cannot contain '/', and two datasets may well
            # have been given the same name by the user.
            base = str(item["name"]).replace("/", "_").strip() or "dataset"
            name, n = base, 2
            while name in used:
                name, n = f"{base}_{n}", n + 1
            used.add(name)
            written.append(name)

            grp = f.create_group(name)
            grp.attrs[NATIVE_ATTR] = str(item["kind"])
            grp.attrs[NATIVE_FORMAT_ATTR] = NATIVE_FORMAT_VERSION
            grp.attrs["nxsloader_name"] = str(item["name"])

            axes = item["axes"]
            # axis_w is the fourth, for a spatial scan; the first three keep
            # their version-1 names so version-1 files stay readable.
            for axis_name, values in zip(("axis_x", "axis_y", "axis_z", "axis_w"),
                                         axes):
                grp.create_dataset(axis_name, data=np.asarray(values, dtype=float))
            value = np.asarray(item["value"])
            # A 0-d or tiny array cannot be chunked, and compressing it would
            # cost more in filter overhead than it saves.
            options = (dict(NATIVE_COMPRESSION)
                       if compress and value.size > 1024 else {})
            grp.create_dataset("value", data=value, **options)

            for axis, label in (item.get("labels") or {}).items():
                if label:
                    grp.create_dataset(f"label_{axis}", data=np.bytes_(str(label).encode()))

            info = grp.create_group("info")
            for key, val in (item.get("info") or {}).items():
                try:
                    info.attrs[str(key)] = val if isinstance(
                        val, (int, float, np.integer, np.floating)) else str(val)
                except (TypeError, ValueError):
                    info.attrs[str(key)] = str(val)
            motors = grp.create_group("motors")
            for key, val in (item.get("motors") or {}).items():
                try:
                    motors.attrs[str(key)] = float(val)
                except (TypeError, ValueError):
                    motors.attrs[str(key)] = str(val)
    return written

def list_native(path: str) -> "list[dict]":
    """Every openable entry of a file written here (see
    :func:`loader.beamlines.antares.list_datasets`)."""
    from arpes_viewer.loader.beamlines.antares import list_datasets
    return list_datasets(path)


def load_native(path: str, entry: str = None) -> NxsScan:
    """One entry of a file written here, as an :class:`NxsScan`."""
    from arpes_viewer.loader.beamlines.antares import load_soleil_nxs
    return load_soleil_nxs(path, entry=entry)


# Imported here, after everything above exists: importing the registry
# installs every loader, and the ANTARES one imports names from this module.
from arpes_viewer.loader.registry import Loader, register  # noqa: E402


class NativeLoader(Loader):
    name = "This program's own format"
    description = ("Datasets saved by this program, and everything in a "
                   "session folder. Detected automatically -- no need to "
                   "pick a beamline.")
    #: Saving here writes .nxs, but a file that has been renamed, or moved
    #: through a system that prefers .h5, is the same file and opens the same
    #: way -- the format is recognised by a marker inside it, not by its name.
    patterns = ("*.nxs", "*.h5", "*.hdf5")
    #: Above every beamline loader: this one *knows*, the others guess.
    priority = 100
    #: A saved dataset holds what someone chose to keep; never trimmed.
    trims_incomplete = False

    def can_open(self, path: str) -> bool:
        """True if any top-level entry carries the native marker."""
        try:
            with HANDLES.borrow(path) as f:
                return any(NATIVE_ATTR in f[name].attrs
                           for name in f.keys()
                           if isinstance(f[name], h5py.Group))
        except Exception:
            return False

    def list_entries(self, path: str) -> list:
        """The entries, each carrying the name the dataset was saved under.

        A beamline file's row is named after the file, because that is all
        there is to go on. A file written here knows better: the dataset had
        a name in the list when it was saved, and it is stored with it. That
        matters most for a session folder, whose filenames carry a counter
        and an extension that are this module's business and not the user's
        -- a recovered dataset should come back as "gold Fermi surface", not
        as "007-gold Fermi surface.nxs".
        """
        entries = list_native(path)
        try:
            with HANDLES.borrow(path) as f:
                for info in entries:
                    group = f.get(info.get("entry") or "")
                    if group is None:
                        continue
                    saved = group.attrs.get("nxsloader_name")
                    if isinstance(saved, bytes):
                        saved = saved.decode("utf-8", "replace")
                    if saved:
                        info["name"] = str(saved)
        except Exception:
            pass        # the names are a nicety; the entries are the point
        return entries

    def load(self, path: str, entry: str = None):
        # Deliberately no ``progress``: declaring it is what marks a reader
        # as one that expects to take long enough to need a progress bar,
        # and routes it through the worker thread. An HDF5 open is one call
        # into the library with nothing to report.
        return load_native(path, entry=entry)


register(NativeLoader())
