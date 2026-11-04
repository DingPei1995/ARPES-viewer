"""
ui/common/live.py
==================
The running program as one object with documented operations: ``L``.

An agent working with the program on screen (route 3: command files dropped
into a folder; route 1 with ``--agent-bridge``: ``viewer_api``) used to find
its way by reading the source and pressing dialogs' buttons by their text.
That is slow, costs tokens, and breaks when a dialog changes. This module is
the stable layer instead: every operation the program offers, by name, with
its parameters and what it returns, acting on the rows of the main list by
their names -- the same rows the person at the screen sees.

    L.help()                     # every operation, grouped
    L.help("kz_to_k")            # one operation in full
    L.rows()                     # what is in the list
    L.fermi_edge("cut1", energy_window=(-0.15, 0.1), temperature=30)
    L.shift_energy("cut1", ef=-0.012)          # -> "cut1 [E-Ef]"
    L.slice_series("map1 [k]", values=[0, -0.1, -0.2], half_width=0.02)

Rules every operation keeps:

* **Rows are named, never guessed.** A name is matched exactly, else as the
  one row whose name contains it; two candidates raise an error listing
  them.
* **Nothing is overwritten.** An operation that makes data adds a new row
  (its name returned) and records how it was made in the row's history.
* **No modal dialog.** Everything runs without waiting for a click; a
  question the program would ask raises an error naming it instead.
* **Plain results.** Dicts, lists, strings and numbers (JSON as they
  stand), so the same operations serve the bridge and MCP.

The list of operations, with their full descriptions, is generated into
``agentic/API.md`` by :mod:`agent.catalog`; a test fails when the two
drift apart, so the reference an agent reads is always the program's own.
"""
from __future__ import annotations

import inspect
import os

import numpy as np

__all__ = ["Live", "operation", "GROUPS"]

#: the groups the operations are listed under, in order
GROUPS = ("Start here", "The list", "Looking at data", "Energy",
          "Processing", "Momentum", "Crystal and Brillouin zone", "Figures",
          "Tool windows", "Your own computation")


def operation(group: str):
    """Mark a method of :class:`Live` as an operation of ``group``."""
    if group not in GROUPS:
        raise ValueError(f"unknown group {group!r}")

    def mark(function):
        function._operation = group
        return function
    return mark


def _keeps_selection(method):
    """Run an operation and put the main list's selection back as it was.

    Several operations select rows to reach a tool (the kz conversion, the
    BZ overlay, a slice series ...), and listing a result selects the new
    row. While the agent works, the person may be looking at data in the
    same list; their selection is theirs, so it is restored after each such
    operation. (``L.select`` is the one operation that changes it, when the
    agent is asked to.)"""
    import functools

    @functools.wraps(method)
    def kept(self, *args, **kwargs):
        widget = self.A.ui.FilePathListWidget
        chosen = [widget.item(i).data(0x0100) for i in range(widget.count())
                  if widget.item(i).isSelected()]
        current = widget.currentItem()
        current = current.data(0x0100) if current is not None else None
        try:
            return method(self, *args, **kwargs)
        finally:
            widget.blockSignals(True)
            try:
                widget.clearSelection()
                for i in range(widget.count()):
                    item = widget.item(i)
                    key = item.data(0x0100)
                    if key == current:
                        widget.setCurrentItem(item)
                    item.setSelected(key in chosen)
            finally:
                widget.blockSignals(False)
            update = getattr(self.A, "update_tool_buttons", None)
            if callable(update):
                update()
    return kept


def _plain(value):
    """``value`` with numpy scalars and arrays turned into JSON types."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist() if value.size <= 64 else (
            f"array{list(value.shape)}")
    if isinstance(value, np.generic):
        return value.item()
    return value


class Dataset:
    """A row's data as plain arrays, for a computation of your own:
    ``kind``, ``axes`` (one array per dimension, in the array's order),
    ``labels`` (one per axis), ``values`` and ``info`` (metadata)."""

    def __init__(self, name, kind, axes, labels, values, info):
        self.name, self.kind = name, kind
        self.axes, self.labels = axes, labels
        self.values, self.info = values, info

    def __repr__(self):
        shape = "x".join(str(n) for n in np.shape(self.values))
        return f"<Dataset {self.name!r}: {self.kind} {shape}, axes {self.labels}>"


class Live:
    """The program's operations, on the rows of its main list.

    ``app`` is :mod:`arpes_viewer.app`, running (the live viewer or the
    program started with the agent bridge).
    """

    def __init__(self, app):
        self.A = app
        self._figures = {}

    # ==================================================================
    # Start here
    # ==================================================================
    @operation("Start here")
    def help(self, topic: str = "") -> str:
        """Every operation, grouped, one line each; ``help("name")`` gives
        one operation in full, ``help("group")`` one group. Read this (or
        ``agentic/API.md``) before anything else: it is the program's own
        list of what it can do, so nothing has to be found in the source."""
        from arpes_viewer.agent.catalog import live_reference
        text = live_reference(topic)
        print(text)
        return text

    @operation("Start here")
    def status(self) -> dict:
        """The program's version, how many rows the list has, which windows
        are open, and where the agent's folders are."""
        from arpes_viewer.version import VERSION
        return {"version": VERSION, "rows": len(self.A.loaded_items),
                "windows": self.windows(),
                "command_folder": getattr(self.A, "_agent_folder", "") or ""}

    # ==================================================================
    # The list
    # ==================================================================
    def _key(self, name: str):
        """The list key of the row called ``name`` (exact, else the one row
        whose name contains it)."""
        items = self.A.loaded_items
        name = str(name)
        exact = [k for k, r in items.items() if r.get("name") == name]
        if len(exact) == 1:
            return exact[0]
        found = [k for k, r in items.items()
                 if name.lower() in str(r.get("name", "")).lower()]
        if len(found) == 1:
            return found[0]
        names = [str(items[k].get("name")) for k in (exact or found)]
        if not names:
            raise KeyError(f"no row called {name!r}; rows: "
                           f"{[r.get('name') for r in items.values()]}")
        raise KeyError(f"{name!r} matches several rows: {names}; give the "
                       f"whole name")

    def _name(self, key) -> str:
        return str(self.A.loaded_items[key].get("name"))

    @operation("The list")
    def rows(self) -> list:
        """The rows of the main list: ``name``, ``kind`` (Cut, Map, kz map,
        k-map ...), ``path`` of the file behind it, and whether it is
        selected."""
        A = self.A
        widget = A.ui.FilePathListWidget
        out = []
        for i in range(widget.count()):
            item = widget.item(i)
            key = item.data(0x0100)
            record = A.loaded_items.get(key, {})
            out.append({"row": i, "name": record.get("name", item.text()),
                        "kind": record.get("kind", ""),
                        "path": record.get("path", ""),
                        "selected": item.isSelected()})
        return out

    @operation("The list")
    @_keeps_selection
    def add_files(self, paths) -> dict:
        """Add files to the list, the reader detected as by Quick add.
        ``paths`` is one path or a list; a folder adds every file in it a
        reader recognises, and the scans in its sub-folders (a CASSIOPEE
        map folder is one row). Returns the rows added."""
        if isinstance(paths, str):
            paths = [paths]
        files = []
        for path in paths:
            files += self._expand(os.path.expanduser(path))
        before = set(self.A.loaded_items)
        self.A.add_files(files, background=False)
        added = [self._name(k) for k in self.A.loaded_items if k not in before]
        return {"added": added, "rows": len(self.A.loaded_items)}

    @staticmethod
    def _expand(path: str) -> list:
        """A file as itself; a folder as the recognised files in it and in
        its sub-folders one level down (the loaders list a numbered series
        once, whichever of its files is given)."""
        if not os.path.isdir(path):
            return [path]
        from arpes_viewer.loader import registry
        found = []
        for folder in [path] + sorted(
                os.path.join(path, d) for d in os.listdir(path)
                if os.path.isdir(os.path.join(path, d))):
            for name in sorted(os.listdir(folder)):
                candidate = os.path.join(folder, name)
                if os.path.isfile(candidate) and registry.detect(candidate):
                    found.append(candidate)
        return found

    @operation("The list")
    def select(self, *names) -> list:
        """Select these rows (and only these), as a click would; what the
        tool windows act on. Returns the names selected."""
        widget = self.A.ui.FilePathListWidget
        keys = [self._key(n) for n in names]
        widget.clearSelection()
        chosen = []
        for i in range(widget.count()):
            item = widget.item(i)
            if item.data(0x0100) in keys:
                item.setSelected(True)
                widget.setCurrentItem(item)
                chosen.append(self._name(item.data(0x0100)))
        return chosen

    @operation("The list")
    def rename(self, name: str, new_name: str) -> str:
        """Give a row a new name (made unique if taken). Returns it."""
        A = self.A
        key = self._key(name)
        new_name = A.unique_name(str(new_name))
        A.loaded_items[key]["name"] = new_name
        item = A._row_for_key(key)
        if item is not None:
            item.setText(A._row_label(key))
        return new_name

    @operation("The list")
    def remove(self, *names) -> list:
        """Take rows off the list (and drop their auto-saved copies). The
        files they were read from are not touched. Only when the person has
        asked for it."""
        keys = [self._key(n) for n in names]
        removed = [self._name(k) for k in keys]
        self.A._remove_keys(keys)
        return removed

    @operation("The list")
    def save(self, names, path: str, fmt: str = "") -> dict:
        """Write rows to one file: ``.nxs`` (the program's own format, which
        it opens again) or ``.itx`` for Igor Pro; ``fmt`` "nxs"/"igor" if
        the extension does not say. Never overwrites: an existing file is
        refused."""
        if isinstance(names, str):
            names = [names]
        path = os.path.expanduser(path)
        if os.path.exists(path):
            raise FileExistsError(f"{path} exists; give a new name")
        from arpes_viewer.agent.workspace import Workspace
        workspace = Workspace()
        ids = [workspace._add(self._scan(n), self._name(self._key(n)))
               for n in names]
        return _plain(workspace.save(ids, path, fmt or None))

    # -- moving data between the list and plain arrays -------------------
    def _scan(self, name):
        """A plain copy of the row's scan (an :class:`NxsScan` in memory),
        for the headless computations."""
        from arpes_viewer.loader.scan import NxsScan, axis_slots
        key = self._key(name)
        data = self.A.load_dataset(key)
        scan = data.scan
        kind = scan.kind
        value = scan.value4d if kind == "spem_4d" else scan.value
        copy = NxsScan(kind=kind, info=dict(scan.info or {}),
                       labels=dict(scan.labels or {}),
                       value=np.asarray(value))
        for slot in set(axis_slots(kind, "array")) | set(axis_slots(kind, "constructor")):
            axis = getattr(scan, slot, None)
            if axis is not None:
                setattr(copy, slot, np.asarray(axis, dtype=float))
        if kind == "spem_4d":
            copy.value4d = copy.value
        return copy

    def _list_scan(self, scan, name: str, source: str = "") -> str:
        """Put a computed scan on the list; returns the row's name."""
        from arpes_viewer.loader.scan import axis_slots
        from arpes_viewer.ui.viewers.widgets import MemoryData
        slots = axis_slots(scan.kind, "constructor")
        data = MemoryData(scan.kind, tuple(getattr(scan, s) for s in slots),
                          np.asarray(scan.array()), dict(scan.labels),
                          source_label=name, source_info=dict(scan.info or {}),
                          source_path=source)
        item = self.A.add_memory_dataset(data, name)
        return self._name(item.data(0x0100))

    # ==================================================================
    # Looking at data
    # ==================================================================
    def _workspace(self, *names):
        from arpes_viewer.agent.workspace import Workspace
        workspace = Workspace()
        ids = [workspace._add(self._scan(n), self._name(self._key(n)))
               for n in names]
        return workspace, ids

    @operation("Looking at data")
    def describe(self, name: str) -> dict:
        """A row's kind, shape and axes (label, range, step, points)."""
        workspace, (ident,) = self._workspace(name)
        return _plain(workspace.describe(ident))

    @operation("Looking at data")
    def metadata(self, name: str, contains: str = "", limit: int = 200) -> dict:
        """A row's metadata (photon energy, temperature, polarisation,
        manipulator, the history of how it was made ...), the keys
        containing ``contains`` if given."""
        workspace, (ident,) = self._workspace(name)
        return _plain(workspace.metadata(ident, contains, limit))

    @operation("Looking at data")
    def picture(self, name: str, x, y, path: str, ranges=None,
                colormap: str = "gray", flip: bool = False, levels=None,
                gamma: float = 1.0, width: int = 700, height: int = 520) -> dict:
        """Write a picture of ``y`` against ``x`` (axis labels, indices, or
        "energy") to the PNG ``path``, integrating the other axes over
        ``ranges`` ({axis: (lo, hi)}); for looking at data without reading
        the screen. Returns what was drawn."""
        path = os.path.expanduser(path)
        workspace, (ident,) = self._workspace(name)
        _png, summary = workspace.image(ident, x, y, ranges, colormap, flip,
                                        width, height, levels, gamma, path, None)
        return _plain(summary)

    @operation("Looking at data")
    def profile(self, name: str, along, ranges=None) -> dict:
        """An EDC or MDC as numbers: the values along one axis, the others
        integrated over ``ranges`` ({axis: (lo, hi)})."""
        workspace, (ident,) = self._workspace(name)
        return _plain(workspace.profile(ident, along, ranges))

    @operation("Looking at data")
    @_keeps_selection
    def open(self, name: str) -> str:
        """Open the row's viewer window on screen (as a double-click does).
        Returns the window's title."""
        self.select(name)
        self.A.open_selected()
        windows = self.A.viewer_windows
        return windows[-1].windowTitle() if windows else ""

    # ==================================================================
    # Energy
    # ==================================================================
    @operation("Energy")
    def fermi_edge(self, name: str, energy_window=None,
                   temperature: float = 30.0, ranges=None,
                   fit_temperature: bool = False) -> dict:
        """Fit the Fermi edge of the EDC summed over ``ranges`` of the other
        axes, within ``energy_window`` (lo, hi) on the row's own energy axis.
        The temperature is held unless ``fit_temperature``. Returns E_F,
        the resolution, their errors and the reduced chi2; a fit that finds
        no edge (normalised data, a window without the edge) is refused
        with the reason."""
        workspace, (ident,) = self._workspace(name)
        return _plain(workspace.fermi_edge(ident, energy_window, temperature,
                                           ranges, fit_temperature))

    @operation("Energy")
    @_keeps_selection
    def shift_energy(self, name: str, ef: float, new_name: str = "") -> str:
        """A copy on E - E_F: ``ef`` (on the row's own energy axis) is
        subtracted. Returns the new row's name."""
        workspace, (ident,) = self._workspace(name)
        result = workspace.shift_energy(ident, float(ef), new_name or None)
        record = workspace.get(result["id"])
        return self._list_scan(record["scan"], record["name"])

    @operation("Energy")
    @_keeps_selection
    def kz_align_fermi(self, name: str, angle_range, energy_range,
                       temperature: float = 30.0, hold_temperature: bool = True,
                       normalise: bool = True) -> dict:
        """Align a photon-energy scan (kz map) on its Fermi level: one
        Fermi-edge fit per photon energy, over the analyser channels
        ``angle_range`` (lo, hi, inclusive indices) and the energy channels
        ``energy_range`` (indices), each spectrum shifted to put its own
        edge at zero, optionally normalised by its total. Adds the aligned
        row (its per-hv E_F kept in ``kz.fermi_level_eV``, which the kz
        conversion's hv calibration uses). Returns the new row and the
        Fermi levels."""
        from arpes_viewer.tools.momentum import kzmap
        key = self._key(name)
        self.select(self._name(key))
        contour = self.A.map_contour(key)
        if contour is None or contour.data.kind != "kz_map":
            raise ValueError(f"{name!r} is not a photon-energy scan (kz map)")
        dialog = contour.open_kz_processing()
        region = ((int(angle_range[0]), int(angle_range[1])),
                  (int(energy_range[0]), int(energy_range[1])))
        dialog.index_region = lambda: region
        dialog.temperature.setValue(float(temperature))
        dialog.hold_temperature.setChecked(bool(hold_temperature))
        dialog.normalise.setChecked(bool(normalise))
        cube = np.asarray(contour.full_cube(), dtype=float)
        result = kzmap.process_kz_map(
            cube, dialog.energy, region, temperature=float(temperature),
            fixed=("temperature",) if hold_temperature else (),
            normalise=bool(normalise))
        before = set(self.A.loaded_items)
        dialog._finish(result)
        added = [self._name(k) for k in self.A.loaded_items if k not in before]
        cut = getattr(dialog, "cut_window", None)
        dialog.close()
        if cut is not None:
            cut.close()
        return _plain({"row": added[-1] if added else "",
                       "fermi_levels_eV": np.asarray(result.ef).tolist(),
                       "fitted": np.asarray(result.ok).tolist(),
                       "spread_eV": float(result.spread)})

    # ==================================================================
    # Processing
    # ==================================================================
    def _derive(self, name, values, axes, step: str, parameters: dict,
                new_name: str = "", labels=None, kind=None) -> str:
        """A new row from ``values`` on ``axes`` made from row ``name``."""
        from arpes_viewer.loader.scan import NxsScan
        from arpes_viewer.tools.processing.process import Step, record_step
        source = self._scan(name)
        kind = kind or source.kind
        slots = source.axis_slots("array")
        scan = NxsScan(kind=kind, labels=dict(labels or source.labels),
                       info=record_step(dict(source.info or {}),
                                        Step(step, _plain(parameters),
                                             source=self._name(self._key(name)))),
                       value=np.asarray(values))
        for slot, axis in zip(slots, axes):
            setattr(scan, slot, np.asarray(axis, dtype=float))
        return self._list_scan(scan, new_name or
                               f"{self._name(self._key(name))} [{step}]")

    @operation("Processing")
    @_keeps_selection
    def crop(self, name: str, bounds, new_name: str = "") -> str:
        """Cut out a box: ``bounds`` is one (lo, hi) per axis in the axes'
        own units, None for "to the end". Returns the new row."""
        from arpes_viewer.tools.processing.dataops import truncate
        data = self.data(name)
        values, axes = truncate(data.values, data.axes, bounds)
        return self._derive(name, values, axes, "truncate",
                            {"bounds": bounds}, new_name)

    @operation("Processing")
    @_keeps_selection
    def bin(self, name: str, factors, new_name: str = "") -> str:
        """Sum blocks of neighbouring points: one factor per axis (1 keeps
        it). Counts are preserved. Returns the new row."""
        from arpes_viewer.tools.processing.dataops import compress
        data = self.data(name)
        values, axes = compress(data.values, data.axes, factors)
        return self._derive(name, values, axes, "compress",
                            {"factors": factors}, new_name)

    @operation("Processing")
    @_keeps_selection
    def normalise(self, name: str, axes=1, window=None,
                  to_peak: bool = False, new_name: str = "") -> str:
        """Divide the data by its own intensity: every line along axis
        ``axes`` (an index; 1 = energy for a cut) by that line's total, or
        every plane spanned by two axes (``axes=(0, 1)``) by its total; the
        sums taken inside ``window`` (lo, hi, on the first of them) if given;
        ``to_peak`` divides by the maximum. Never before a Fermi fit: fit the
        raw data first."""
        from arpes_viewer.tools.processing.dataops import self_normalize
        data = self.data(name)
        dims = (axes,) if np.ndim(axes) == 0 else tuple(axes)
        values = self_normalize(data.values, data.axes, dims, window=window,
                                to_peak=to_peak)
        return self._derive(name, values, data.axes, "normalise",
                            {"dims": list(dims), "window": window,
                             "to_peak": to_peak}, new_name)

    @operation("Processing")
    @_keeps_selection
    def smooth(self, name: str, widths, new_name: str = "") -> str:
        """Gaussian smoothing, NaN-aware; ``widths`` one sigma per axis in
        the axis's units (0 leaves it). Returns the new row (tagged
        smoothed)."""
        from arpes_viewer.tools.processing.process import gaussian_smooth
        data = self.data(name)
        values = gaussian_smooth(data.values, data.axes, widths)
        return self._derive(name, values, data.axes, "smooth",
                            {"sigmas": widths}, new_name)

    @operation("Processing")
    @_keeps_selection
    def derivative(self, name: str, axis: int = 1, order: int = 2,
                   window: float = None, new_name: str = "") -> str:
        """The (negated) ``order``-th derivative along ``axis`` (index), by
        local polynomial fit over ``window`` (axis units). Returns the new
        row."""
        from arpes_viewer.tools.processing.process import derivative
        data = self.data(name)
        values = derivative(data.values, data.axes, int(axis), int(order),
                            window=window)
        return self._derive(name, values, data.axes, "derivative",
                            {"dim": axis, "order": order, "window": window},
                            new_name)

    @operation("Processing")
    @_keeps_selection
    def curvature(self, name: str, mode: str = "2d", a0: float = 1.0,
                  new_name: str = "") -> str:
        """Curvature of a 2-D cut or map plane: ``mode`` "2d" (isotropic),
        "x" or "y" (one-dimensional along that axis); ``a0`` the
        dimensionless free parameter. Returns the new row."""
        from arpes_viewer.tools.processing.process import curvature
        data = self.data(name)
        values = np.asarray(data.values, dtype=float)
        if values.ndim == 2:
            out = curvature(values, data.axes, mode=mode, a0=a0)
        else:
            out = np.stack([curvature(values[..., i], data.axes[:2], mode=mode,
                                      a0=a0) for i in range(values.shape[-1])],
                           axis=-1)
        return self._derive(name, out, data.axes, "curvature",
                            {"mode": mode, "a0": a0}, new_name)

    @operation("Processing")
    @_keeps_selection
    def background(self, name: str, method: str = "percentile", axis: int = 1,
                   new_name: str = "", **options) -> str:
        """Subtract a background from a cut: ``method`` "percentile",
        "polynomial", "shirley" or "tougaard" (see tools/processing), along
        ``axis`` for the one-dimensional ones. Returns the new row."""
        from arpes_viewer.tools.processing.process import subtract_background
        data = self.data(name)
        values, _background = subtract_background(data.values, data.axes,
                                                  method, dim=int(axis),
                                                  **options)
        return self._derive(name, values, data.axes, "background",
                            dict(options, method=method, dim=axis), new_name)

    @operation("Processing")
    @_keeps_selection
    def symmetrise(self, name: str, fold: int = 1, centre=(0.0, 0.0),
                   mirror_angles=(), inversion: bool = False,
                   new_name: str = "") -> dict:
        """Average a constant-energy map (each energy plane of a k-map, or a
        2-D map) over ``fold``-fold rotations, mirrors at ``mirror_angles``
        (degrees) and inversion, about ``centre`` -- which is yours to give,
        never guessed. Returns the new row and the residual."""
        from arpes_viewer.tools.processing.process import symmetrise
        data = self.data(name)
        values = np.asarray(data.values, dtype=float)
        x, y = data.axes[0], data.axes[1]
        options = dict(fold=int(fold), centre=tuple(centre),
                       mirror_angles=tuple(mirror_angles), inversion=bool(inversion))
        if values.ndim == 2:
            result = symmetrise(values, x, y, **options)
            out, residual = result.values, result.residual
        else:
            planes = [symmetrise(values[..., i], x, y, **options)
                      for i in range(values.shape[-1])]
            out = np.stack([p.values for p in planes], axis=-1)
            residual = float(np.mean([p.residual for p in planes]))
        row = self._derive(name, out, data.axes, "symmetry", options, new_name)
        return {"row": row, "residual": float(residual)}

    # ==================================================================
    # Momentum
    # ==================================================================
    @operation("Momentum")
    @_keeps_selection
    def cut_to_k(self, name: str, gamma_slit_deg: float = 0.0,
                 deflector_deg: float = 0.0, gamma_deflector_deg: float = None,
                 azimuth_deg: float = 0.0, n_k: int = None,
                 new_name: str = "") -> str:
        """A cut in momentum (k conversion, cut): normal emission at slit
        angle ``gamma_slit_deg``; the deflector or polar angle the cut was
        taken at and where Γ is on it, if off normal. A cut already on
        E - E_F stays on it. Returns the new row."""
        workspace, (ident,) = self._workspace(name)
        result = workspace.convert_cut(
            ident, gamma_slit_deg=gamma_slit_deg, deflector_deg=deflector_deg,
            gamma_deflector_deg=gamma_deflector_deg, azimuth_deg=azimuth_deg,
            n_k=n_k, name=new_name or None)
        record = workspace.get(result["id"])
        return self._list_scan(record["scan"], record["name"])

    @operation("Momentum")
    @_keeps_selection
    def map_to_k(self, name: str, gamma_deflector_deg: float = 0.0,
                 gamma_slit_deg: float = 0.0, azimuth_deg: float = 0.0,
                 n_kx: int = None, n_ky: int = None, new_name: str = "") -> str:
        """An angle map in momentum, (kx, ky, E) (k conversion, map): Γ at
        deflector/polar ``gamma_deflector_deg`` and slit ``gamma_slit_deg``,
        turned by ``azimuth_deg``. Convert a map already on E - E_F, so the
        result is too. Returns the new row (a k-map)."""
        workspace, (ident,) = self._workspace(name)
        result = workspace.convert_map(
            ident, gamma_deflector_deg=gamma_deflector_deg,
            gamma_slit_deg=gamma_slit_deg, azimuth_deg=azimuth_deg,
            n_kx=n_kx, n_ky=n_ky, name=new_name or None)
        record = workspace.get(result["id"])
        return self._list_scan(record["scan"], record["name"])

    @operation("Momentum")
    @_keeps_selection
    def kz_to_k(self, name: str, *, space_group: int, a: float, b: float = None,
                c: float = None, alpha: float = None, beta: float = None,
                gamma: float = None, surface_hkl=(0, 0, 1),
                kpar_rotation_deg: float = 0.0, inner_potential: float = None,
                gamma_hv: float = None, work_function: float = None,
                effective_mass: float = 1.0, normal_emission_deg: float = 0.0,
                theta_offset_deg: float = None, calibrate_hv: bool = False,
                n_kz: int = None, n_kpar: int = None) -> dict:
        """A photon-energy scan (on E - E_F) in (k_z, k//, E), as the kz
        conversion window does it. Give ``inner_potential`` (V0, eV), or
        ``gamma_hv``: the photon energy at which normal emission passes
        through Γ, from which V0 is set. The lattice decides the zone and
        the period; ``surface_hkl`` the surface normal; k// runs along a*
        (or the first reciprocal axis not along the normal) turned by
        ``kpar_rotation_deg``. ``theta_offset_deg`` only to correct a
        manipulator offset from Γ; ``calibrate_hv`` uses each photon energy's
        fitted E_F (after kz_align_fermi). Grid: from the measurement unless
        given. Returns the new row, V0 and the k ranges."""
        from arpes_viewer.tools.momentum import kzconv
        key = self._key(name)
        self.select(self._name(key))
        dialog = self.A.open_kz_conversion()
        if dialog is None:
            raise ValueError(f"{name!r} is not a photon-energy scan (kz map)")
        try:
            dialog.space_group.setValue(int(space_group))
            for box, value in ((dialog.lat_a, a), (dialog.lat_b, b),
                               (dialog.lat_c, c), (dialog.lat_alpha, alpha),
                               (dialog.lat_beta, beta), (dialog.lat_gamma, gamma)):
                if value is not None and box.isEnabled():
                    box.setValue(float(value))
            dialog._sync_mirrored_lengths()
            dialog._lattice_changed()
            wanted = tuple(int(v) for v in surface_hkl)
            from arpes_viewer.ui.panels.kzconv import _same_direction
            for index in range(dialog.normal_index.count()):
                data = dialog.normal_index.itemData(index)
                if data is not None and _same_direction(data[0], wanted):
                    dialog.normal_index.setCurrentIndex(index)
                    break
            else:
                raise ValueError(f"surface {wanted} is not among the lattice's "
                                 f"planes for this cell")
            for box in (dialog.kpar_h, dialog.kpar_k, dialog.kpar_l):
                box.setValue(0)
            dialog.kpar_rotation.setValue(float(kpar_rotation_deg))
            if work_function is not None:
                dialog.work_function.setValue(float(work_function))
            dialog.effective_mass.setValue(float(effective_mass))
            dialog.angle_offset.setValue(float(normal_emission_deg))
            dialog.theta_correct.setChecked(theta_offset_deg is not None)
            dialog.theta_position.setValue(float(theta_offset_deg or 0.0))
            if calibrate_hv and not dialog.calibrate_hv.isEnabled():
                raise ValueError("no per-photon-energy Fermi levels on this "
                                 "row: run kz_align_fermi first")
            dialog.calibrate_hv.setChecked(bool(calibrate_hv))
            order = None
            if gamma_hv is not None:
                dialog.gamma_hv.setValue(float(gamma_hv))
                _v0, order = dialog.set_v0_from_gamma()
            elif inner_potential is not None:
                dialog.inner_potential.setValue(float(inner_potential))
            else:
                raise ValueError("give inner_potential or gamma_hv")
            dialog.default_grid()
            if n_kz:
                dialog.n_kz.setValue(int(n_kz))
            if n_kpar:
                dialog.n_kpar.setValue(int(n_kpar))
            cube = np.asarray(dialog.contour.full_cube(), dtype=float)
            converted = kzconv.to_kz_cube(
                dialog.hv, dialog.angle, dialog.energy, cube,
                n_kz=int(dialog.n_kz.value()), n_kpar=int(dialog.n_kpar.value()),
                **dialog.settings())
            before = set(self.A.loaded_items)
            dialog._finish(converted)
            added = [self._name(k) for k in self.A.loaded_items if k not in before]
            kz_axis, kpar_axis = converted[0], converted[1]
            return {"row": added[-1] if added else "",
                    "inner_potential_eV": float(dialog.inner_potential.value()),
                    "gamma_zone_order": order,
                    "kz_range": [float(kz_axis[0]), float(kz_axis[-1])],
                    "kpar_range": [float(kpar_axis[0]), float(kpar_axis[-1])],
                    "surface_period_invA": float(dialog.surface_period()),
                    "points_in_plane": [p for p, _k in dialog.points_in_plane()]}
        finally:
            dialog.close()

    # ==================================================================
    # Crystal and Brillouin zone
    # ==================================================================
    @operation("Crystal and Brillouin zone")
    def brillouin_zone(self, space_group: int, a: float, b: float = None,
                       c: float = None, alpha: float = 90.0, beta: float = 90.0,
                       gamma: float = None) -> dict:
        """The zone's high-symmetry points (Cartesian, Å⁻¹) and the
        reciprocal vectors, for a space group and cell; the parameters the
        space group fixes are set by it."""
        from arpes_viewer.agent.workspace import Workspace
        return _plain(Workspace.brillouin_zone(space_group, a, b, c, alpha,
                                               beta, gamma))

    @operation("Crystal and Brillouin zone")
    def read_cif(self, path: str) -> dict:
        """A CIF file's cell, space group and atom sites."""
        from arpes_viewer.agent.workspace import Workspace
        return _plain(Workspace.read_cif(os.path.expanduser(path)))

    @operation("Crystal and Brillouin zone")
    @_keeps_selection
    def bz_overlay(self, name: str, *, space_group: int, a: float,
                   b: float = None, c: float = None, alpha: float = None,
                   beta: float = None, gamma: float = None, hkl=(0, 0, 1),
                   offset: float = 0.0, azimuth_deg: float = 0.0,
                   kpar_hkl=(0, 0, 0), repeat: bool = True,
                   labels: bool = True, irreducible: bool = False,
                   layer_2d: bool = False) -> dict:
        """Draw the Brillouin zone on a k-map (or a converted kz map) and
        keep it with the row, as BZ overlap does: the cut of the 3-D zone by
        the plane normal to ``hkl`` at ``offset`` (Å⁻¹ along it), turned by
        ``azimuth_deg``; for a kz map, ``hkl`` is the surface normal and
        ``kpar_hkl`` the k// direction. ``layer_2d`` uses a plane lattice
        (a, b, gamma) instead. The zone then goes into slice series and
        exports. Returns what was drawn."""
        key = self._key(name)
        self.select(self._name(key))
        contour = self.A.map_contour(key)
        if contour is None:
            raise ValueError(f"{name!r} could not be opened")
        dialog = contour.open_brillouin_zone(bound=False)
        try:
            (dialog.mode_2d if layer_2d else dialog.mode_3d).setChecked(True)
            (dialog.zone_irreducible if irreducible
             else dialog.zone_conventional).setChecked(True)
            if layer_2d:
                dialog.a2_box.setValue(float(a))
                dialog.b2_box.setValue(float(b if b is not None else a))
                dialog.gamma2_box.setValue(float(gamma if gamma is not None else 120.0))
            else:
                dialog.spacegroup_box.setValue(int(space_group))
                for box, value in ((dialog.a_box, a), (dialog.b_box, b),
                                   (dialog.c_box, c), (dialog.alpha_box, alpha),
                                   (dialog.beta_box, beta), (dialog.gamma_box, gamma)):
                    if value is not None and box.isEnabled():
                        box.setValue(float(value))
                for box, value in zip((dialog.h_box, dialog.k_box, dialog.l_box), hkl):
                    box.setValue(int(value))
                for box, value in zip((dialog.kpar_h_box, dialog.kpar_k_box,
                                       dialog.kpar_l_box), kpar_hkl):
                    box.setValue(int(value))
                dialog.offset_box.setValue(float(offset))
            dialog.azimuth_box.setValue(float(azimuth_deg))
            dialog.tile_cb.setChecked(bool(repeat))
            dialog.labels_cb.setChecked(bool(labels))
            message = dialog.plot()
            if message is None:
                raise ValueError(dialog.note.text())
            return {"drawn": message,
                    "cut": dialog.cut_description() if not layer_2d else ""}
        finally:
            dialog.close()

    @operation("Crystal and Brillouin zone")
    def bz3d_picture(self, path: str, *, space_group: int, a: float,
                     b: float = None, c: float = None, alpha: float = None,
                     beta: float = None, gamma: float = None, planes=((0, 0, 1, 0.0),),
                     paths=("",), frame: str = "crystal", surface_hkl=(0, 0, 1),
                     azimuth_deg: float = 0.0, axes: bool = True,
                     labels: bool = True, left_labels: str = "",
                     view="oblique", size=(1600, 1600), panel_mm: float = 0.0,
                     text_pt: float = 8.0) -> dict:
        """A picture of the 3-D Brillouin zone (the 3D BZ window), for a
        schematic panel: ``planes`` as (h, k, l, height) with height in units
        of the reciprocal vector (0 through Γ, 0.5 the zone top); ``paths``
        like "G-M-K-G"; axes in the crystal frame (k_a, k_b, k_c) or, with
        ``frame="sample"``, the data's (k_x, k_y, k_z: k_z along
        ``surface_hkl``, k_x turned by ``azimuth_deg``); ``view`` "oblique",
        an axis name or a vector; labels sized for a ``panel_mm`` wide panel
        at ``text_pt`` if given. Never overwrites ``path``."""
        path = os.path.expanduser(path)
        if os.path.exists(path):
            raise FileExistsError(f"{path} exists; give a new name")
        from arpes_viewer.ui.panels.bz3d import BrillouinZone3DDialog
        dialog = BrillouinZone3DDialog()
        try:
            dialog.cell_input.set_cell(int(space_group), a, b, c, alpha, beta, gamma)
            for row in list(dialog.plane_rows):
                dialog.remove_plane(row)
            for plane in planes:
                h, k, l, height = plane
                dialog.add_plane((int(h), int(k), int(l)), float(height))
            for row in list(dialog.path_rows):
                dialog.remove_path(row)
            for text in paths:
                dialog.add_path(str(text))
            dialog.axes_box.setChecked(bool(axes))
            dialog.labels_box.setChecked(bool(labels))
            dialog.left_edit.setText(left_labels)
            dialog.set_frame(frame, surface_hkl, azimuth_deg)
            dialog.width_box.setValue(int(size[0]))
            dialog.height_box.setValue(int(size[1]))
            dialog.panel_mm_box.setValue(float(panel_mm))
            dialog.text_pt_box.setValue(float(text_pt))
            dialog.refresh()
            dialog.look_along(view)
            dialog.save_picture(path)
            return {"path": path, "axes": list(dialog.view.zone_axis_names),
                    "label_px": dialog.label_px()}
        finally:
            dialog.close()

    # ==================================================================
    # Figures
    # ==================================================================
    def _figure(self, title: str = ""):
        from PyQt5.QtWidgets import QApplication
        from arpes_viewer.ui.panels.figure import FigureWindow
        figures = [w for w in QApplication.topLevelWidgets()
                   if isinstance(w, FigureWindow) and w.isVisible()]
        if title:
            exact = [w for w in figures if w.windowTitle() == title]
            figures = exact or [w for w in figures
                                if title.lower() in w.windowTitle().lower()]
        if not figures:
            raise KeyError(f"no figure window titled like {title!r}")
        return figures[-1]

    def _figure_made(self, window, title: str) -> dict:
        if window is None:
            raise ValueError("no figure was made")
        if title:
            window.setWindowTitle(title)
        return window.describe()

    @operation("Figures")
    @_keeps_selection
    def slice_series(self, name: str, values, *, axis: int = 2,
                     half_width: float = 0.0, cols: int = 3,
                     nominal_titles: bool = True, shared: bool = True,
                     colormap: str = None, flip: bool = None,
                     percentiles=(0.0, 100.0), gamma: float = 1.0,
                     zone: bool = True, zone_style: str = "solid",
                     title: str = "") -> dict:
        """A page of slices through a map (Slice series figure): one panel
        per value along ``axis`` (2 = energy), each the planes within
        ``half_width``, titled with the value asked for; colour map, levels
        (percentiles), gamma at creation; the row's Brillouin zone on
        constant-energy panels. Returns the figure in numbers (its title
        names it for the other figure operations)."""
        self.select(name)
        window = self.A.open_slice_series(
            values=list(values), axis=int(axis), half_width=float(half_width),
            cols=int(cols), nominal_titles=nominal_titles, shared=shared,
            colormap=colormap, flip=flip, percentiles=tuple(percentiles),
            gamma=float(gamma), zone=bool(zone), zone_style=zone_style)
        return self._figure_made(window, title)

    @operation("Figures")
    @_keeps_selection
    def figure_from(self, *names, title: str = "") -> dict:
        """A figure composer with these rows as panels (as "Plot as
        figure"). Returns the figure in numbers."""
        self.select(*names)
        window = self.A.plot_selected_as_figure()
        return self._figure_made(window, title)

    @operation("Figures")
    def figures(self) -> list:
        """The titles of the open figure windows: the names the other figure
        operations take."""
        from PyQt5.QtWidgets import QApplication
        from arpes_viewer.ui.panels.figure import FigureWindow
        return [w.windowTitle() for w in QApplication.topLevelWidgets()
                if isinstance(w, FigureWindow) and w.isVisible()]

    @operation("Figures")
    def figure_describe(self, title: str = "") -> dict:
        """A figure in numbers: page size, each panel's frame (mm), title,
        axis names, colour scale, text sizes. Check a layout with this, not
        with a picture."""
        return self._figure(title).describe()

    @operation("Figures")
    def figure_style(self, title: str = "", **style) -> dict:
        """Set the figure's style: width_mm, height_mm, font_pt, gap_x_mm,
        gap_y_mm, edge_labels_only, inner_tick_numbers, shared_levels,
        equal_aspect, panel_label_position ... (FigureStyle). Returns the
        figure in numbers."""
        window = self._figure(title)
        known = set(vars(window.figure.style))
        unknown = set(style) - known
        if unknown:
            raise ValueError(f"no style {sorted(unknown)}; known: {sorted(known)}")
        for key, value in style.items():
            setattr(window.figure.style, key, value)
        window.refresh()
        return window.describe()

    @operation("Figures")
    def panel_set(self, title: str = "", index: int = 0, **attributes) -> dict:
        """Set panel ``index`` of a figure: colormap, flip, levels (lo, hi),
        gamma, title, x_label, y_label, x_range, y_range, colorbar, span
        (rows, cols), font_pt ... (figure Panel). Returns the figure in
        numbers."""
        window = self._figure(title)
        panel = window.figure.panels[int(index)]
        known = set(vars(panel))
        unknown = set(attributes) - known
        if unknown:
            raise ValueError(f"no panel attribute {sorted(unknown)}")
        for key, value in attributes.items():
            setattr(panel, key, tuple(value) if isinstance(value, list) else value)
        window.refresh()
        return window.describe()

    @operation("Figures")
    def panel_picture(self, title: str = "", index: int = 0, path: str = "",
                      span=None) -> dict:
        """Fill panel ``index`` with a picture file (a schematic, a 3D BZ
        picture); it keeps its own shape. ``span`` (rows, cols) lets it take
        several grid cells at the next arrange."""
        window = self._figure(title)
        panel = window.figure.panels[int(index)]
        window.load_picture(panel, os.path.expanduser(path))
        if span is not None:
            panel.span = tuple(int(v) for v in span)
        return window.describe()

    @operation("Figures")
    def figure_arrange(self, title: str = "", rows: int = 1, cols: int = 1) -> dict:
        """Put the panels on a rows x cols grid (each taking its span), the
        page height following. Returns the figure in numbers."""
        window = self._figure(title)
        window.figure.freeze()
        window.figure.arrange_grid(int(rows), int(cols))
        window.refresh()
        return window.describe()

    @operation("Figures")
    def figure_render(self, title: str = "", path: str = "", dpi: int = 0) -> dict:
        """Write the figure as a PNG, as it will print (not a screenshot),
        and return its numbers. Never overwrites ``path``."""
        path = os.path.expanduser(path)
        if os.path.exists(path):
            raise FileExistsError(f"{path} exists; give a new name")
        return self._figure(title).render(path, dpi=int(dpi) or None)

    @operation("Figures")
    def figure_export(self, title: str = "", path: str = "") -> list:
        """Write the figure as PDF, SVG, PNG or TIFF (from the extension).
        Never overwrites. Returns the files written."""
        path = os.path.expanduser(path)
        if os.path.exists(path):
            raise FileExistsError(f"{path} exists; give a new name")
        fmt = os.path.splitext(path)[1].lstrip(".").lower()
        fmt = {"tiff": "tif"}.get(fmt, fmt)
        return list(self._figure(title).write(path, fmt))

    @operation("Figures")
    def figure_save(self, title: str = "", path: str = "",
                    with_data: bool = True) -> str:
        """Save the figure as an .afig file to open and edit again, with
        (``with_data``) the data of each panel in "data for <name>" beside
        it -- leave that out of anything shared. Never overwrites."""
        path = os.path.expanduser(path)
        if os.path.exists(path):
            raise FileExistsError(f"{path} exists; give a new name")
        return self._figure(title).save_file(path, with_data=bool(with_data))

    # ==================================================================
    # Tool windows
    # ==================================================================
    @operation("Tool windows")
    def tools(self) -> list:
        """Every tool-panel button, by action name, with what it acts on --
        for the tools that have no operation of their own here (MDC/EDC
        fits, core levels, detector corrections, tight-binding fit,
        calculated bands, 3-D views ...). Open one with ``run_tool``."""
        from arpes_viewer.agent.catalog import tool_actions
        return tool_actions()

    @operation("Tool windows")
    @_keeps_selection
    def run_tool(self, action: str, *names) -> str:
        """Select ``names`` and open the tool ``action`` (see ``tools()``)
        on them, on screen. Returns the title of the window it opened. Its
        controls are then the window's own; prefer an operation here where
        there is one."""
        from PyQt5.QtWidgets import QApplication
        if names:
            self.select(*names)
        before = set(QApplication.topLevelWidgets())
        self.A.run_list_action(action)
        QApplication.processEvents()
        new = [w for w in QApplication.topLevelWidgets()
               if w not in before and w.isVisible() and w.windowTitle()]
        return new[-1].windowTitle() if new else ""

    @operation("Tool windows")
    def windows(self) -> list:
        """The titles of the program's open windows (viewers, tools,
        figures), for ``close`` and for knowing what is on screen."""
        from PyQt5.QtWidgets import QApplication
        return [w.windowTitle() for w in QApplication.topLevelWidgets()
                if w.isVisible() and w.windowTitle()]

    @operation("Tool windows")
    def close(self, title: str) -> str:
        """Close a window by (part of) its title; not the main window."""
        from PyQt5.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            if (widget.isVisible() and title.lower() in widget.windowTitle().lower()
                    and widget is not self.A.win):
                text = widget.windowTitle()
                widget.close()
                return text
        raise KeyError(f"no open window titled like {title!r}")

    # ==================================================================
    # Your own computation
    # ==================================================================
    @operation("Your own computation")
    def data(self, name: str) -> Dataset:
        """A row's data as plain arrays (``.kind``, ``.axes``, ``.labels``,
        ``.values``, ``.info``), for a computation the operations above do
        not cover -- with the program's own functions (``functions()``)
        where there is one. Say so when you compute something yourself."""
        scan = self._scan(name)
        slots = scan.axis_slots("array")
        return Dataset(self._name(self._key(name)), scan.kind,
                       [np.asarray(getattr(scan, s), dtype=float) for s in slots],
                       [scan.labels.get(s, s) for s in slots],
                       np.asarray(scan.array()), dict(scan.info or {}))

    @operation("Your own computation")
    @_keeps_selection
    def add(self, name: str, kind: str, axes, values, labels=None, info=None,
            made_from: str = "", step: str = "computed",
            parameters: dict = None) -> str:
        """Put a result of your own on the list as a new row: ``kind``
        "cut", "map", "k_map", "kz_map", "kz_map_k", "edc", "mdc" ...;
        ``axes`` one array per dimension (array order); ``labels`` one per
        axis. With ``made_from`` (a row) the new row carries its metadata
        and a history step (``step``, ``parameters``) saying how it was
        made. Returns the row's name."""
        from arpes_viewer.loader.scan import NxsScan, axis_slots
        from arpes_viewer.tools.processing.process import Step, record_step
        slots = axis_slots(kind, "array")
        if len(slots) != len(axes):
            raise ValueError(f"a {kind} has {len(slots)} axes {slots}")
        base = dict(self._scan(made_from).info or {}) if made_from else {}
        base.update(info or {})
        base = record_step(base, Step(step, _plain(parameters or {}),
                                      source=made_from))
        labels = list(labels or slots)
        scan = NxsScan(kind=kind, info=base,
                       labels={s: str(l) for s, l in zip(slots, labels)},
                       value=np.asarray(values))
        for slot, axis in zip(slots, axes):
            setattr(scan, slot, np.asarray(axis, dtype=float))
        return self._list_scan(scan, name)

    @operation("Your own computation")
    def functions(self, module: str = "") -> str:
        """The program's own computations (Qt-free, under
        ``arpes_viewer.tools``) with their signatures and what each does:
        all modules, or one (e.g. "spectra.peaks"). Use these on
        ``data(name).values`` rather than writing your own."""
        from arpes_viewer.agent.catalog import functions_reference
        text = functions_reference(module)
        print(text)
        return text


def operations():
    """``[(group, name, method)]`` of every operation, in group order."""
    found = []
    for name, member in inspect.getmembers(Live, predicate=inspect.isfunction):
        group = getattr(member, "_operation", None)
        if group:
            found.append((GROUPS.index(group), name, member))
    order = {name: i for i, name in enumerate(Live.__dict__)}
    found.sort(key=lambda t: (t[0], order.get(t[1], 0)))
    return [(GROUPS[g], name, member) for g, name, member in found]
