"""
agent/workspace.py
==================
The program's data operations without its windows: what the MCP server's
headless tools do.

A :class:`Workspace` holds the datasets an agent has opened or made, by a
short id (``d1``, ``d2``...). Each is a :class:`loader.scan.NxsScan`
with a name -- read by the same loaders as the main window, so a file the
program opens, the agent opens too, and made by the same functions as the
tools (the k conversions of :mod:`tools.momentum`, the Fermi-edge fit of
:mod:`tools.spectra.fermi`). A result can be saved as this program's
``.nxs`` (which the main window opens, and the live viewer can be told to
list) or for Igor Pro.

Axes are named the way a person would: by index (0, 1, 2), by slot
(``x``, ``y``, ``k``, ``z``), by a word of the label (``energy``,
``slit``, ``kx``...). Ranges are ``[lo, hi]`` in the axis's own units.

No Qt here: the server runs without a display.
"""
from __future__ import annotations

import os
import struct
import zlib

import numpy as np

__all__ = ["Workspace", "png_bytes"]

#: The most numbers a curve or a table hands back as text, unless asked.
MAX_POINTS = 400


def png_bytes(rgba) -> bytes:
    """An ``(height, width, 4)`` uint8 array as PNG bytes (no Pillow)."""
    rgba = np.ascontiguousarray(np.asarray(rgba, dtype=np.uint8))
    height, width = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[row].tobytes() for row in range(height))

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def default_kx_points(scanned: int) -> int:
    """The kx grid of a map's k conversion: twice the scanned angles, at
    most 100 points, never fewer than the scan has. One point per scan step
    (61 deflector angles, say) leaves streaks between the scanned cuts."""
    return int(max(scanned, min(2 * scanned, 100)))


class Workspace:
    """The datasets of one agent session, by id."""

    def __init__(self):
        self.datasets = {}           # id -> {"name", "scan", "source"}
        self._count = 0

    # ==================================================================
    # Files and datasets
    # ==================================================================
    @staticmethod
    def loaders() -> list:
        from arpes_viewer.loader import registry
        return [{"name": l.name, "patterns": list(l.patterns),
                 "description": getattr(l, "description", "")}
                for l in registry.loaders()]

    @staticmethod
    def find_files(folder: str, pattern: str = "*", recursive: bool = False,
                   limit: int = 300) -> list:
        """The files under ``folder`` that a loader recognises, with the
        datasets each holds."""
        import glob
        from arpes_viewer.loader import registry

        folder = os.path.normpath(os.path.expanduser(folder))
        if not os.path.isdir(folder):
            raise ValueError(f"no folder {folder}")
        spec = os.path.join(folder, "**", pattern) if recursive \
            else os.path.join(folder, pattern)
        found = []
        for path in sorted(glob.glob(spec, recursive=recursive)):
            if not os.path.isfile(path):
                continue
            loader = registry.detect(path)
            if loader is None:
                continue
            entries = registry.list_entries(path)
            found.append({"path": path, "loader": loader.name,
                          "datasets": [{"entry": e.get("entry"),
                                        "kind": e.get("kind"),
                                        "name": e.get("name") or e.get("title")}
                                       for e in entries[:20]]})
            if len(found) >= limit:
                break
        return found

    def _add(self, scan, name: str, source: str = "") -> str:
        self._count += 1
        ident = f"d{self._count}"
        self.datasets[ident] = {"name": name, "scan": scan, "source": source}
        return ident

    def open(self, path: str, entry: str = None, loader: str = None,
             name: str = None) -> dict:
        from arpes_viewer.loader import registry

        path = os.path.normpath(os.path.expanduser(path))
        options = registry.LoadOptions(loader=loader) if loader else None
        scan = registry.load(path, entry, options)
        base = os.path.splitext(os.path.basename(path.rstrip(os.sep)))[0]
        ident = self._add(scan, name or (f"{base} · {entry}" if entry else base),
                          path)
        return self.describe(ident)

    def get(self, ident: str):
        record = self.datasets.get(str(ident))
        if record is None:
            raise KeyError(f"no dataset {ident!r}; open ones: "
                           f"{', '.join(self.datasets) or 'none'}")
        return record

    def close(self, ident: str) -> str:
        record = self.datasets.pop(str(ident), None)
        if record is None:
            raise KeyError(f"no dataset {ident!r}")
        try:
            record["scan"].close()
        except Exception:                                  # noqa: BLE001
            pass
        return f"closed {ident}"

    def listing(self) -> list:
        return [{"id": i, "name": r["name"], "kind": r["scan"].kind,
                 "shape": list(np.shape(r["scan"].array()))}
                for i, r in self.datasets.items()]

    # -- what a dataset is ---------------------------------------------------
    @staticmethod
    def _slots(scan):
        from arpes_viewer.loader.scan import axis_slots
        return list(axis_slots(scan.kind, "array"))

    def axes(self, ident):
        """``[(slot, label, axis)]`` in the array's order."""
        scan = self.get(ident)["scan"]
        return [(slot, scan.labels.get(slot, slot),
                 np.asarray(getattr(scan, slot), dtype=float))
                for slot in self._slots(scan)]

    def describe(self, ident: str) -> dict:
        record = self.get(ident)
        scan = record["scan"]
        axes = []
        for index, (slot, label, axis) in enumerate(self.axes(ident)):
            step = float(np.median(np.diff(axis))) if axis.size > 1 else 0.0
            axes.append({"index": index, "slot": slot, "label": label,
                         "min": float(np.nanmin(axis)), "max": float(np.nanmax(axis)),
                         "points": int(axis.size), "step": step})
        info = scan.info or {}
        keys = ("photon_energy", "hv", "temperature", "pass_energy",
                "polarization", "polarisation", "fitEF.ef_subtracted",
                "loader.name", "axis0.role")
        highlights = {}
        for key, value in info.items():
            tail = str(key).lower()
            if any(k in tail for k in keys) and len(highlights) < 25:
                highlights[key] = _short(value)
        return {"id": str(ident), "name": record["name"], "kind": scan.kind,
                "source": record["source"], "axes": axes,
                "metadata_highlights": highlights,
                "metadata_fields": len(info)}

    def metadata(self, ident: str, contains: str = "", limit: int = 200) -> dict:
        info = self.get(ident)["scan"].info or {}
        words = str(contains).lower().split()
        out = {}
        for key, value in info.items():
            text = f"{key} {value}".lower()
            if all(w in text for w in words):
                out[str(key)] = _short(value)
            if len(out) >= int(limit):
                break
        return out

    # ==================================================================
    # Reading values
    # ==================================================================
    def axis_index(self, ident, spec) -> int:
        """An axis by index, slot, or a word of its label."""
        axes = self.axes(ident)
        if isinstance(spec, (int, np.integer)) or (isinstance(spec, str) and spec.isdigit()):
            index = int(spec)
            if not 0 <= index < len(axes):
                raise ValueError(f"axis {index} out of range (0-{len(axes) - 1})")
            return index
        word = str(spec).strip().lower()
        for index, (slot, _l, _a) in enumerate(axes):
            if word == slot:
                return index
        if word in ("e", "energy", "ek", "ekin", "binding"):
            from arpes_viewer.loader.scan import energy_slot
            scan = self.get(ident)["scan"]
            slot = energy_slot(scan.kind)
            for index, (s, _l, _a) in enumerate(axes):
                if s == slot:
                    return index
        for index, (_s, label, _a) in enumerate(axes):
            if word in str(label).lower():
                return index
        raise ValueError(f"no axis {spec!r}; axes are "
                         + ", ".join(f"{i}: {s} = {l}" for i, (s, l, _a) in enumerate(axes)))

    def _window(self, ident, keep, ranges):
        """The array cut to ``ranges`` and averaged over every axis not in
        ``keep``: ``(values, [kept axes])``."""
        axes = self.axes(ident)
        scan = self.get(ident)["scan"]
        ranges = {self.axis_index(ident, k): v for k, v in (ranges or {}).items()}
        index = []
        for i, (_s, _l, axis) in enumerate(axes):
            span = ranges.get(i)
            if span is None:
                index.append(slice(None))
                continue
            if np.isscalar(span):
                nearest = int(np.argmin(np.abs(axis - float(span))))
                index.append(slice(nearest, nearest + 1))
                continue
            lo, hi = float(min(span)), float(max(span))
            inside = np.flatnonzero((axis >= lo) & (axis <= hi))
            if inside.size == 0:
                nearest = int(np.argmin(np.abs(axis - 0.5 * (lo + hi))))
                inside = np.array([nearest])
            index.append(slice(int(inside[0]), int(inside[-1]) + 1))
        values = np.asarray(scan.array()[tuple(index)], dtype=float)
        drop = tuple(i for i in range(len(axes)) if i not in keep)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            if drop:
                values = np.nanmean(values, axis=drop)
        kept = [axes[i][2][index[i]] for i in sorted(keep)]
        if list(keep) != sorted(keep):                    # (y, x) asked for
            values = values.T
            kept = kept[::-1]
        return values, kept

    def profile(self, ident, along, ranges=None, max_points: int = MAX_POINTS,
                path: str = None) -> dict:
        """A curve: the values along one axis, averaged over ``ranges`` of
        the others (all of each axis not given)."""
        i = self.axis_index(ident, along)
        values, (axis,) = self._window(ident, (i,), ranges)
        label = self.axes(ident)[i][1]
        if path:
            path = os.path.normpath(os.path.expanduser(path))
            np.savetxt(path, np.column_stack([axis, values]), delimiter=",",
                       header=f"{label},intensity", comments="")
        step = max(1, int(np.ceil(axis.size / max(int(max_points), 2))))
        return {"axis": label, "points": int(axis.size),
                "every": step, "x": axis[::step].round(6).tolist(),
                "y": np.round(values[::step], 6).tolist(),
                "saved": path or ""}

    def image(self, ident, x, y, ranges=None, colormap: str = "gray",
              flip: bool = False, width: int = 700, height: int = 520,
              levels=None, gamma: float = 1.0, path: str = None,
              csv_path: str = None):
        """A 2-D picture: axis ``x`` across, ``y`` up, the other axes
        averaged over ``ranges``. Returns ``(png bytes, summary)``."""
        from arpes_viewer.tools.output import colormaps
        from arpes_viewer.tools.output.export import render_rgba

        ix, iy = self.axis_index(ident, x), self.axis_index(ident, y)
        if ix == iy:
            raise ValueError("x and y must be two different axes")
        values, (ax, ay) = self._window(ident, (ix, iy), ranges)
        if ix > iy:
            pass                      # _window put them in (x, y) already
        finite = values[np.isfinite(values)]
        if levels is None and finite.size:
            levels = (float(np.percentile(finite, 1)),
                      float(np.percentile(finite, 99.5)))
        rgba = render_rgba(values, ax, ay,
                           x_range=(float(ax.min()), float(ax.max())),
                           y_range=(float(ay.min()), float(ay.max())),
                           lut=colormaps.get_lut(colormap, flip=bool(flip)),
                           levels=levels, gamma=float(gamma),
                           width=int(width), height=int(height))
        png = png_bytes(rgba)
        if path:
            path = os.path.normpath(os.path.expanduser(path))
            with open(path, "wb") as handle:
                handle.write(png)
        if csv_path:
            csv_path = os.path.normpath(os.path.expanduser(csv_path))
            table = np.vstack([np.concatenate([[np.nan], ay]),
                               np.column_stack([ax, values])])
            np.savetxt(csv_path, table, delimiter=",")
        labels = self.axes(ident)
        summary = {"x": labels[ix][1], "y": labels[iy][1],
                   "x_range": [float(ax.min()), float(ax.max())],
                   "y_range": [float(ay.min()), float(ay.max())],
                   "levels": list(levels) if levels is not None else None,
                   "shape": list(values.shape), "saved_png": path or "",
                   "saved_csv": csv_path or ""}
        return png, summary

    # ==================================================================
    # Operations that make a new dataset
    # ==================================================================
    def _derived(self, kind, axes_by_slot, value, labels, info, name, source_id):
        from arpes_viewer.loader.scan import NxsScan
        scan = NxsScan(kind=kind, info=dict(info or {}), labels=dict(labels),
                       value=np.asarray(value))
        for slot, axis in axes_by_slot.items():
            setattr(scan, slot, np.asarray(axis, dtype=float))
        return self._add(scan, name, f"from {source_id}")

    def fermi_edge(self, ident, energy_window=None, temperature: float = 30.0,
                   ranges=None, fit_temperature: bool = False) -> dict:
        """Fit the Fermi edge of the EDC averaged over ``ranges`` of the
        other axes."""
        from arpes_viewer.tools.spectra.fermi import fit_fermi_edge

        e = self.axis_index(ident, "energy")
        values, (energy,) = self._window(ident, (e,), ranges)
        window = tuple(energy_window) if energy_window else (None, None)
        fit = fit_fermi_edge(energy, values, temperature=float(temperature),
                             fixed=() if fit_temperature else ("temperature",),
                             window=window)
        problems = fit.problems()
        if problems:
            raise ValueError("no Fermi edge found: " + "; ".join(problems))
        return {"success": bool(fit.success), "message": fit.message,
                "values": {k: float(v) for k, v in fit.values.items()},
                "errors": {k: float(v) for k, v in fit.errors.items()},
                "reduced_chi2": float(fit.reduced_chi2),
                "points": int(fit.n_points),
                "combined_width_eV": float(fit.combined_width)}

    def shift_energy(self, ident, ef: float, name: str = None) -> dict:
        """A copy on E - E_F, ``ef`` on the dataset's own energy axis."""
        record = self.get(ident)
        scan = record["scan"]
        e = self.axis_index(ident, "energy")
        slots = self._slots(scan)
        axes = {s: np.asarray(getattr(scan, s), dtype=float) for s in slots}
        axes[slots[e]] = axes[slots[e]] - float(ef)
        labels = dict(scan.labels)
        labels[slots[e]] = "E - E_F (eV)"
        info = dict(scan.info or {})
        info["fitEF.ef_subtracted"] = float(ef)
        new = self._derived(scan.kind, axes, np.asarray(scan.array()), labels,
                            info, name or f"{record['name']} [E-Ef]", ident)
        return self.describe(new)

    def crop(self, ident, ranges, name: str = None) -> dict:
        record = self.get(ident)
        scan = record["scan"]
        axes = self.axes(ident)
        values, kept = self._window(ident, tuple(range(len(axes))), ranges)
        slots = self._slots(scan)
        new = self._derived(scan.kind, dict(zip(slots, kept)), values,
                            dict(scan.labels), dict(scan.info or {}),
                            name or f"{record['name']} [crop]", ident)
        return self.describe(new)

    def convert_cut(self, ident, gamma_slit_deg: float = 0.0,
                    deflector_deg: float = 0.0, gamma_deflector_deg: float = None,
                    azimuth_deg: float = 0.0, energy_offset_eV: float = 0.0,
                    output_fermi_level_eV: float = None, n_k: int = None,
                    name: str = None) -> dict:
        """A cut in momentum, as the *k conversion (cut)* tool does it."""
        from arpes_viewer.tools.momentum.cutk import K_LABEL, convert_cut

        record = self.get(ident)
        scan = record["scan"]
        if scan.kind != "cut":
            raise ValueError(f"{ident} is a {scan.kind}, not a cut")
        shifted = float((scan.info or {}).get("fitEF.ef_subtracted", 0.0) or 0.0)
        offset = float(energy_offset_eV) + shifted
        k_axis, energy, values, report = convert_cut(
            scan.x, scan.y, np.asarray(scan.value),
            deflector_deg=float(deflector_deg),
            gamma_deflector_deg=float(deflector_deg if gamma_deflector_deg is None
                                      else gamma_deflector_deg),
            gamma_slit_deg=float(gamma_slit_deg), azimuth_deg=float(azimuth_deg),
            energy_offset_eV=offset, n_k=int(n_k or len(scan.x)))
        energy = np.asarray(energy, dtype=float) - offset if shifted else np.asarray(energy)
        labels = {"x": K_LABEL, "y": scan.labels.get("y", "Energy (eV)")}
        info = dict(scan.info or {})
        if output_fermi_level_eV is not None and not shifted:
            energy = energy - offset - float(output_fermi_level_eV)
            info["fitEF.ef_subtracted"] = float(output_fermi_level_eV) + offset
            labels["y"] = "E - E_F (eV)"
        new = self._derived("cut", {"x": k_axis, "y": energy}, values, labels,
                            info, name or f"{record['name']} [k]", ident)
        out = self.describe(new)
        out["k_perp"] = float(report.get("k_perp", 0.0))
        out["measured_fraction"] = float(report.get("measured_fraction", 0.0))
        return out

    def convert_map(self, ident, gamma_deflector_deg: float = 0.0,
                    gamma_slit_deg: float = 0.0, azimuth_deg: float = 0.0,
                    energy_offset_eV: float = 0.0,
                    output_fermi_level_eV: float = None, n_kx: int = None,
                    n_ky: int = None, name: str = None) -> dict:
        """A map in momentum, as the *k conversion (map)* tool does it."""
        from arpes_viewer.tools.momentum.kspace import convert_map

        record = self.get(ident)
        scan = record["scan"]
        if scan.kind != "map":
            raise ValueError(f"{ident} is a {scan.kind}, not an angle map")
        shifted = float((scan.info or {}).get("fitEF.ef_subtracted", 0.0) or 0.0)
        offset = float(energy_offset_eV) + shifted
        kx, ky, energy, cube = convert_map(
            scan.x, scan.k, scan.z, np.asarray(scan.value),
            theta_offset_deg=float(gamma_deflector_deg),
            phi_offset_deg=float(gamma_slit_deg), azimuth_deg=float(azimuth_deg),
            energy_offset_eV=offset, n_kx=int(n_kx or default_kx_points(len(scan.x))),
            n_ky=int(n_ky or len(scan.k)), precision="float32")
        energy = np.asarray(energy, dtype=float)
        labels = {"x": "kx (Å⁻¹)", "k": "ky (Å⁻¹)",
                  "z": scan.labels.get("z", "Energy (eV)")}
        info = dict(scan.info or {})
        if shifted:
            energy = energy - offset
        elif output_fermi_level_eV is not None:
            energy = energy - offset - float(output_fermi_level_eV)
            info["fitEF.ef_subtracted"] = float(output_fermi_level_eV) + offset
            labels["z"] = "E - E_F (eV)"
        new = self._derived("k_map", {"x": kx, "k": ky, "z": energy}, cube,
                            labels, info, name or f"{record['name']} [k]", ident)
        return self.describe(new)

    # ==================================================================
    # Saving
    # ==================================================================
    def as_dict(self, ident) -> dict:
        from arpes_viewer.loader.session import scan_to_dict
        record = self.get(ident)
        return scan_to_dict(record["scan"].kind, record["scan"], record["name"])

    def save(self, ids, path: str, fmt: str = None) -> dict:
        """Save to ``.nxs`` (this program's own, several datasets per file),
        ``.itx`` (Igor text, several waves) or ``.ibw`` (one wave)."""
        from arpes_viewer.loader.native import save_dataset
        from arpes_viewer.tools.output import igor

        ids = [ids] if isinstance(ids, str) else list(ids)
        path = os.path.normpath(os.path.expanduser(path))
        fmt = (fmt or os.path.splitext(path)[1].lstrip(".") or "nxs").lower()
        items = [self.as_dict(i) for i in ids]
        for item in items:
            item["value"] = np.asarray(item["value"])
        if fmt == "nxs":
            written = save_dataset(path, items)
        elif fmt == "itx":
            taken = []
            specs = []
            for item in items:
                spec = igor.wave_from_dataset(item, taken)
                taken.append(spec.name)
                specs.append(spec)
            igor.write_itx(path, specs)
            written = [s.name for s in specs]
        elif fmt == "ibw":
            if len(items) != 1:
                raise ValueError("an .ibw holds one wave: save one dataset")
            spec = igor.wave_from_dataset(items[0])
            igor.write_ibw(path, spec)
            written = [spec.name]
        else:
            raise ValueError(f"unknown format {fmt!r}: nxs, itx or ibw")
        return {"path": path, "format": fmt, "entries": list(written)}

    # ==================================================================
    # The crystal
    # ==================================================================
    @staticmethod
    def brillouin_zone(space_group: int, a: float, b: float = None,
                       c: float = None, alpha: float = 90.0, beta: float = 90.0,
                       gamma: float = None) -> dict:
        """The zone's named points (Cartesian, Å⁻¹) and the reciprocal
        vectors, with the cell constrained by the space group."""
        from arpes_viewer.tools.crystal.highsym import high_symmetry_points
        from arpes_viewer.tools.crystal.lattice import (LatticeParams, free_parameters,
                                                        primitive_vectors,
                                                        reciprocal_vectors)
        from arpes_viewer.tools.crystal.spacegroups import spacegroup_info

        number = int(space_group)
        constraints = free_parameters(number)
        given = {"a": float(a), "b": None if b is None else float(b),
                 "c": None if c is None else float(c), "alpha": float(alpha),
                 "beta": float(beta), "gamma": None if gamma is None else float(gamma)}
        for target, source in constraints.mirrors.items():
            given[target] = given[source]
        for name, value in constraints.fixed_angles.items():
            given[name] = value
        given = {k: (given["a"] if v is None and k in "bc" else v)
                 for k, v in given.items()}
        if given["gamma"] is None:
            given["gamma"] = 90.0
        params = LatticeParams(given["a"], given["b"], given["c"], given["alpha"],
                               given["beta"], given["gamma"], space_group=number)
        info = spacegroup_info(number)
        b_vectors = reciprocal_vectors(primitive_vectors(params))
        return {"space_group": number, "symbol": info.symbol,
                "crystal_system": info.crystal_system,
                "cell": given, "constraints": constraints.note,
                "reciprocal_vectors": np.round(b_vectors, 6).tolist(),
                "points": {p.label: np.round(p.k, 6).tolist()
                           for p in high_symmetry_points(params)}}

    @staticmethod
    def read_cif(path: str) -> dict:
        from arpes_viewer.tools.crystal.structure import read_cif
        structure = read_cif(os.path.normpath(os.path.expanduser(path)))
        return {"name": structure.name, "formula": structure.formula(),
                "space_group": structure.space_group,
                "space_group_number": structure.space_group_number,
                "cell": {"a": structure.a, "b": structure.b, "c": structure.c,
                         "alpha": structure.alpha, "beta": structure.beta,
                         "gamma": structure.gamma},
                "sites": [{"label": s.label, "element": s.element,
                           "frac": list(s.frac), "occupancy": s.occupancy}
                          for s in structure.sites],
                "atoms_in_cell": len(structure.atoms)}


def _short(value):
    """A metadata value small enough to show: arrays summarised."""
    if isinstance(value, np.ndarray):
        if value.size == 1:
            return value.reshape(-1)[0].item()
        flat = value.reshape(-1)
        return f"array{list(value.shape)} {flat[:5].tolist()}{' ...' if flat.size > 5 else ''}"
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    text = value if isinstance(value, (int, float, bool)) else str(value)
    return text[:300] if isinstance(text, str) else text
