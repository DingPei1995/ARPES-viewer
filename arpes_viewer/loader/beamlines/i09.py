"""
loader/beamlines/i09.py
=======================
Diamond Light Source **I09** (SISA): the soft and hard X-ray branches'
EW4000 hemispherical analyser, and the **I09-2** momentum microscope
(delay-line detector, DLD). Written after the beamline's own Igor loader
(``I09_LoadData.ipf``), without a file from the beamline; check a real file
before relying on it.

What the Igor loader reads, and where
-------------------------------------
GDA writes its NeXus under ``/entry1`` (before GDA 9.38) or ``/entry``
(9.38 on); ``program_name`` (``"GDA 9.32.0"``) says which, and the scan
command moved from ``<entry>/scan_command`` to
``<entry>/diamond_scan/scan_command``.

=====================  ==================================================
what                   where
=====================  ==================================================
EW4000 regions         ``<entry>/instrument/ew4000/region_list`` names
                       them; each is a group ``<entry>/<region>`` with
                       ``image_data`` ``(*scan, angles, energies)``,
                       ``spectrum_data`` ``(*scan, energies)``, ``angles``
                       and ``energies``.
I09-2 DLD images       ``<entry>/instrument/<detector>/data``, the
                       detector being the last scan-command token followed
                       by a number (``... dld 1.0``); ``(*scan, y, x)``.
I09-2 DLD total        ``<entry>/instrument/dld_total/mcp_roi_total`` against
                       ``sample_bias`` or ``kenergy`` (of ``dld_total`` or
                       ``dld``).
XAS (drain current)    ``<entry>/sdc/data`` divided by ``<entry>/jI0/data``,
                       against ``<entry>/sdc/energy_demand`` (keV).
anything else scanned  ``<entry>/instrument/<name>/value`` for every name of
                       the scan command (the Igor loader's *Custom* and
                       *nixswr* buttons: a current, a reflectivity, against
                       a monochromator energy).
=====================  ==================================================

How they open
-------------
* An **EW4000 region** goes through :mod:`loader.formats.nexus_arpes`, as a
  Diamond I05 file does: a single spectrum is a ``cut``; one scanned motor a
  ``map`` (a polar or deflector angle convertible to k), a photon energy a
  ``kz_map`` (each spectrum referred to E_F by its own hv), two spatial
  motors (``smpmx``, ``smpmy``, ...) a ``spem_4d``. The scanned motors are
  the scan command's (``scan smpmx 0 1 0.1 ...``), read from the region's
  own group or ``instrument/<motor>/value``. A region with no image (a
  fixed or XPS-only region) opens as an ``edc``, one channel per scan point.
  The energy is the analyser's kinetic energy; a region recorded on the
  binding-energy scale is labelled so.
* The **DLD** stack opens as a ``map``: detector X and Y (pixels) against
  the scanned energy (``kenergy`` or ``sample_bias``), each energy a
  momentum image. A single image is a ``cut`` of Y against X. Calibrating the
  pixels to momentum is left to the user, as at the beamline. The Igor
  loader's hot-pixel, flat-field and binning buttons are processing, not
  reading: they are the program's own tools (detector corrections,
  arithmetic, rebinning).
* Curves (**DLD total**, **XAS**, a **scalar scan**) open as an ``edc``
  when the scanned axis is an energy, else an ``mdc``, with one channel per
  detector.

Every one-element dataset of the entry goes into ``info`` (the Igor
loader's *Explore* list), under its path below the entry.

The Igor procedures in ``I09_Extra.ipf`` (3-D rotation and curvature of a
momentum-microscope stack, VAMAS export) are analysis, not reading; the
program has its own curvature, symmetrisation and export.
"""
from __future__ import annotations

import os
import re
from itertools import product
from typing import Optional

import h5py
import numpy as np

from arpes_viewer.loader.formats.nexus_arpes import (Dim, Layout, NexusView,
                                                     build_scan, list_layout,
                                                     motor_role, text,
                                                     unit_text)
from arpes_viewer.loader.registry import Loader, register
from arpes_viewer.loader.scan import ENERGY_UNIT, HANDLES, KIND_LABELS, NxsScan, _scalarize

__all__ = ["DiamondI09Loader", "is_i09", "entry_root", "parse_scan_command",
           "list_i09", "load_i09"]

#: Separates a dataset's family from its own entry key in a listed entry:
#: ``"region:Au_4f"``, ``"region:Au_4f|point 2"``.
_SEP = "|"

#: Photon-energy scannables of I09: the soft branch's grating
#: monochromator in eV, the hard branch's crystal monochromators in keV.
_HV_EV = ("pgmenergy", "ienergy_ev", "energy_ev", "hv")
_HV_KEV = ("jenergy", "ienergy", "dcmenergy", "energy")
#: Energies of the momentum microscope: what it steps to scan the kinetic
#: energy.
_DLD_ENERGY = ("kenergy", "sample_bias", "kinetic_energy", "ke")
#: Words of a scan command that are not scannables or detectors.
_KEYWORDS = {"scan", "cscan", "rscan", "mscan", "cvscan", "pathscan", "gscan",
             "step", "axis", "pts", "points", "grid", "rect", "snake",
             "noconcurrent", "concurrent", "repeat", "staticscan"}
_SPATIAL = {"smpmx", "smpmy", "smpmz", "smpx", "smpy", "smpz", "sax", "say",
            "saz", "sx", "sy", "sz", "x", "y", "z"}
#: Region-group datasets that are never a scanned axis.
_REGION_DATA = {"image_data", "spectrum_data", "angles", "energies",
                "external_io_data", "excitation_energy", "time_per_channel"}


# --------------------------------------------------------------------------
# Recognising the file
# --------------------------------------------------------------------------
def entry_root(f: h5py.File) -> Optional[str]:
    """``"/entry1"`` (GDA before 9.38) or ``"/entry"`` (9.38 on), or None.

    Chosen by ``program_name`` as the Igor loader does, else by which of
    the two groups exists."""
    for root in ("/entry", "/entry1"):
        if f"{root}/program_name" in f:
            return root
    for root in ("/entry1", "/entry"):
        if isinstance(f.get(root), h5py.Group):
            return root
    return None


def gda_version(f: h5py.File, root: str) -> Optional[float]:
    """``9.32`` for ``"GDA 9.32.0"``, None when unrecorded."""
    path = f"{root}/program_name"
    if path not in f:
        return None
    match = re.search(r"(\d+)\.(\d+)", text(f[path][()]))
    return int(match.group(1)) + int(match.group(2)) / 100 if match else None


def _scan_command(f: h5py.File, root: str) -> str:
    for path in (f"{root}/diamond_scan/scan_command", f"{root}/scan_command"):
        if path in f and isinstance(f[path], h5py.Dataset):
            return text(f[path][()])
    return ""


def is_i09(f: h5py.File, path: str = "") -> bool:
    """A GDA file from I09: says so in ``instrument/name`` or its name
    (``i09-NNNNNN.nxs``, ``i09-2-NNNN.nxs``), or holds what only I09
    writes -- the EW4000's region list or the momentum microscope's DLD."""
    root = entry_root(f)
    if root is None or f"{root}/analyser" in f:
        return False          # Diamond I05's NXdata: that reader's
    name = ""
    if f"{root}/instrument/name" in f:
        try:
            name = text(f[f"{root}/instrument/name"][()]).casefold()
        except (OSError, TypeError):
            name = ""
    if name.startswith("i09"):
        return True
    base = os.path.basename(path or getattr(f, "filename", "")).casefold()
    if base.startswith("i09"):
        return True
    instrument = f"{root}/instrument"
    return any(f"{instrument}/{part}" in f for part in
               ("ew4000/region_list", "dld/data", "dld_total/mcp_roi_total"))


def branch(f: h5py.File, path: str = "") -> str:
    """``"I09-2"`` for the momentum microscope, else ``"I09"``."""
    root = entry_root(f) or "/entry1"
    name = ""
    if f"{root}/instrument/name" in f:
        name = text(f[f"{root}/instrument/name"][()]).casefold()
    base = os.path.basename(path or getattr(f, "filename", "")).casefold()
    if "i09-2" in name or base.startswith("i09-2"):
        return "I09-2"
    if any(k.startswith("dld") for k in _keys(f, f"{root}/instrument")):
        return "I09-2"
    return "I09"


def _keys(f: h5py.File, path: str) -> list:
    group = f.get(path)
    return list(group.keys()) if isinstance(group, h5py.Group) else []


# --------------------------------------------------------------------------
# The scan command
# --------------------------------------------------------------------------
def _is_number(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


def parse_scan_command(command: str) -> tuple:
    """``(scannables, detectors)`` of a GDA scan command, each a list of
    ``(name, numbers)``.

    As the Igor loader reads it: a name followed by two or more numbers
    (``start stop step``) is scanned, outer first; any other name is a
    detector, with its exposure if one follows (``dld 1.0``). Keywords
    (``scan``, ``mscan``, ``step`` ...) and paths are skipped.
    """
    tokens = [t for t in re.split(r"[\s,]+", str(command or "").strip()) if t]
    groups = []
    for token in tokens:
        if _is_number(token):
            if groups:
                groups[-1][1].append(float(token))
            continue
        groups.append((token, []))
    scannables, detectors = [], []
    for name, numbers in groups:
        folded = name.casefold()
        if folded in _KEYWORDS or "/" in name or "\\" in name \
                or not re.match(r"^[A-Za-z_][\w.]*$", name):
            continue
        (scannables if len(numbers) >= 2 else detectors).append((name, numbers))
    return scannables, detectors


def _detector(f: h5py.File, root: str, detectors) -> Optional[str]:
    """The DLD the scan command names (the last detector with an exposure,
    as the Igor loader picks it), or the one the file holds."""
    names = [n for n, numbers in detectors if numbers] + [n for n, _ in detectors]
    for name in reversed(names):
        if name.casefold().startswith("dld") and \
                f"{root}/instrument/{name}" in f:
            return name
    for name in ("dld", "dld_summed"):
        if f"{root}/instrument/{name}/data" in f:
            return name
    return None


# --------------------------------------------------------------------------
# Axis values
# --------------------------------------------------------------------------
def _numeric(f: h5py.File, path: str) -> Optional[np.ndarray]:
    item = f.get(path)
    if not isinstance(item, h5py.Dataset) or not np.issubdtype(item.dtype, np.number):
        return None
    try:
        return np.asarray(item[()], dtype=float)
    except (OSError, TypeError, ValueError):
        return None


def _unit(f: h5py.File, path: str) -> str:
    item = f.get(path)
    if item is None:
        return ""
    for key in ("units", "unit"):
        if key in item.attrs:
            return unit_text(item.attrs[key])
    return ""


def _motor_values(f: h5py.File, root: str, name: str, *groups) -> tuple:
    """``(values, unit)`` of a scannable, wherever GDA put it: in a data
    group beside the spectra, ``instrument/<name>/value`` (as the Igor
    loader reads it), or the older ``<entry>/<name>/<name>``."""
    paths = [f"{g}/{name}" for g in groups] + [
        f"{root}/instrument/{name}/value", f"{root}/instrument/{name}/{name}",
        f"{root}/{name}/{name}", f"{root}/{name}/value",
        f"{root}/before_scan/{name}/{name}"]
    for path in paths:
        values = _numeric(f, path)
        if values is not None:
            return values, _unit(f, path)
    return None, ""


def _stepped(values: np.ndarray, scan_shape: tuple):
    """``(dim, axis)`` of a motor recorded against a scan of
    ``scan_shape``: a vector along one dimension, or the whole grid (GDA
    records a nested scan's motors on the grid). None if it fits nowhere
    or does not move."""
    values = np.asarray(values, dtype=float)
    if values.shape == scan_shape and values.ndim > 1:
        spreads = [float(np.mean(np.ptp(values, axis=a))) for a in range(values.ndim)]
        dim = int(np.argmax(spreads))
        if spreads[dim] <= 1e-12 * max(1.0, float(np.max(np.abs(values)))):
            return None
        others = tuple(a for a in range(values.ndim) if a != dim)
        return dim, values.mean(axis=others)
    flat = values.reshape(-1)
    fits = [d for d, n in enumerate(scan_shape) if n == flat.size]
    if len(fits) == 1:
        return fits[0], flat
    return None


def _role(name: str, axis: np.ndarray, unit: str) -> tuple:
    """``(role, label, axis)``: the motor's role as nexus_arpes reads it,
    with I09's photon energies (keV on the hard branch, put in eV)."""
    folded = name.casefold()
    if folded in _HV_KEV:
        if unit.casefold() == "kev" or (axis.size and np.nanmax(np.abs(axis)) < 30):
            axis = axis * 1000.0
        return "photon_energy", f"Photon energy ({ENERGY_UNIT})", axis
    if folded in _HV_EV:
        return "photon_energy", f"Photon energy ({ENERGY_UNIT})", axis
    if folded in _SPATIAL:
        return "position", "", axis
    role, label = motor_role(name)
    if role == "photon_energy" and folded == "value":
        role, label = "other", None
    return role, label or "", axis


def _scan_dims(f: h5py.File, root: str, scan_shape: tuple, scannables,
               group: str = "") -> list:
    """One :class:`Dim` per scan dimension: the scan command's scannables
    matched to the dimensions they step, then any other vector of the data
    group that does; a dimension nothing matches is numbered."""
    found = {}
    names = [name for name, _numbers in scannables]
    if group and isinstance(f.get(group), h5py.Group):
        names += [k for k in f[group].keys() if k not in _REGION_DATA
                  and k not in names]
    for name in names:
        values, unit = _motor_values(f, root, name, *([group] if group else []))
        if values is None:
            continue
        stepped = _stepped(values, scan_shape)
        if stepped is None:
            continue
        dim, axis = stepped
        if dim in found or (axis.size > 1 and not np.ptp(axis) > 0):
            continue
        role, label, axis = _role(name, axis, unit)
        found[dim] = Dim(name, unit, axis, role, label)
    dims = []
    for d, n in enumerate(scan_shape):
        dims.append(found.get(d) or Dim("Scan point", "", np.arange(n, dtype=float),
                                        "index", "Scan point (index)"))
    return dims


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------
_INFO_LIMIT = 1500


def read_info(f: h5py.File, root: str) -> dict:
    """Every one-element dataset of the entry, by its path below it (the
    Igor loader's *Explore* list), with the usual short names besides."""
    info = {}

    def visit(name, item):
        if len(info) >= _INFO_LIMIT or not isinstance(item, h5py.Dataset):
            return
        if item.size != 1 or name.endswith("scan_command"):
            return
        try:
            value = _scalarize(item[()])
        except (OSError, TypeError, ValueError):
            return
        if isinstance(value, np.ndarray):
            value = value.reshape(-1)[0] if value.size else None
        if isinstance(value, (bytes, np.bytes_)):
            value = text(value)
        if hasattr(value, "item"):
            value = value.item()
        if value is None or (isinstance(value, str) and not value.strip()):
            return
        info[name.replace("/", ".")] = value

    group = f.get(root)
    if isinstance(group, h5py.Group):
        try:
            group.visititems(visit)
        except (OSError, RuntimeError):
            pass
    for key in ("title", "start_time", "end_time", "program_name",
                "experiment_identifier", "entry_identifier"):
        path = f"{root}/{key}"
        if path in f and isinstance(f[path], h5py.Dataset):
            value = text(f[path][()])
            if value:
                info[key] = value
    command = _scan_command(f, root)
    if command:
        info["scan_command"] = command
    for name in _HV_EV + _HV_KEV:
        values, unit = _motor_values(f, root, name)
        if values is not None and values.size == 1 and np.isfinite(values).all():
            _role_, _label, axis = _role(name, values.reshape(-1), unit)
            info.setdefault("photon_energy_eV", float(axis[0]))
    for path in (f"{root}/sample/temperature", f"{root}/instrument/lakeshore/value",
                 f"{root}/instrument/sample_temperature/value"):
        values = _numeric(f, path)
        if values is not None and values.size and np.isfinite(values.reshape(-1)[0]):
            info.setdefault("SampleTemperature_K", float(values.reshape(-1)[0]))
    return info


# --------------------------------------------------------------------------
# EW4000 regions
# --------------------------------------------------------------------------
def regions(f: h5py.File, root: str) -> list:
    """``[(region name, group path)]`` in the region list's order; without
    a list, every group of the entry that holds the analyser's data."""
    out = []
    listed = f.get(f"{root}/instrument/ew4000/region_list")
    if isinstance(listed, h5py.Dataset):
        raw = listed[()]
        names = [text(n) for n in np.asarray(raw).reshape(-1)] \
            if np.ndim(raw) else [n.strip() for n in text(raw).split(",")]
        for name in names:
            for group in (f"{root}/{name}", f"{root}/instrument/{name}"):
                if isinstance(f.get(group), h5py.Group) and any(
                        k in f[group] for k in ("image_data", "spectrum_data")):
                    out.append((name, group))
                    break
    if out:
        return out
    for parent in (root, f"{root}/instrument"):
        for key in _keys(f, parent):
            group = f"{parent}/{key}"
            if isinstance(f.get(group), h5py.Group) and any(
                    k in f[group] for k in ("image_data", "spectrum_data")) \
                    and key not in {name for name, _ in out}:
                out.append((key, group))
    return out


def _energy_mode(f: h5py.File, root: str, name: str, group: str) -> str:
    for path in (f"{group}/energy_mode", f"{root}/instrument/{name}/energy_mode",
                 f"{root}/instrument/ew4000/{name}/energy_mode"):
        if path in f and isinstance(f[path], h5py.Dataset):
            return text(f[path][()]).casefold()
    return "kinetic"


def region_layout(f: h5py.File, root: str, name: str, group: str,
                  path: str = "") -> Layout:
    """The :class:`Layout` of one region's image."""
    dataset = f[f"{group}/image_data"]
    shape = tuple(int(n) for n in dataset.shape)
    if len(shape) < 2:
        raise ValueError(f"region {name}: image of shape {shape}")
    energies = _numeric(f, f"{group}/energies")
    angles = _numeric(f, f"{group}/angles")
    n_angle, n_energy = shape[-2], shape[-1]
    if energies is None:
        energies = np.arange(n_energy, dtype=float)
    if angles is None:
        angles = np.arange(n_angle, dtype=float)
    angle = angles.reshape(-1, angles.shape[-1])[0] if angles.ndim > 1 else angles
    if angle.size != n_angle:
        angle = np.arange(n_angle, dtype=float)
    scan_shape = shape[:-2]
    per_point = energies.ndim > 1 and energies.shape[-1] == n_energy and \
        int(np.prod(energies.shape[:-1])) == int(np.prod(scan_shape)) and \
        int(np.prod(scan_shape)) > 1
    energy = energies.reshape(-1, energies.shape[-1])[0] if energies.ndim > 1 \
        else energies
    if energy.size != n_energy:
        energy = np.arange(n_energy, dtype=float)
    scannables, _detectors = parse_scan_command(_scan_command(f, root))
    dims = _scan_dims(f, root, scan_shape, scannables, group)
    point_energies = energies.reshape(scan_shape + (n_energy,)) if per_point else None
    if per_point and point_energies is not None:
        # The kinetic window follows the photon energy: the stepped
        # dimension is the photon energy whatever the motor is called.
        for d in range(len(scan_shape)):
            if scan_shape[d] > 1 and float(np.ptp(point_energies[..., 0], axis=d).max()) > 0 \
                    and dims[d].role != "photon_energy":
                hv, unit = None, ""
                for candidate in _HV_EV + _HV_KEV:
                    values, unit = _motor_values(f, root, candidate, group)
                    if values is not None and _stepped(values, scan_shape):
                        dim_, hv = _stepped(values, scan_shape)
                        _r, _l, hv = _role(candidate, hv, unit)
                        break
                if hv is not None:
                    dims[d] = Dim(dims[d].name, "eV", hv, "photon_energy",
                                  f"Photon energy ({ENERGY_UNIT})")
    info = read_info(f, root)
    info["i09.region"] = name
    mode = _energy_mode(f, root, name, group)
    info["i09.energy_mode"] = mode
    which = branch(f, path)
    return Layout(dataset=dataset, perm=tuple(range(len(shape))), dims=dims,
                  angle=angle, energy=energy,
                  facility=f"Diamond {which} (EW4000)",
                  prefix=f"{which.replace('-', '_')}_",
                  energy_scale="binding" if "bind" in mode else "kinetic",
                  energies=point_energies, info=info)


def _region_spectra(f: h5py.File, root: str, name: str, group: str) -> NxsScan:
    """A region with no image: its spectra as an EDC, a channel per scan
    point."""
    data = np.asarray(f[f"{group}/spectrum_data"][()], dtype=float)
    energies = _numeric(f, f"{group}/energies")
    n = data.shape[-1]
    if energies is None or energies.reshape(-1).size < n:
        energies = np.arange(n, dtype=float)
    energy = energies.reshape(-1, energies.shape[-1])[0] if energies.ndim > 1 else energies
    table = data.reshape(-1, n).T
    scan_shape = data.shape[:-1]
    names = []
    if table.shape[1] == 1:
        names = [name]
    else:
        scannables, _ = parse_scan_command(_scan_command(f, root))
        dims = _scan_dims(f, root, scan_shape, scannables, group)
        for index in product(*[range(k) for k in scan_shape]):
            names.append(", ".join(f"{dims[d].name} {dims[d].axis[i]:.4g}"
                                   for d, i in enumerate(index)))
    mode = _energy_mode(f, root, name, group)
    label = "Binding energy (eV)" if "bind" in mode else "Kinetic energy (eV)"
    return _curve("edc", energy, table, names, label, "Counts")


# --------------------------------------------------------------------------
# Curves
# --------------------------------------------------------------------------
def _curve(kind, x, table, names, x_label, value_label) -> NxsScan:
    x = np.asarray(x, dtype=float).reshape(-1)
    table = np.asarray(table, dtype=float).reshape(x.size, -1)
    order = np.argsort(x, kind="stable")
    scan = NxsScan(kind=kind, filename_prefix="I09_")
    scan.x = x[order]
    scan.y = np.arange(table.shape[1], dtype=float)
    scan.value = table[order]
    scan.labels = {"x": x_label, "y": "Channel"}
    scan.info["curve.channels"] = "|".join(str(n).replace("|", "/") for n in names)
    scan.info["curve.value_label"] = value_label
    return scan


def _first(f: h5py.File, paths) -> tuple:
    for path in paths:
        values = _numeric(f, path)
        if values is not None:
            return values, path
    return None, ""


def _dld_total(f: h5py.File, root: str) -> Optional[NxsScan]:
    """``mcp_roi_total`` against the kinetic energy (Igor: *Read 1D*)."""
    total, _ = _first(f, (f"{root}/instrument/dld_total/mcp_roi_total",
                          f"{root}/instrument/dld/mcp_roi_total"))
    if total is None:
        return None
    total = total.reshape(-1)
    energy, where = _first(f, (
        f"{root}/instrument/dld_total/sample_bias",
        f"{root}/instrument/dld/sample_bias",
        f"{root}/instrument/dld_total/kenergy",
        f"{root}/instrument/dld/kenergy",
        f"{root}/instrument/kenergy/value",
        f"{root}/instrument/sample_bias/value"))
    if energy is None or energy.reshape(-1).size != total.size:
        energy, where = np.arange(total.size, dtype=float), ""
    label = "Sample bias (V)" if "sample_bias" in where else \
        ("Kinetic energy (eV)" if where else "Scan point")
    scan = _curve("edc" if where else "mdc", energy.reshape(-1), total,
                  ["MCP total"], label, "Counts")
    scan.info["i09.energy_from"] = where.replace(root + "/", "")
    return scan


def _xas(f: h5py.File, root: str) -> Optional[NxsScan]:
    """The drain current over I0 against the photon energy (Igor: *XAS*)."""
    data = _numeric(f, f"{root}/sdc/data")
    energy = _numeric(f, f"{root}/sdc/energy_demand")
    if data is None or energy is None:
        return None
    data, energy = data.reshape(-1), energy.reshape(-1)
    if data.size != energy.size:
        return None
    i0 = _numeric(f, f"{root}/jI0/data")
    columns, names = [data], ["sdc"]
    if i0 is not None and i0.reshape(-1).size == data.size:
        i0 = i0.reshape(-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            columns = [np.where(i0 != 0, data / i0, np.nan), data, i0]
        names = ["sdc / I0", "sdc", "I0"]
    unit = _unit(f, f"{root}/sdc/energy_demand") or "keV"
    return _curve("edc", energy, np.column_stack(columns), names,
                  f"Photon energy ({unit})", "Drain current")


def _scalar_scan(f: h5py.File, root: str) -> Optional[NxsScan]:
    """Every detector of the scan command that recorded one number per
    point, against the first scannable (Igor: *Custom*, *nixswr*)."""
    scannables, detectors = parse_scan_command(_scan_command(f, root))
    if not scannables:
        return None
    name = scannables[0][0]
    axis, unit = _motor_values(f, root, name)
    if axis is None or axis.reshape(-1).size < 2:
        return None
    axis = axis.reshape(-1)
    columns, names = [], []
    for detector, _numbers in detectors:
        for path in (f"{root}/instrument/{detector}/value",
                     f"{root}/instrument/{detector}/{detector}",
                     f"{root}/{detector}/{detector}",
                     f"{root}/instrument/{detector}/data"):
            values = _numeric(f, path)
            if values is not None and values.reshape(-1).size == axis.size:
                columns.append(values.reshape(-1))
                names.append(detector)
                break
    if not columns:
        return None
    role, label, axis = _role(name, axis, unit)
    if not label:
        label = f"{name} ({unit})" if unit else name
    kind = "edc" if role == "photon_energy" or "energy" in name.casefold() else "mdc"
    return _curve(kind, axis, np.column_stack(columns), names, label, "Signal")


# --------------------------------------------------------------------------
# The momentum microscope's images
# --------------------------------------------------------------------------
def _dld_entries(f: h5py.File, root: str) -> list:
    """``[(key, kind label, name)]`` for the DLD image stack."""
    _scannables, detectors = parse_scan_command(_scan_command(f, root))
    detector = _detector(f, root, detectors)
    if detector is None:
        return []
    dataset = f.get(f"{root}/instrument/{detector}/data")
    if not isinstance(dataset, h5py.Dataset) or dataset.ndim < 2:
        return []
    shape = dataset.shape
    if len(shape) == 2:
        return [(f"dld:{detector}", KIND_LABELS["cut"], detector)]
    if len(shape) == 3:
        return [(f"dld:{detector}", KIND_LABELS["map"], detector)]
    outer = int(np.prod(shape[:-3]))
    return [(f"dld:{detector}{_SEP}point {i}", KIND_LABELS["map"],
             f"{detector} point {i}") for i in range(outer)]


def _dld_scan(f: h5py.File, root: str, detector: str, point: int = 0) -> NxsScan:
    dataset = f[f"{root}/instrument/{detector}/data"]
    shape = tuple(int(n) for n in dataset.shape)
    ny, nx = shape[-2], shape[-1]
    x = np.arange(nx, dtype=float)
    y = np.arange(ny, dtype=float)
    scan = NxsScan(kind="cut", filename_prefix="I09_2_")
    scan.info.update(read_info(f, root))
    scan.info["facility"] = "Diamond I09-2 (momentum microscope)"
    scan.info["nexus.dataset"] = dataset.name
    scan.info["i09.detector"] = detector
    scan.info["i09.pixels_note"] = (
        "detector pixels; calibrate them to momentum from a known feature")
    if len(shape) == 2:
        scan.x, scan.y = x, y
        scan.value = NexusView(dataset, (1, 0))
        scan.labels = {"x": "Detector X (px)", "y": "Detector Y (px)"}
        return scan
    scannables, _ = parse_scan_command(_scan_command(f, root))
    scan_shape = shape[:-2]
    dims = _scan_dims(f, root, scan_shape, scannables,
                      f"{root}/instrument/{detector}")
    energy_dim = dims[-1]
    if energy_dim.role == "index":
        for name in _DLD_ENERGY:
            for path in (f"{root}/instrument/{detector}/{name}",
                         f"{root}/instrument/dld_total/{name}",
                         f"{root}/instrument/{name}/value"):
                values = _numeric(f, path)
                if values is not None and values.reshape(-1).size == shape[-3]:
                    energy_dim = Dim(name, _unit(f, path), values.reshape(-1), "other")
                    break
            if energy_dim.role != "index":
                break
    folded = energy_dim.name.casefold()
    if folded == "sample_bias":
        z_label = "Sample bias (V)"
    elif folded in _DLD_ENERGY:
        z_label = f"Kinetic energy ({ENERGY_UNIT})"
    else:
        z_label = energy_dim.label
    nd = len(shape)
    fixed = {}
    if nd > 3:
        index = np.unravel_index(int(point), shape[:-3])
        fixed = {d: int(i) for d, i in enumerate(index)}
        for d, i in fixed.items():
            scan.fourd_info[dims[d].name] = f"{dims[d].axis[i]:.6g} {unit_text(dims[d].unit)}".strip()
    scan.kind = "map"
    scan.x, scan.k, scan.z = x, y, energy_dim.axis
    scan.value = NexusView(dataset, (nd - 1, nd - 2, nd - 3), fixed)
    scan.labels = {"x": "Detector X (px)", "k": "Detector Y (px)", "z": z_label}
    scan.info["axis0.role"] = "other"
    return scan


# --------------------------------------------------------------------------
# Listing and loading
# --------------------------------------------------------------------------
def list_i09(f: h5py.File, path: str) -> list:
    """Every dataset of an I09 file, one dict per row of the browser."""
    root = entry_root(f)
    base = os.path.splitext(os.path.basename(path))[0]
    title = text(f[f"{root}/title"][()]) if f"{root}/title" in f else None
    start = text(f[f"{root}/start_time"][()]) if f"{root}/start_time" in f else None
    out = []
    for name, group in regions(f, root):
        if "image_data" in f[group]:
            try:
                layout = region_layout(f, root, name, group, path)
            except Exception:                               # noqa: BLE001
                continue
            for row in list_layout(layout, f"{base} {name}", title, start):
                key = f"region:{name}"
                if row["entry"] != "entry1":
                    key += _SEP + row["entry"]
                out.append({**row, "entry": key})
        else:
            out.append({"entry": f"region:{name}", "kind": KIND_LABELS["edc"],
                        "name": f"{base} {name}", "title": title,
                        "start_time": start})
    for key, kind, name in _dld_entries(f, root):
        out.append({"entry": key, "kind": kind, "name": f"{base} {name}",
                    "title": title, "start_time": start})
    for key, reader, label in (("total", _dld_total, "MCP total"),
                               ("xas", _xas, "XAS"),
                               ("scalars", _scalar_scan, "scan")):
        if out and key == "scalars":
            continue        # the detectors are already read as images
        try:
            scan = reader(f, root)
        except Exception:                                   # noqa: BLE001
            scan = None
        if scan is not None:
            out.append({"entry": key, "kind": KIND_LABELS[scan.kind],
                        "name": f"{base} {label}", "title": title,
                        "start_time": start})
    return out


def load_i09(f: h5py.File, path: str, entry: str = None) -> NxsScan:
    root = entry_root(f)
    if root is None:
        raise ValueError(f"{path}: no GDA entry")
    if entry is None:
        listed = list_i09(f, path)
        if not listed:
            raise ValueError(f"{path}: nothing I09 writes was found in it")
        entry = listed[0]["entry"]
    family, _, rest = str(entry).partition(":")
    if family == "region":
        name, _, point = rest.partition(_SEP)
        group = dict(regions(f, root)).get(name)
        if group is None:
            raise KeyError(f"no region {name!r} in {path}")
        if "image_data" not in f[group]:
            scan = _region_spectra(f, root, name, group)
            scan.info.update(read_info(f, root))
        else:
            layout = region_layout(f, root, name, group, path)
            scan = build_scan(layout, point or None)
            if layout.energy_scale == "binding" and scan.kind != "kz_map":
                slot = "y" if scan.kind == "cut" else "z"
                scan.labels[slot] = "Binding energy (eV)"
        scan.info["i09.region"] = name
    elif family == "dld":
        detector, _, point = rest.partition(_SEP)
        index = int(point.split()[-1]) if point else 0
        scan = _dld_scan(f, root, detector, index)
    elif entry in ("total", "xas", "scalars"):
        reader = {"total": _dld_total, "xas": _xas, "scalars": _scalar_scan}[entry]
        scan = reader(f, root)
        if scan is None:
            raise KeyError(f"no {entry} data in {path}")
        scan.info.update(read_info(f, root))
    else:
        raise KeyError(f"no dataset {entry!r} in {path}")
    scan.info.setdefault("facility", f"Diamond {branch(f, path)}")
    version = gda_version(f, root)
    if version is not None:
        scan.info["gda_version"] = version
    return scan


class DiamondI09Loader(Loader):
    name = "Diamond I09 (EW4000, I09-2 momentum microscope)"
    description = ("NeXus .nxs files from I09 at Diamond (written after the "
                   "beamline's Igor loader): EW4000 regions as cuts, maps, "
                   "photon-energy and spatial scans; the I09-2 momentum "
                   "microscope's image stacks and MCP totals; XAS and other "
                   "scalar scans as curves.")
    patterns = ("*.nxs",)
    priority = 13

    def can_open(self, path: str) -> bool:
        try:
            with HANDLES.borrow(path) as f:
                return is_i09(f, path)
        except Exception:
            return False

    def list_entries(self, path: str) -> list:
        try:
            with HANDLES.borrow(path) as f:
                return list_i09(f, path)
        except Exception:
            return []

    def load(self, path: str, entry: str = None, progress=None):
        f = HANDLES.acquire(path)
        keep_open = False
        try:
            scan = load_i09(f, path, entry)
            if isinstance(scan.array(), NexusView):
                scan._h5file = f
                scan._h5path = path
                keep_open = True
            return scan
        finally:
            if not keep_open:
                HANDLES.release(path, f)


register(DiamondI09Loader())
