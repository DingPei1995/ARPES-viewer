"""
loader/beamlines/antares.py
===========================
SOLEIL ANTARES (nano-ARPES): its ``*.nxs`` (NeXus/HDF5) files, and the
loader that registers them.

Which raw axis is which
-----------------------
The scan arrays carry no axis names. Each raw HDF5 axis is matched to a
physical quantity **by length**, against the independently read axis
vectors (the actuator and scale datasets), and transposed into an explicit,
named order (:func:`loader.scan.align_and_transpose`). That holds unless two
axes have the same number of points, in which case it warns and picks one.
:func:`inspect_nxs` prints a file's structure to check a new kind of file.

Which entry, and which case
---------------------------
A file can hold more than one top-level entry (a real-space navigation
image recorded just before the k-space scan, both saved in the same file).
Which entry is parsed, and as which case, is decided by **what each entry
contains** (:func:`_classify_entry`) -- entry names such as ``img1_0001``
are sequential labels, not a guide to content. See :func:`list_datasets`
and the ``entry=`` parameter of :func:`load_soleil_nxs`. An entry written
by this program (:mod:`loader.native`) is recognised by its marker and read
by that module, so a file can hold both.

Kinds produced
--------------
- ``"spem_4d"``  : real-space scan, the full 4-D cube (x, y, k, E) and a
                   reduced 3-D preview. The nano-ARPES *imaging* mode.
- ``"spem_1d"``  : a real-space scan along one line (x, angle, E).
- ``"cut"``      : one E-vs-angle spectrum (deflector fixed).
- ``"map"``      : a deflector scan as a (deflector, slit angle, E) cube, the
                   raw material of a constant-energy map.
- ``"kz_map"``   : a photon-energy (PhD) scan, (hv, angle, E), assembled
                   from one single-frame entry per photon energy (case 6,
                   :func:`_parse_phd`).
- ``"unsupported"``: ``Scan2D_MBS_vs_PIX_PIY`` (case 1), not read.

Nothing here imports Qt.
"""
from __future__ import annotations

import re
import warnings
from typing import Optional
import h5py
import numpy as np

from arpes_viewer.loader.scan import (ANGLE_UNIT, ENERGY_UNIT, HANDLES,
                                      KIND_LABELS, LazyArray, LazyCube,
                                      NxsScan, _decode, _read, _read_opt,
                                      _scalarize, align_and_transpose,
                                      resolve_axis_order, scalar0,
                                      squeeze_to_1d)
from arpes_viewer.loader.native import (NATIVE_ATTR, _first_string,
                                        _parse_native)


# Entry names are sequential labels, not a guide to content, so cases are
# decided by what an entry contains (_classify_entry). This name table is
# only the fallback for case 1, which is not read and so has nothing to be
# detected by.
GROUP_NAME_TO_CASE = {
    "/Scan2D_MBS_vs_PIX_PIY": 1,
}


def _classify_entry(f: h5py.File, g: str) -> Optional[int]:
    """Determine which parsing case (2, 3 or 4) the entry at group path
    ``g`` actually contains, by checking which datasets exist inside it --
    robust to arbitrary/reused entry names. Returns None if nothing
    recognized (falls back to :data:`GROUP_NAME_TO_CASE` by name in that
    case, then to raising "unrecognized" if that also comes up empty)."""
    sd, traj = f"{g}/scan_data", f"{g}/scan_config/trajectory"

    # Case 5: written by this program's own "Save dataset" (see
    # save_dataset). Checked first because it is unambiguous -- the entry
    # says so in an attribute -- and because a saved k-map has axes that are
    # momenta, which no beamline layout would describe.
    try:
        if NATIVE_ATTR in f[g].attrs:
            return 5
    except (KeyError, AttributeError):
        pass

    # Case 2 (SPEM real-space scan): two independent spatial actuators
    # under scan_config/trajectory, plus the 4D-candidate cube dataset
    # (data_12 is read regardless of whether it turns out to be 4D or not
    # -- that decision happens inside _parse_case2).
    if f"{sd}/data_12" in f and traj in f:
        traj_grp = f[traj]
        actuators = [k for k in traj_grp.keys() if k.startswith("actuator_") and k.endswith("_1")]
        if len(actuators) >= 1 and f"{sd}/data_04" in f:
            return 2

    # Case 3/4 (deflector-angle scan): a single scan actuator living
    # directly under scan_data (NOT under scan_config/trajectory -- that
    # distinguishes it from case 2's spatial actuators).
    if f"{sd}/actuator_1_1" in f:
        has_case4 = all(f"{sd}/{d}" in f for d in
                         ("data_04", "data_05", "data_06", "data_07", "data_08", "data_09", "data_11"))
        has_case3 = all(f"{sd}/{d}" in f for d in
                         ("data_01", "data_02", "data_03", "data_04", "data_05", "data_06", "data_09"))
        if has_case4:
            return 4
        if has_case3:
            return 3

    # Case 6: one frame of a photon-energy (PhD) scan -- a group beside
    # ANTARES/User holding a single MBS image and its scales. See
    # _parse_phd for how a file of these becomes one kz map.
    if _phd_group(f, g) is not None:
        return 6

    return GROUP_NAME_TO_CASE.get(g)


def inclusive_range(start: float, step: float, stop: float) -> np.ndarray:
    """``start, start + step, ...`` up to and including ``stop`` (within
    floating-point tolerance), as the files' scale triplets mean. Defensively coerces its arguments to plain
    Python floats first -- see :func:`scalar0` for why that isn't always a
    no-op on real files."""
    start = float(np.ravel(start)[0]) if np.ndim(start) else float(start)
    step = float(np.ravel(step)[0]) if np.ndim(step) else float(step)
    stop = float(np.ravel(stop)[0]) if np.ndim(stop) else float(stop)
    if step == 0:
        return np.array([start], dtype=float)
    n = int(np.floor((stop - start) / step + 1e-9)) + 1
    n = max(n, 0)
    return start + step * np.arange(n)


# --------------------------------------------------------------------------
# Metadata fields deliberately NOT shown in the GUI's info table.
#
# These are read-able but were judged noise for day-to-day work at the
# beamline: fixed provenance strings, the User group, the parts of the
# machine record that never change, the thermocouples, and the scan_config
# summary (whose useful content is duplicated under Traj.*). Delete an entry
# here to bring a field back; nothing else needs changing.
# --------------------------------------------------------------------------
INFO_FIELDS_HIDDEN = {
    "title", "experiment_identifier", "run_cycle",
    "Machine.name", "Machine.probe", "Machine.type",
}


INFO_PREFIXES_HIDDEN = ("User.", "TC1.", "TC2.", "ScanCfg.")


def _hide_noisy_info(info: dict) -> dict:
    return {k: v for k, v in info.items()
            if k not in INFO_FIELDS_HIDDEN and not k.startswith(INFO_PREFIXES_HIDDEN)}


def spatial_unit_for(actuator_names) -> str:
    """Unit for the real-space scan axes, inferred from the actuator names
    recorded in ``scan_config/trajectory/actuator_*_1/name``.

    The piezo stage (PIX/PIY) moves in micrometres; the coarse sample
    stages are in millimetres, which is the default when the names don't
    identify a piezo axis. Detection is name-based because the files carry
    no unit attribute on these datasets.
    """
    if any(_antares_stage(n) in ("pix", "piy") for n in actuator_names):
        return "\u00b5m"
    joined = " ".join(str(n).lower() for n in actuator_names if n is not None)
    if any(tag in joined for tag in ("pix", "piy", "pi_x", "pi_y", "ex-pi", "ex/pi/")):
        return "\u00b5m"
    return "mm"


def _read_group_fields(f: h5py.File, group_path: str, prefix: str, out: dict,
                        skip=("controller_record",)):
    """Copy every scalar/string dataset directly under ``group_path`` into
    ``out`` as ``prefix.<field>``. Used instead of a hand-maintained field
    list so new fields the beamline adds show up automatically rather than
    being silently dropped.

    ``controller_record`` is skipped by default: it is a long Tango
    configuration blob present on every device group, useless in a summary
    table and long enough to swamp it."""
    if group_path not in f:
        return
    grp = f[group_path]
    if not isinstance(grp, h5py.Group):
        return
    for key in sorted(grp.keys()):
        if key in skip:
            continue
        item = grp[key]
        if not isinstance(item, h5py.Dataset):
            continue
        # Skip bulk data: metadata fields are scalars or short strings, and
        # a full detector frame in the info table would be useless anyway.
        if item.size > 16:
            continue
        try:
            out[f"{prefix}.{key}"] = _scalarize(_decode(item[()]))
        except (OSError, TypeError) as exc:
            out[f"{prefix}.{key}"] = f"<unreadable: {exc}>"


def _read_common_info(f: h5py.File, g: str) -> dict:
    """Read the experiment metadata worth showing in the GUI's info table.

    Field selection follows what actually exists in these files (verified
    against a real ``h5info`` dump of a SOLEIL ANTARES nano-ARPES file):
    NXentry-level provenance, the User group, the MBS analyzer settings,
    the monochromator/undulator/machine state, both thermocouples, and
    every sample/optics motor position. Device groups are read
    field-by-field via :func:`_read_group_fields` rather than through a
    hard-coded list, so fields added by future beamline-software versions
    appear automatically.
    """
    info = {}

    # -- NXentry-level provenance -------------------------------------
    for key in ("title", "experiment_identifier", "start_time", "end_time",
                "duration", "run_cycle"):
        value = _read_opt(f, f"{g}/{key}")
        if value is not None:
            info[key] = _scalarize(value)

    # -- who ran it ----------------------------------------------------
    _read_group_fields(f, f"{g}/User", "User", info)

    # -- analyzer (MBS) ------------------------------------------------
    _read_group_fields(f, f"{g}/ANTARES/MBSAcquisition_1", "MBS", info)

    # -- beamline: monochromator, undulators, machine ------------------
    _read_group_fields(f, f"{g}/ANTARES/i12-m-c04-op-mono1", "Mono", info)
    _read_group_fields(f, f"{g}/ANTARES/hu60", "HU60", info)
    _read_group_fields(f, f"{g}/ANTARES/hu256", "HU256", info)
    _read_group_fields(f, f"{g}/ANTARES/ans-ca-machinestatus", "Machine", info)

    # -- temperatures (both thermocouples, also in K)
    for tc, label in (("i12-m-cx1-ex-tc.1", "TC1"), ("i12-m-cx1-ex-tc.2", "TC2")):
        temp = _read_opt(f, f"{g}/ANTARES/{tc}/temperature")
        if temp is not None:
            temp = _scalarize(temp)
            info[f"{label}.temperature_C"] = temp
            info[f"{label}.temperature_K"] = temp + 273.15
            # The per-thermocouple rows are hidden as noise (they were asked
            # to be), but the sample temperature itself is not noise: the
            # Fermi-edge fit holds the temperature at it, so one plain row
            # survives with the first reading available.
            info.setdefault("SampleTemperature_K", temp + 273.15)
        tctype = _read_opt(f, f"{g}/ANTARES/{tc}/type")
        if tctype is not None:
            info[f"{label}.type"] = _scalarize(tctype)

    # -- scan configuration --------------------------------------------
    _read_group_fields(f, f"{g}/scan_config", "ScanCfg", info)
    traj = f"{g}/scan_config/trajectory"
    if traj in f and isinstance(f[traj], h5py.Group):
        for actuator in sorted(f[traj].keys()):
            _read_group_fields(f, f"{traj}/{actuator}", f"Traj.{actuator}", info)

    # -- convenience aliases ---------------------------------------------
    # (short names that scripts and earlier sessions read)
    aliases = {
        "PhotonEnergy": f"{g}/ANTARES/i12-m-c04-op-mono1/energy",
        "Grating": f"{g}/ANTARES/i12-m-c04-op-mono1/current_grating_name",
        "exitSlit": f"{g}/ANTARES/i12-m-c04-op-mono1/exit_slit_aperture",
        "resolution": f"{g}/ANTARES/i12-m-c04-op-mono1/resolution",
    }
    for alias, path in aliases.items():
        value = _read_opt(f, path)
        if value is not None:
            info[alias] = _scalarize(value)
    return _hide_noisy_info(info)


def _antares_stage(name) -> Optional[str]:
    """Which ANTARES real-space stage an actuator name is -- ``"st"``,
    ``"sz"``, ``"pix"`` or ``"piy"`` -- or None.

    The files record the Tango attribute, e.g.
    ``i12-m-cx1/ex/sample-mt_sz/position`` (coarse) or ``i12-m-cx1/ex/pi/x``
    (piezo); bare names ("ST", "PIX", "pi_y") are accepted as well. The name
    is split at ``/ _ - .`` and a trailing ``position`` dropped, so what is
    left ends in the stage.
    """
    n = str(name or "").strip().lower()
    tokens = [t for t in re.split(r"[/_\-. ]+", n) if t]
    while tokens and tokens[-1] in ("position", "value", "pos"):
        tokens.pop()
    if not tokens:
        return None
    last = tokens[-1]
    if last in ("st", "sz", "pix", "piy"):
        return last
    if last in ("x", "y") and len(tokens) > 1 and tokens[-2] == "pi":
        return "pi" + last
    return None


#: How ANTARES draws its two kinds of spatial scan, which is how the
#: beamline's own software shows them and so how its users read a map:
#:
#: coarse (ST horizontal, SZ vertical): ST decreases left to right, SZ
#:     increases top to bottom -- both axes reversed from the plotting
#:     default (increasing to the right and upwards);
#: fine (PIX horizontal, PIY vertical): PIX decreases left to right, PIY
#:     decreases top to bottom -- only the horizontal axis reversed.
#:
#: Keyed by stage; the value is whether that stage's axis is drawn reversed.
#: Used for ANTARES files only: data from anywhere else keeps the default.
ANTARES_REVERSED = {"st": True, "sz": True, "pix": True, "piy": False}


#: Which stage is drawn across the map; the other of the pair goes up it.
ANTARES_HORIZONTAL = ("st", "pix")


ANTARES_VERTICAL = ("sz", "piy")


def antares_spatial_orientation(first, second=None) -> dict:
    """How to draw an ANTARES spatial scan whose first and second scanned
    actuators are called ``first`` and ``second``, as metadata for the
    viewer (display only -- the data is never reordered):

    ``Spatial.swap_xy``   the first actuator is the *vertical* stage (the
                          coarse scans record SZ before ST), so the map is
                          drawn with the scan's Y across;
    ``Spatial.invert_x``  the horizontal *screen* axis runs large to small;
    ``Spatial.invert_y``  the vertical screen axis runs small to large going
                          down (see :data:`ANTARES_REVERSED`).

    A line scan (``second`` empty) gets only ``invert_x``, and only when it
    ran along ST or PIX. Empty when the names are not an ANTARES pair, so
    anything else is drawn the default way.
    """
    s1, s2 = _antares_stage(first), _antares_stage(second)
    if not second:
        if s1 in ANTARES_HORIZONTAL:
            return {"Spatial.invert_x": ANTARES_REVERSED[s1]}
        return {}
    if s1 in ANTARES_HORIZONTAL and s2 in ANTARES_VERTICAL:
        horizontal, vertical, swap = s1, s2, False
    elif s1 in ANTARES_VERTICAL and s2 in ANTARES_HORIZONTAL:
        horizontal, vertical, swap = s2, s1, True
    else:
        return {}
    return {"Spatial.swap_xy": swap,
            "Spatial.invert_x": ANTARES_REVERSED[horizontal],
            "Spatial.invert_y": ANTARES_REVERSED[vertical]}


#: What an ANTARES stage is called on an axis title.
ANTARES_STAGE_TITLES = {"st": "ST", "sz": "SZ", "pix": "PIX", "piy": "PIY"}


def _spatial_title(name, fallback: str) -> str:
    """``"SZ (mm)"`` / ``"PIX (\u00b5m)"`` for an ANTARES stage, else
    ``"<fallback> (<unit>)"`` with the unit guessed from the name."""
    stage = _antares_stage(name)
    unit = spatial_unit_for([name])
    return f"{ANTARES_STAGE_TITLES.get(stage, fallback)} ({unit})"


def _spatial_labels(f: h5py.File, g: str) -> "tuple[str, str, dict]":
    """Axis titles for the two real-space scan axes (the scan's own first
    and second actuator, which is how the arrays are ordered), plus what
    they were called in the file.

    An ANTARES stage is titled by its name and unit -- "ST (mm)", "SZ (mm)",
    "PIX (\u00b5m)", "PIY (\u00b5m)" -- and anything else "X"/"Y" with the
    unit guessed from the name. How the map is then *drawn* (which stage
    across, which way each runs) is left to the viewer, from the
    ``Spatial.*`` entries :func:`antares_spatial_orientation` adds: the
    arrays stay in the order the file has them.
    """
    traj = f"{g}/scan_config/trajectory"
    names = []
    if traj in f and isinstance(f[traj], h5py.Group):
        for actuator in sorted(f[traj].keys()):
            names.append(_read_opt(f, f"{traj}/{actuator}/name"))

    def clean(value):
        value = _scalarize(value)
        return str(_decode(value)).strip() if value is not None else ""

    first = clean(names[0]) if len(names) > 0 else ""
    second = clean(names[1]) if len(names) > 1 else ""

    detail = {"Spatial.X_actuator": first or "(unnamed)",
              "Spatial.Y_actuator": second or "(unnamed)"}
    detail.update(antares_spatial_orientation(first, second))
    return _spatial_title(first, "X"), _spatial_title(second, "Y"), detail


def _motor_minus_offset(f: h5py.File, g: str, motor: str):
    pos = _read_opt(f, f"{g}/ANTARES/{motor}/position")
    off = _read_opt(f, f"{g}/ANTARES/{motor}/offset")
    if pos is None:
        return None
    return _scalarize(pos) - (_scalarize(off) if off is not None else 0)


# Motor groups worth reporting, as (device name, friendly label): the sample
# stages, the zone plate, the OSA and the pinhole.
_MOTOR_GROUPS = [
    ("i12-m-cx1-ex-sample-mt_sn", "focus"),
    ("i12-m-cx1-ex-sample-mt_st", "roughY"),
    ("i12-m-cx1-ex-sample-mt_sz", "roughX"),
    ("i12-m-cx1-ex-sample-mt_srn", "SRn"),
    ("i12-m-cx1-ex-sample-mt_srz", "SRz"),
    ("i12-m-cx1-op-zp-mt_zs", "ZP_ZS"),
    ("i12-m-cx1-op-zp-mt_zx", "ZP_ZX"),
    ("i12-m-cx1-op-zp-mt_zz", "ZP_ZT"),
    ("i12-m-cx1-op-osa-mt_os", "OSA_S"),
    ("i12-m-cx1-op-osa-mt_ox", "OSA_X"),
    ("i12-m-cx1-op-osa-mt_oz", "OSA_Z"),
    ("i12-m-cx1-op-pin-mt_ps", "Pinhole_S"),
    ("i12-m-cx1-op-pin-mt_px", "Pinhole_X"),
    ("i12-m-cx1-op-pin-mt_pz", "Pinhole_Z"),
]


def _read_fourd_info(f: h5py.File, g: str) -> dict:
    """Motor positions, offset-corrected. Also the fine piezo stage
    (``i12-m-cx1-ex-pi/{x,y,z}``), which stores x/y/z directly with no
    separate offset dataset, so it is read as-is."""
    out = {}
    for device, label in _MOTOR_GROUPS:
        value = _motor_minus_offset(f, g, device)
        if value is not None:
            out[label] = _scalarize(value)

    for axis in ("x", "y", "z"):
        value = _read_opt(f, f"{g}/ANTARES/i12-m-cx1-ex-pi/{axis}")
        if value is not None:
            out[f"fine_{axis}"] = _scalarize(value)
    return out


def _find_actuator_group(f: h5py.File, trajectory_path: str) -> str:
    """The ``actuator_*_1`` subgroup under ``trajectory_path``, found by
    name, not by ordinal position."""
    grp = f[trajectory_path]
    candidates = [k for k in grp.keys() if k.startswith("actuator_") and k.endswith("_1")]
    if not candidates:
        raise KeyError(f"No actuator_*_1 group found under {trajectory_path}")
    if len(candidates) > 1:
        warnings.warn(
            f"Multiple actuator groups under {trajectory_path}: {candidates}; "
            f"using '{candidates[0]}'."
        )
    return f"{trajectory_path}/{candidates[0]}"


# --------------------------------------------------------------------------
# Case 2: real-space (SPEM) scan
# --------------------------------------------------------------------------
def _parse_case2(f: h5py.File, g: str, is_zpalign: bool) -> NxsScan:
    ds = f[f"{g}/scan_data/data_12"]
    if ds.ndim == 4:
        # NOT ds[()]: see LazyCube -- reading the whole cube here is what
        # made opening a spatial scan take many seconds.
        raw4d_shape = ds.shape

        traj = f"{g}/scan_config/trajectory"
        relxdelta = scalar0(_read(f, f"{traj}/actuator_1_1/delta"), "actuator_1_1/delta")
        relxfrom = scalar0(_read(f, f"{traj}/actuator_1_1/from"), "actuator_1_1/from")
        relxto = scalar0(_read(f, f"{traj}/actuator_1_1/to"), "actuator_1_1/to")

        relydelta = scalar0(_read(f, f"{traj}/actuator_2_1/delta"), "actuator_2_1/delta")
        relyfrom = scalar0(_read(f, f"{traj}/actuator_2_1/from"), "actuator_2_1/from")
        relyto = scalar0(_read(f, f"{traj}/actuator_2_1/to"), "actuator_2_1/to")

        escalemin = scalar0(f[f"{g}/scan_data/data_04"][()], "data_04 (escalemin)")
        escalemult = scalar0(f[f"{g}/scan_data/data_05"][()], "data_05 (escalemult)")
        escalemax = scalar0(f[f"{g}/scan_data/data_06"][()], "data_06 (escalemax)")
        xscalemin = scalar0(f[f"{g}/scan_data/data_07"][()], "data_07 (xscalemin)")
        xscalemult = scalar0(f[f"{g}/scan_data/data_08"][()], "data_08 (xscalemult)")
        xscalemax = scalar0(f[f"{g}/scan_data/data_09"][()], "data_09 (xscalemax)")

        x = inclusive_range(relxfrom, relxdelta, relxto)
        y = inclusive_range(relyfrom, relydelta, relyto)
        k = inclusive_range(xscalemin, xscalemult, xscalemax)
        z = inclusive_range(escalemin, escalemult, escalemax)

        perm = resolve_axis_order(raw4d_shape,
                                  {"y": len(y), "x": len(x), "k": len(k), "e": len(z)},
                                  ["y", "x", "k", "e"], what="data_12")
        value4d = LazyCube(ds, perm)

        # The reduced preview cubes the file already carries. data_11 is the
        # cube summed over energy and data_01 the cube summed over the slit
        # angle, so either one collapses to the spatial overview at a
        # thousandth of the data volume. They are kept as open datasets,
        # unread, and NxsData validates one against the real cube before
        # trusting it.
        previews = {}
        for name, axes in (("data_11", ("y", "x", "k")), ("data_01", ("y", "x", "e"))):
            path = f"{g}/scan_data/{name}"
            if path not in f:
                continue
            dset = f[path]
            try:
                lengths = {"y": len(y), "x": len(x), "k": len(k), "e": len(z)}
                previews[name] = (dset, resolve_axis_order(
                    dset.shape, {a: lengths[a] for a in axes}, list(axes), what=name))
            except (ValueError, KeyError) as exc:
                warnings.warn(f"{name}: not usable as a spatial preview ({exc})")
        value3d = None

        scan = NxsScan(kind="spem_4d",
                        filename_prefix="ZPAlign_" if is_zpalign else "SPEM_")
        scan.x, scan.y, scan.k, scan.z = x, y, k, z
        scan.value4d = value4d
        scan.value = value3d
        scan.previews = previews
        scan.info["SPEM_kmin"] = xscalemin
        scan.info["SPEM_kmax"] = xscalemax
        x_label, y_label, spatial_detail = _spatial_labels(f, g)
        scan.info.update(spatial_detail)
        scan.labels = {
            "x": x_label,
            "y": y_label,
            "k": f"Angle along slit ({ANGLE_UNIT})",
            "z": f"Energy ({ENERGY_UNIT})",
        }
        return scan

    # --- fallback: 1D spatial scan ("SPEM1D") ---
    raw3d = f[f"{g}/scan_data/data_11"][()]
    actuator_path = _find_actuator_group(f, f"{g}/scan_config/trajectory")
    relxdelta = scalar0(_read(f, f"{actuator_path}/delta"), "actuator/delta")
    relxfrom = scalar0(_read(f, f"{actuator_path}/from"), "actuator/from")
    relxto = scalar0(_read(f, f"{actuator_path}/to"), "actuator/to")

    escalemin = scalar0(f[f"{g}/scan_data/data_04"][()], "data_04 (escalemin)")
    escalemult = scalar0(f[f"{g}/scan_data/data_05"][()], "data_05 (escalemult)")
    escalemax = scalar0(f[f"{g}/scan_data/data_06"][()], "data_06 (escalemax)")
    xscalemin = scalar0(f[f"{g}/scan_data/data_07"][()], "data_07 (xscalemin)")
    xscalemult = scalar0(f[f"{g}/scan_data/data_08"][()], "data_08 (xscalemult)")
    xscalemax = scalar0(f[f"{g}/scan_data/data_09"][()], "data_09 (xscalemax)")

    x = inclusive_range(relxfrom, relxdelta, relxto)
    yaxis = inclusive_range(xscalemin, xscalemult, xscalemax)  # the slit axis, in .y
    z = inclusive_range(escalemin, escalemult, escalemax)

    value = align_and_transpose(raw3d, {"x": len(x), "y": len(yaxis), "e": len(z)}, ["x", "y", "e"])

    scan = NxsScan(kind="spem_1d", filename_prefix="SPEM1D_")
    scan.x, scan.y, scan.z = x, yaxis, z
    scan.value = value
    x_label, _y_label, spatial_detail = _spatial_labels(f, g)
    scan.info.update(spatial_detail)
    scan.labels = {
        "x": x_label,
        # .y holds the analyser slit axis for this branch
        "y": f"Angle along slit ({ANGLE_UNIT})",
        "z": f"Energy ({ENERGY_UNIT})",
    }
    return scan


def _best_effort_transpose_3d(arr: np.ndarray, axis_lengths: dict) -> np.ndarray:
    """The 3-D preview cube's axis order is not recorded; try the 3 most-likely orders against the known axis
    lengths and fall back to the raw array (with a warning) if none match
    cleanly."""
    names = list(axis_lengths.keys())
    if arr.ndim != 3:
        warnings.warn(f"Unexpected ndim={arr.ndim} for the 3D preview cube; returning raw array as-is.")
        return arr
    from itertools import permutations, combinations
    for combo in combinations(names, 3):
        for order in permutations(combo):
            if all(arr.shape[i] == axis_lengths[order[i]] for i in range(3)):
                return np.transpose(arr, list(range(3)))  # already in a matching order; identity transpose
    warnings.warn(
        f"Could not match the 3D preview cube's shape {arr.shape} to any "
        f"combination of known axis lengths {axis_lengths}; returning it "
        f"unmodified. Use inspect_nxs() to check axis order by hand."
    )
    return arr


# --------------------------------------------------------------------------
# Case 3 / 4: deflector-angle scan (k-space "Cut" or "Map")
# --------------------------------------------------------------------------
def _parse_case34(f: h5py.File, g: str, e_idx: tuple, x_idx: tuple, v_idx: str) -> NxsScan:
    """``e_idx``/``x_idx`` are the ('data_NN','data_NN','data_NN') triplets
    for (escale) and (xscale) that differ between case 3 (01-03 / 04-06) and
    case 4 (04-06 / 07-09); ``v_idx`` is the value dataset name (data_09 /
    data_11)."""
    deflx = squeeze_to_1d(f[f"{g}/scan_data/actuator_1_1"][()], "actuator_1_1 (deflx)")

    escalemin = scalar0(f[f"{g}/scan_data/{e_idx[0]}"][()], f"{e_idx[0]} (escalemin)")
    escalemult = scalar0(f[f"{g}/scan_data/{e_idx[1]}"][()], f"{e_idx[1]} (escalemult)")
    escalemax = scalar0(f[f"{g}/scan_data/{e_idx[2]}"][()], f"{e_idx[2]} (escalemax)")
    xscalemin = scalar0(f[f"{g}/scan_data/{x_idx[0]}"][()], f"{x_idx[0]} (xscalemin)")
    xscalemult = scalar0(f[f"{g}/scan_data/{x_idx[1]}"][()], f"{x_idx[1]} (xscalemult)")
    xscalemax = scalar0(f[f"{g}/scan_data/{x_idx[2]}"][()], f"{x_idx[2]} (xscalemax)")

    escale = inclusive_range(escalemin, escalemult, escalemax)
    xscale = inclusive_range(xscalemin, xscalemult, xscalemax)

    # The dataset, not its contents: the axis order is worked out from the
    # *shape*, which costs nothing to ask for, and the numbers are then left
    # on disk behind a LazyCube. A deflector map is tens to hundreds of MB
    # and reading it whole here was the largest single allocation the
    # program made -- for a view that only ever shows one slice at a time.
    raw_dataset = f[f"{g}/scan_data/{v_idx}"]

    # On real files this comes both as a bare 2D (k,E) array for a true
    # single-position Cut *and* as a 3D (scan_points, k, E) array with
    # scan_points==1 even for a single position (the acquisition software
    # apparently doesn't special-case a 1-point scan) -- handle both rather
    # than assuming a 2-D shape.
    if raw_dataset.ndim == 2:
        perm = resolve_axis_order(raw_dataset.shape,
                                  {"k": len(xscale), "e": len(escale)},
                                  ["k", "e"], what="array")
        value = LazyCube(raw_dataset, tuple(perm))
    elif raw_dataset.ndim == 3:
        perm = resolve_axis_order(
            raw_dataset.shape,
            {"deflx": deflx.size, "k": len(xscale), "e": len(escale)},
            ["deflx", "k", "e"], what="array")
        value3d = LazyCube(raw_dataset, tuple(perm))
        # One deflector position is a Cut, and a Cut is small enough that
        # keeping it on disk buys nothing; read that one frame now.
        value = value3d[0] if deflx.size == 1 else value3d
    else:
        raise ValueError(
            f"{v_idx}: unexpected ndim={raw_dataset.ndim} (shape={raw_dataset.shape}); "
            f"expected 2 (bare Cut) or 3 (scan_points, k, E). Use inspect_nxs() to check."
        )

    if deflx.size == 1:
        scan = NxsScan(kind="cut", filename_prefix="Cut_")
        scan.x, scan.y = xscale, escale
        scan.value = value
        scan.labels = {
            "x": f"Angle along slit ({ANGLE_UNIT})",
            "y": f"Energy ({ENERGY_UNIT})",
        }
        # The one deflector position the cut was taken at. It is not an axis
        # here -- there is only one of it -- but it is half the geometry a
        # k conversion of this cut needs (the other half being where Gamma
        # sits), so it is kept rather than dropped with the axis.
        scan.info["DeflectorAngle_deg"] = float(deflx[0])
        return scan

    # multiple deflector positions -> 3D (deflx, k, E) map
    scan = NxsScan(kind="map", filename_prefix="Map_")
    scan.x, scan.k, scan.z = deflx, xscale, escale
    scan.value = value
    scan.labels = {
        "x": f"Angle, deflector ({ANGLE_UNIT})",
        "k": f"Angle along slit ({ANGLE_UNIT})",
        "z": f"Energy ({ENERGY_UNIT})",
    }
    return scan


# --------------------------------------------------------------------------
# Photon-energy dependent scans (PhD)
# --------------------------------------------------------------------------
#: An ANTARES photon-energy scan is not one entry with a scanned axis, the
#: way a deflector map is. It is one top-level entry *per photon energy* --
#: ``Phd_0002``, ``Phd_0003``, ... -- each holding a single MBS frame in a
#: group of its own (``MBS_0_0``, ``MBS_0_1``, ...) beside the usual
#: ``ANTARES`` and ``User`` trees, with the frame's own scales and the
#: photon energy it was taken at::
#:
#:     /Phd_0002/MBS_0_0/Image32_1       (angle, energy) int32
#:     /Phd_0002/MBS_0_0/Escale_Min_1, Escale_Mult_1, Escale_Max_1
#:     /Phd_0002/MBS_0_0/Xscale_Min_1, Xscale_Mult_1, Xscale_Max_1
#:     /Phd_0002/MBS_0_0/hv, Theta, Phi, PI-X, PI-Y, PI-Z
#:
#: The first entry of a real file (``Phd_0001``) holds only the beamline
#: state and no frame, so "is this a PhD entry" is decided by the frame
#: being there, not by the name. The browser lists the frames of a file as
#: one ``kz_map`` under the entry name :data:`PHD_WILDCARD` appended to their
#: shared prefix (``"Phd_*"``); each frame can still be opened on its own,
#: by its own name, as a cut.
PHD_IMAGE = "Image32_1"


PHD_WILDCARD = "*"


#: What the analyser work function is taken to be when a PhD scan's energy
#: axis is kinetic and has to be referred to the Fermi level. The files do
#: not record one. It is written into the scan's info as
#: ``work_function_eV``, which the k_z conversion reads back, so the two
#: steps cannot disagree; a wrong value is a rigid energy shift, which the
#: Fermi-edge tools correct.
PHD_WORK_FUNCTION_EV = 4.5


def _phd_group(f: h5py.File, g: str) -> Optional[str]:
    """The group under entry ``g`` holding a single MBS frame, or None."""
    try:
        entry = f[g]
    except KeyError:
        return None
    if not isinstance(entry, h5py.Group):
        return None
    for name in entry.keys():
        if name in ("ANTARES", "User", "scan_data", "scan_config"):
            continue
        sub = entry.get(name)
        if (isinstance(sub, h5py.Group) and PHD_IMAGE in sub
                and "Escale_Min_1" in sub and "Xscale_Min_1" in sub):
            return f"{g}/{name}"
    return None


def _phd_prefix(names) -> str:
    """``["Phd_0002", "Phd_0003"]`` -> ``"Phd_"``: the shared name with its
    running number taken off."""
    stems = {re.sub(r"\d+$", "", name) for name in names}
    return stems.pop() if len(stems) == 1 else "PhD_"


def phd_entries(f: h5py.File) -> "list[str]":
    """The top-level entries of ``f`` that are one frame of a PhD scan, in
    file order."""
    return [name for name in f.keys()
            if _classify_entry(f, "/" + name) == 6]


def _phd_hv(f: h5py.File, g: str, mbs: str) -> float:
    """The photon energy one PhD frame was taken at: the frame's own record
    of it, else the monochromator's."""
    for path in (f"{mbs}/hv", f"{g}/ANTARES/i12-m-c04-op-mono1/energy"):
        if path in f:
            try:
                return scalar0(f[path][()], path)
            except (ValueError, TypeError):
                continue
    return float("nan")


def _phd_frame_axes(f: h5py.File, mbs: str):
    """``(dataset, perm, angle, energy)`` for one frame: the energy and
    slit axes from its scales, and which raw axis of the image is which.

    The scales are ``min:mult:max``, and that range can come out one point
    longer or shorter than the image by rounding, so the image's own
    lengths decide the axis length and the scales only say which is which
    and where they start.
    """
    def scale(prefix):
        lo = scalar0(f[f"{mbs}/{prefix}_Min_1"][()], f"{prefix}_Min_1")
        step = scalar0(f[f"{mbs}/{prefix}_Mult_1"][()], f"{prefix}_Mult_1")
        hi = scalar0(f[f"{mbs}/{prefix}_Max_1"][()], f"{prefix}_Max_1")
        return lo, step, len(inclusive_range(lo, step, hi))

    dataset = f[f"{mbs}/{PHD_IMAGE}"]
    if dataset.ndim != 2:
        raise ValueError(f"{mbs}/{PHD_IMAGE}: expected a 2-D frame, got "
                         f"shape {dataset.shape}")
    e0, de, ne = scale("Escale")
    x0, dx, nx = scale("Xscale")
    shape = dataset.shape
    as_stored = abs(shape[0] - nx) + abs(shape[1] - ne)
    swapped = abs(shape[0] - ne) + abs(shape[1] - nx)
    perm = (0, 1) if as_stored <= swapped else (1, 0)
    n_angle, n_energy = shape[perm[0]], shape[perm[1]]
    angle = x0 + dx * np.arange(n_angle)
    energy = e0 + de * np.arange(n_energy)
    return dataset, perm, angle, energy


def _resample_energy(frame: np.ndarray, source: np.ndarray,
                     target: np.ndarray) -> np.ndarray:
    """Linear resampling of ``frame`` (angle, energy) from the evenly
    stepped ``source`` energy axis onto ``target``, which lies inside it."""
    step = source[1] - source[0] if source.size > 1 else 1.0
    position = (target - source[0]) / step
    position = np.clip(position, 0, source.size - 1)
    low = np.minimum(np.floor(position).astype(int), source.size - 2)
    low = np.maximum(low, 0)
    weight = (position - low).astype(frame.dtype)
    high = np.minimum(low + 1, source.size - 1)
    return frame[:, low] * (1 - weight) + frame[:, high] * weight


def _parse_phd(f: h5py.File, names: "list[str]", progress=None) -> NxsScan:
    """Assemble the PhD frames ``names`` into one (hv, angle, energy) cube.

    Each frame is measured at its own photon energy, so the same kinetic
    energy is a different state in each, and a cube has only one energy
    axis. When the frames' axes are kinetic (they lie near hv, not near
    zero) each is referred to the Fermi level by its own photon energy,
    ``E - E_F = E_kin - hv + W``, with ``W`` = :data:`PHD_WORK_FUNCTION_EV`;
    an axis that is already a binding energy is used as it is. If the
    referred windows coincide the frames are stacked untouched; otherwise
    they are resampled, linearly and along energy only, onto the range all
    of them cover.
    """
    frames = []
    for position, name in enumerate(names):
        g = "/" + name
        if progress is not None:
            progress(position, len(names), name)
        mbs = _phd_group(f, g)
        dataset, perm, angle, energy = _phd_frame_axes(f, mbs)
        frame = np.transpose(np.asarray(dataset[()], dtype=np.float32), perm)
        frames.append({
            "entry": name, "frame": frame, "angle": angle, "energy": energy,
            "hv": _phd_hv(f, g, mbs),
            "theta": _read_opt(f, f"{mbs}/Theta"),
            "phi": _read_opt(f, f"{mbs}/Phi"),
        })

    shapes = {item["frame"].shape for item in frames}
    if len({shape[0] for shape in shapes}) != 1:
        raise ValueError(
            f"the frames of this photon-energy scan do not all have the same "
            f"number of angles ({sorted(shapes)}); they cannot be one cube")
    frames.sort(key=lambda item: item["hv"])
    hv = np.asarray([item["hv"] for item in frames], dtype=float)
    angle = frames[0]["angle"]

    notes = {}
    kinetic = bool(np.all(np.isfinite(hv))) and all(
        np.median(item["energy"]) > 0.5 * item["hv"] for item in frames)
    if kinetic:
        referred = [item["energy"] - item["hv"] + PHD_WORK_FUNCTION_EV
                    for item in frames]
        energy_label = f"E - E_F ({ENERGY_UNIT})"
        notes["work_function_eV"] = PHD_WORK_FUNCTION_EV
        notes["antares.energy_reference"] = (
            f"each frame referred by its own hv: E_kin - hv + "
            f"{PHD_WORK_FUNCTION_EV:g} eV (assumed work function)")
    else:
        referred = [item["energy"] for item in frames]
        energy_label = f"Energy ({ENERGY_UNIT})"
        notes["antares.energy_reference"] = "as recorded"

    first = referred[0]
    step = abs(first[1] - first[0]) if first.size > 1 else 1.0
    same = all(axis.size == first.size
               and np.max(np.abs(axis - first)) < 0.01 * step
               for axis in referred)
    if same:
        energy = first
        cube = np.stack([item["frame"] for item in frames], axis=0)
    else:
        low = max(float(axis.min()) for axis in referred)
        high = min(float(axis.max()) for axis in referred)
        if high <= low:
            raise ValueError(
                "the energy windows of this photon-energy scan's frames do "
                "not overlap once referred to the Fermi level, so there is "
                "no energy range common to all of them")
        energy = low + step * np.arange(int(np.floor((high - low) / step
                                                     + 1e-9)) + 1)
        cube = np.empty((len(frames), angle.size, energy.size),
                        dtype=np.float32)
        for index, (item, axis) in enumerate(zip(frames, referred)):
            if axis[0] > axis[-1]:
                axis, frame = axis[::-1], item["frame"][:, ::-1]
            else:
                frame = item["frame"]
            cube[index] = _resample_energy(frame, axis, energy)
        notes["antares.energy_resampled"] = (
            f"frames resampled onto their common range, "
            f"{energy[0]:.4g} to {energy[-1]:.4g} eV")

    varies = bool(np.all(np.isfinite(hv))) and np.ptp(hv) > 1e-6
    scan = NxsScan(kind="kz_map" if varies else "map",
                   filename_prefix="PhD_")
    if varies:
        stepped = hv
        if hv.size > 2:
            # The monochromator reads back where it stopped, not the even
            # step that was asked for; straighten it when it is plainly a
            # jittered even scan, since the viewers place rows evenly anyway.
            index = np.arange(hv.size, dtype=float)
            slope, intercept = np.polyfit(index, hv, 1)
            straight = index * slope + intercept
            if np.max(np.abs(straight - hv)) < 0.25 * abs(slope):
                stepped = straight
        scan.x = stepped
        scan.labels = {"x": f"Photon energy ({ENERGY_UNIT})"}
        scan.info["axis0.role"] = "photon_energy"
    else:
        scan.x = np.arange(1, len(frames) + 1, dtype=float)
        scan.labels = {"x": "Index (cut)"}
        scan.info["axis0.role"] = "other"
    scan.k, scan.z = angle, np.asarray(energy, dtype=float)
    scan.value = cube
    scan.labels.update({"k": f"Angle along slit ({ANGLE_UNIT})",
                        "z": energy_label})

    scan.info.update(_read_common_info(f, "/" + frames[0]["entry"]))
    scan.info.update(notes)
    scan.info["antares.phd_members"] = len(frames)
    scan.info["antares.phd_entries"] = [item["entry"] for item in frames]
    scan.info["antares.axis0_measured"] = hv
    if varies:
        scan.info["PhotonEnergy"] = f"{hv.min():g} to {hv.max():g}"
        scan.info["antares.photon_energy_range_eV"] = \
            f"{hv.min():g} to {hv.max():g}"
    for key in ("theta", "phi"):
        values = [item[key] for item in frames]
        if all(value is not None for value in values):
            values = np.asarray([_scalarize(np.asarray(value))
                                 for value in values], dtype=float)
            scan.info[f"antares.{key}_deg"] = (
                float(values[0]) if np.ptp(values) < 1e-6 else values)
    if progress is not None:
        progress(len(names), len(names), "")
    return scan


def _parse_phd_frame(f: h5py.File, g: str) -> NxsScan:
    """One PhD frame on its own, as a cut."""
    mbs = _phd_group(f, g)
    dataset, perm, angle, energy = _phd_frame_axes(f, mbs)
    scan = NxsScan(kind="cut", filename_prefix="Cut_")
    scan.x, scan.y = angle, energy
    scan.value = np.transpose(np.asarray(dataset[()], dtype=np.float32), perm)
    scan.labels = {"x": f"Angle along slit ({ANGLE_UNIT})",
                   "y": f"Energy ({ENERGY_UNIT})"}
    _read_group_fields(f, mbs, "MBS", scan.info)
    return scan


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def _entry_kind(f: h5py.File, g: str) -> Optional[str]:
    """Label one entry: "SPEM", "Cut", "Map", or None if unrecognised.

    Reads only the entry's structure and the *shape* of the deflector
    actuator -- never a data array -- so a directory of multi-GB scans can
    be labelled instantly.
    """
    case = _classify_entry(f, g)
    if case == 5:
        # A dataset this program saved; it states its own kind, which may be
        # one no beamline layout produces (a converted k_map).
        kind = _decode(f[g].attrs.get(NATIVE_ATTR, ""))
        if isinstance(kind, np.ndarray):
            kind = str(kind.reshape(-1)[0])
        return KIND_LABELS.get(str(kind), str(kind) or None)
    if case == 2:
        return "SPEM"
    if case == 6:
        return "Cut"
    if case in (3, 4):
        # Cut vs Map is decided by how many deflector positions were
        # scanned; the shape alone answers that, no data needed.
        actuator = f.get(f"{g}/scan_data/actuator_1_1")
        if actuator is None:
            return None
        n_positions = int(np.prod(actuator.shape)) if actuator.shape else 1
        return "Cut" if n_positions <= 1 else "Map"
    return None


def list_datasets(path: str) -> "list[dict]":
    """Every independently-openable dataset in a ``.nxs`` file.

    A single file routinely holds several measurements -- up to six Cuts or
    Maps recorded one after another, each a complete top-level NeXus entry
    with its own ``scan_data``. They are separate measurements that happen
    to share a file, so the browser lists one row per entry and opening one
    opens only that entry.

    Returns a list of dicts, in file order, with keys:

    ``entry``       the NeXus group name, e.g. ``"DeflX_0003"``
    ``kind``        "SPEM" / "Cut" / "Map"
    ``title``       the entry's own ``title``, if it has one
    ``start_time``  when it was recorded, if recorded

    Entries whose layout is not recognised are skipped, and an unreadable
    file yields an empty list rather than raising -- a browser listing must
    not fail because of one bad file.
    """
    out = []
    try:
        with HANDLES.borrow(path) as f:
            phd = phd_entries(f)
            for name in f.keys():
                g = "/" + name
                if len(phd) > 1 and name in phd:
                    # The frames of a photon-energy scan are one
                    # measurement: listed once, where the first one is.
                    if name == phd[0]:
                        out.append(_phd_listing(f, phd))
                    continue
                try:
                    kind = _entry_kind(f, g)
                except Exception:
                    kind = None
                if kind is None:
                    continue
                out.append({
                    "entry": name,
                    "kind": kind,
                    "title": _first_string(f, f"{g}/title"),
                    "start_time": _first_string(f, f"{g}/start_time"),
                })
    except Exception:
        return []
    return out


def _phd_listing(f: h5py.File, names: "list[str]") -> dict:
    """The one browser row for the PhD frames ``names``: a ``kz map``
    when the photon energy was stepped, a plain map of cuts when it was
    not. Reads only the scalar ``hv`` of each frame."""
    hv = [_phd_hv(f, "/" + name, _phd_group(f, "/" + name)) for name in names]
    varies = all(np.isfinite(hv)) and np.ptp(hv) > 1e-6
    g = "/" + names[0]
    return {
        "entry": _phd_prefix(names) + PHD_WILDCARD,
        "kind": KIND_LABELS["kz_map"] if varies else KIND_LABELS["map"],
        "title": _first_string(f, f"{g}/title"),
        "start_time": _first_string(f, f"{g}/start_time"),
    }


def probe_kind(path: str) -> str:
    """The kind of a file's *default* entry (see :func:`_pick_entry`), for
    callers that want one label per file. A browser listing wants
    :func:`list_datasets` instead, which enumerates every entry."""
    try:
        with HANDLES.borrow(path) as f:
            top_level = list(f.keys())
            if not top_level:
                return "unknown"
            return _entry_kind(f, _pick_entry(f, path, top_level)) or "unknown"
    except Exception:
        return "unknown"


def list_entries(path: str) -> "list[tuple[str, Optional[int]]]":
    """List every top-level NeXus entry in ``path`` as ``(group_name, case)``
    pairs (``case`` is ``None`` if the entry's content doesn't match any
    known structure). Real SOLEIL files can contain *more than one*
    top-level entry in a single .nxs file -- e.g. a real-space navigation
    image (case 2) recorded right before the actual deflector-angle map
    (case 3/4) that the file is "about", or a stale/incomplete entry left
    over from an aborted acquisition. Use this to see what's really in a
    file before calling :func:`load_soleil_nxs` with an explicit ``entry=``."""
    with HANDLES.borrow(path) as f:
        return [("/" + k, _classify_entry(f, "/" + k)) for k in f.keys()]


def _pick_entry(f: h5py.File, path: str, top_level: "list[str]") -> str:
    """Choose which top-level entry to parse when a file has more than one.
    Prefers a recognized entry with the highest numeric suffix (SOLEIL's
    ``..._0001``, ``..._0002``, ... naming), on the assumption that a lower
    number is an earlier, preliminary acquisition (e.g. a navigation image
    taken before the actual scan) -- this is a heuristic, not a guarantee;
    pass ``entry=`` explicitly to load_soleil_nxs() if it picks the wrong
    one for your file. Entries whose *content* doesn't match any known case
    (see :func:`_classify_entry`) are never picked automatically, even if
    their name looks like a match."""
    import re
    candidates = [("/" + k, _classify_entry(f, "/" + k)) for k in top_level]
    recognized = [(g, c) for g, c in candidates if c is not None]
    if not recognized:
        return "/" + top_level[0]  # let the caller raise a clear "unrecognized" error

    if len(recognized) == 1:
        return recognized[0][0]

    def _suffix(name: str) -> int:
        m = re.search(r"(\d+)$", name)
        return int(m.group(1)) if m else -1

    recognized.sort(key=lambda gc: _suffix(gc[0]))
    chosen, _ = recognized[-1]
    warnings.warn(
        f"{path}: multiple usable top-level entries found: {recognized}. "
        f"Using '{chosen}' (highest numeric suffix -- typically the main scan "
        f"rather than a preliminary navigation image, but this is a heuristic). "
        f"Pass entry='{chosen.lstrip('/')}' explicitly to silence this warning, "
        f"or a different entry name from the list above if this guess is wrong "
        f"for your data."
    )
    return chosen


def load_soleil_nxs(path: str, entry: Optional[str] = None,
                    progress=None) -> NxsScan:
    """Load a SOLEIL ANTARES nano-ARPES ``*.nxs`` file. Returns an
    :class:`NxsScan`. Raises for unsupported/unrecognized files rather than
    silently returning garbage.

    ``entry``: which top-level NeXus entry to parse, if the file has more
    than one (see :func:`list_entries`). By default the entry is picked
    automatically among the entries whose *content* is recognized (see
    :func:`_pick_entry`); pass this explicitly to override that guess.
    A photon-energy (PhD) scan is read whole, as a ``kz_map``, when
    ``entry`` is its wildcard name (``"Phd_*"``, as :func:`list_datasets`
    lists it) or when ``entry`` is None and the file holds one; naming one
    of its frames reads that frame alone, as a cut.

    ``progress`` is ``callable(done, total, label)`` or None; only the PhD
    assembly, which reads one frame per photon energy, reports through it.
    """
    # Any of the HDF5 extensions, not just .nxs. The check is here to catch
    # a file of the wrong *type* being pointed at -- a text spectrum, a
    # spreadsheet -- and for that the family is the right granularity. NeXus
    # is an HDF5 layout, this program's own saved format is written with
    # h5py, and a dataset saved as .h5 or handed over as .hdf5 is readable
    # by exactly the same code; refusing it on its name alone meant a file
    # this program itself wrote could not be reopened.
    if not path.lower().endswith((".nxs", ".h5", ".hdf5", ".hdf", ".nx5")):
        raise ValueError(
            f"Not an HDF5/NeXus file (.nxs, .h5, .hdf5): {path}")

    # Opened through the registry, not with a `with`: a spatial scan keeps
    # reading from the file as the user moves around it (see LazyCube), so
    # the handle has to outlive this call, and several entries of the same
    # file must share one handle. Anything that raises, or that read
    # everything it needed, releases it before returning.
    f = HANDLES.acquire(path)
    keep_open = False
    try:
        top_level = list(f.keys())
        phd = phd_entries(f)
        if entry is not None and entry.endswith(PHD_WILDCARD):
            stem = entry.lstrip("/")[:-len(PHD_WILDCARD)]
            members = [name for name in phd if name.startswith(stem)]
            if not members:
                raise KeyError(
                    f"No photon-energy scan frames matching '{entry}' in "
                    f"{path}; available: {top_level}")
        elif entry is None and len(phd) > 1:
            members = phd
        else:
            members = None
        if members is not None:
            scan = _parse_phd(f, members, progress=progress)
            scan.info["_group"] = "/" + _phd_prefix(members) + PHD_WILDCARD
            scan.info["_case"] = 6
            others = [t for t in top_level if t not in members]
            if others:
                scan.info["_other_entries"] = others
            return scan

        if entry is not None:
            g = entry if entry.startswith("/") else "/" + entry
            if g.lstrip("/") not in f:
                raise KeyError(f"Entry '{g}' not found in {path}; available: {top_level}")
        else:
            g = _pick_entry(f, path, top_level)

        case = _classify_entry(f, g)
        if case is None:
            raise KeyError(
                f"Entry '{g}' in {path} doesn't match any known case (its "
                f"content was inspected, not just its name) -- add support "
                f"for it in loader/beamlines/antares.py once you know its structure. "
                f"Run inspect_nxs('{path}') to look at the file. "
                f"All top-level entries in this file: {top_level}"
            )

        if case == 1:
            scan = NxsScan(kind="unsupported", filename_prefix="")
        elif case == 2:
            scan = _parse_case2(f, g, is_zpalign=(g == "/ZPAlign_0001"))
        elif case == 3:
            scan = _parse_case34(f, g, ("data_01", "data_02", "data_03"), ("data_04", "data_05", "data_06"), "data_09")
        elif case == 5:
            scan = _parse_native(f, g)
        elif case == 4:
            scan = _parse_case34(f, g, ("data_04", "data_05", "data_06"), ("data_07", "data_08", "data_09"), "data_11")
        elif case == 6:
            scan = _parse_phd_frame(f, g)
        else:
            raise AssertionError(f"unreachable case {case}")

        # A natively-saved entry carries its own metadata, already read by
        # _parse_native; the beamline readers would find nothing there.
        if scan.kind != "unsupported" and case != 5:
            scan.info.update(_read_common_info(f, g))
            scan.fourd_info.update(_read_fourd_info(f, g))
        scan.info["_group"] = g
        scan.info["_case"] = case
        if len(top_level) > 1:
            scan.info["_other_entries"] = [t for t in top_level if "/" + t != g]

        # Anything still pointing into the file -- a lazy cube, a lazy value
        # array, or an unread preview -- means the handle has to outlive this
        # call. Getting this condition wrong does not fail here; it fails
        # later, at the first slice, with an h5py "identifier is not of
        # specified type", which is why it is one expression rather than
        # being spread across the parsers.
        if (isinstance(scan.value4d, (LazyCube, LazyArray))
                or isinstance(scan.value, (LazyCube, LazyArray))
                or scan.previews):
            scan._h5file = f
            scan._h5path = path
            keep_open = True
        return scan
    finally:
        if not keep_open:
            HANDLES.release(path, f)


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------
def inspect_nxs(path: str, max_depth: int = 6) -> None:
    """Print the HDF5 tree (groups/datasets/shapes) and the detected case,
    for validating the axis-alignment assumptions above against a real
    file. Read-only, side-effect-free besides printing."""
    with HANDLES.borrow(path) as f:
        top_level = list(f.keys())
        print(f"File: {path}")
        print(f"Top-level entries and their detected case (content-based, not name-based):")
        for k in top_level:
            g = "/" + k
            case = _classify_entry(f, g)
            print(f"  {g}: {'UNRECOGNIZED' if case is None else f'case {case}'}")
        print("-" * 70)

        def _walk(name, obj, depth):
            if depth > max_depth:
                return
            indent = "  " * depth
            if isinstance(obj, h5py.Dataset):
                print(f"{indent}{name.split('/')[-1]}  shape={obj.shape} dtype={obj.dtype}")
            else:
                print(f"{indent}{name.split('/')[-1]}/")

        f.visititems(lambda name, obj: _walk(name, obj, name.count("/")))


# --------------------------------------------------------------------------
# The loader
# --------------------------------------------------------------------------
# Imported here, after everything above exists: importing the registry
# installs every loader, and several import names from this module.
from arpes_viewer.loader.registry import Loader, register  # noqa: E402


class SoleilAntaresLoader(Loader):
    name = "SOLEIL ANTARES"
    description = ("Nano-ARPES .nxs files from the ANTARES beamline at "
                   "SOLEIL: spatial scans, deflector maps, single cuts and "
                   "photon-energy (PhD) scans.")
    patterns = ("*.nxs",)
    priority = 10

    def can_open(self, path: str) -> bool:
        """Recognised by *structure*, not by filename.

        ``_classify_entry`` looks at what an entry actually contains -- which
        scan_data datasets exist and what shape the actuators are -- which is
        the same check the reader itself uses, so "can_open said yes" and
        "load worked" cannot disagree.
        """
        try:
            with HANDLES.borrow(path) as f:
                for name in f.keys():
                    try:
                        if _classify_entry(f, "/" + name) is not None:
                            return True
                    except Exception:
                        continue
        except Exception:
            return False
        return False

    def list_entries(self, path: str) -> list:
        return list_datasets(path)

    def load(self, path: str, entry: str = None, progress=None):
        return load_soleil_nxs(path, entry=entry, progress=progress)


register(SoleilAntaresLoader())


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        inspect_nxs(sys.argv[1])
    else:
        print("Usage: python -m arpes_viewer.loader.beamlines.antares <path-to-file.nxs>   # prints file structure")
