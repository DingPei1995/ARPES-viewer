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
    L.shift_energy("cut1", ef=-0.012)          # -> "cut1 [E-E_F]"
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
``arpes_viewer/agent/API.md`` by :mod:`agent.catalog`; a test fails when the two
drift apart, so the reference an agent reads is always the program's own.
"""
from __future__ import annotations

import inspect
import os

import numpy as np

from arpes_viewer.ui.common.paths import native

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
        import functools

        @functools.wraps(function)
        def run(*args, **kwargs):
            # windows opened and closed again inside an operation never
            # flash on screen; those it leaves open appear on the main
            # panel's screen (ui.common.quietwindows)
            from arpes_viewer.ui.common.quietwindows import agent_windows
            with agent_windows():
                return function(*args, **kwargs)
        run._operation = group
        return run
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


def _strip_tags(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", str(text))


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
        ``arpes_viewer/agent/API.md``) before anything else: it is the program's own
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

    @operation("Start here")
    def session_script(self, path: str, with_output: bool = True) -> dict:
        """Write every step run so far in this session -- command files
        and MCP requests, oldest first -- as one Python script at ``path``:
        each step's code, when it ran, whether it failed (those are kept
        as comments) and, with ``with_output``, what it printed. The record
        of the whole processing, and a script that does it again. Call it
        at the end, as a step of its own (the step calling it is not yet
        in the record). Returns ``{"path", "steps", "failed"}``."""
        from arpes_viewer.ui.common import agentsteps
        return agentsteps.save(self.A, path, with_output=with_output)

    # ==================================================================
    # The list
    # ==================================================================
    def _key(self, name):
        """The list key of the row called ``name`` (exact, else the one row
        whose name contains it); an ``int`` is the row's number in
        ``rows()``, and the path of a file reaches the one row read from it
        -- for rows that share a name."""
        items = self.A.loaded_items
        if isinstance(name, (int, np.integer)) and not isinstance(name, bool):
            widget = self.A.ui.FilePathListWidget
            if not 0 <= int(name) < widget.count():
                raise KeyError(f"no row number {int(name)}; the list has "
                               f"{widget.count()} rows (0-{widget.count() - 1})")
            return widget.item(int(name)).data(0x0100)
        name = str(name)
        exact = [k for k, r in items.items() if r.get("name") == name]
        if len(exact) == 1:
            return exact[0]
        found = [k for k, r in items.items()
                 if name.lower() in str(r.get("name", "")).lower()]
        if len(found) == 1 and not exact:
            return found[0]
        if os.path.sep in name or "/" in name:
            wanted = os.path.normcase(os.path.normpath(name))
            by_path = [k for k, r in items.items() if r.get("path") and
                       os.path.normcase(os.path.normpath(str(r["path"]))) == wanted]
            if len(by_path) == 1:
                return by_path[0]
        names = [str(items[k].get("name")) for k in (exact or found)]
        if not names:
            raise KeyError(f"no row called {name!r}; rows: "
                           f"{[r.get('name') for r in items.values()]}")
        raise KeyError(f"{name!r} matches several rows: {names}; give the "
                       f"whole name, the row's number in rows() or its path")

    def _name(self, key) -> str:
        return str(self.A.loaded_items[key].get("name"))

    @operation("The list")
    def rows(self, compact: bool = False):
        """The rows of the main list: ``row`` (its number, which every
        operation also takes in place of a name), ``name``, ``kind`` (Cut,
        Map, kz map, k-map ...), ``path`` of the file behind it, and whether
        it is selected. ``compact=True`` gives one line per row instead
        ("3 | Map LH 117eV | Map | D:\\...\\Map_1_ROI1_.txt"): a long list
        costs far fewer tokens that way."""
        A = self.A
        widget = A.ui.FilePathListWidget
        out = []
        for i in range(widget.count()):
            item = widget.item(i)
            key = item.data(0x0100)
            record = A.loaded_items.get(key, {})
            out.append({"row": i, "name": record.get("name", item.text()),
                        "kind": record.get("kind", ""),
                        "path": native(record.get("path", "")) or "",
                        "selected": item.isSelected()})
        if compact:
            return "\n".join(f"{r['row']} | {r['name']} | {r['kind']} | "
                             f"{r['path']}" + (" | selected" if r["selected"] else "")
                             for r in out)
        return out

    @operation("The list")
    @_keeps_selection
    def add_files(self, paths, extras: bool = False) -> dict:
        """Add files to the list, the reader detected as by Quick add.
        ``paths`` is one path or a list; a folder adds every file in it a
        reader recognises, and the scans in its sub-folders (a CASSIOPEE
        map folder is one row). Returns ``added`` (the names of the new
        rows), and what to tell the person before going on:

        * ``left_out``: single spectra found inside a sub-folder next to a
          map's numbered scans (a test spectrum, a reference ...) -- not
          part of the map, so not listed unless ``extras=True``;
        * ``unrecognised``: files no reader took (parameter files, notes);
        * ``warnings``: what a reader noticed, e.g. a polarisation in the
          file name that differs from the one recorded with the data.

        Row names come from the file or folder name, with the photon energy
        and polarisation the beamline recorded; names are unique."""
        if isinstance(paths, str):
            paths = [paths]
        files, unrecognised, folders = [], [], []
        for path in paths:
            path = native(path)
            if os.path.isdir(path):
                folders.append(path)
            found, skipped = self._expand(path, report=True)
            files += found
            unrecognised += skipped
        before = set(self.A.loaded_items)
        self.A.add_files(files, background=False)
        new = [k for k in self.A.loaded_items if k not in before]
        left_out = []
        if folders and not extras:
            records = self.A.loaded_items
            series_dirs = {os.path.dirname(str(records[k].get("path", "")))
                           for k in new if records[k].get("entry") == "series"}
            loose = [k for k in new if records[k].get("entry") != "series"
                     and os.path.dirname(str(records[k].get("path", ""))) in series_dirs
                     and os.path.dirname(str(records[k].get("path", ""))) not in folders]
            if loose:
                left_out = [native(records[k].get("path", "")) for k in loose]
                self.A._remove_keys(loose)
                new = [k for k in new if k not in loose]
        warnings = []
        for k in new:
            record = self.A.loaded_items[k]
            if record.get("warning"):
                warnings.append(f"{record.get('name')}: {record['warning']}")
        added = [self._name(k) for k in new]
        out = {"added": added, "rows": len(self.A.loaded_items)}
        if left_out:
            out["left_out"] = left_out
            out["left_out_note"] = (
                "single spectra in a map's folder, not part of the map; tell "
                "the person, and add them with add_files(path) if wanted")
        if unrecognised:
            out["unrecognised"] = unrecognised[:30] + (
                [f"... {len(unrecognised) - 30} more"] if len(unrecognised) > 30 else [])
        if warnings:
            out["warnings"] = warnings
        return out

    @staticmethod
    def _expand(path: str, report: bool = False):
        """A file as itself; a folder as the recognised files in it and in
        its sub-folders one level down (the loaders list a numbered series
        once, whichever of its files is given). With ``report``, also the
        files no reader recognised: ``(found, unrecognised)``."""
        if not os.path.isdir(path):
            return ([path], []) if report else [path]
        from arpes_viewer.loader import registry
        found, skipped = [], []
        for folder in [path] + sorted(
                os.path.join(path, d) for d in os.listdir(path)
                if os.path.isdir(os.path.join(path, d))):
            for name in sorted(os.listdir(folder)):
                candidate = os.path.join(folder, name)
                if not os.path.isfile(candidate):
                    continue
                if registry.detect(candidate):
                    found.append(candidate)
                elif not (name.startswith(".") or
                          os.path.splitext(name)[0].endswith("_i")):
                    # (a CASSIOPEE scan's parameter file "<scan>_i.txt" is
                    # read with its scan, not on its own)
                    skipped.append(os.path.relpath(candidate, path))
        return (found, skipped) if report else found

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
    def naming(self) -> str:
        """How a processed row is named: its source's name plus one tag in
        square brackets per step, oldest first ('Map80eV [norm] [E-E_F]
        [k]'), from the ordered table returned here. Every operation names
        its result this way; a ``new_name=`` of your own keeps the tags and
        adds the step's tag in brackets too, so "Sort by data type" groups
        the list by what was last done."""
        from arpes_viewer.tools.runtime.naming import naming_rule
        return naming_rule()

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
        path = native(path)
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
        path = native(path)
        workspace, (ident,) = self._workspace(name)
        _png, summary = workspace.image(ident, x, y, ranges, colormap, flip,
                                        width, height, levels, gamma, path, None)
        summary["saved_png"] = native(summary.get("saved_png")) or ""
        return _plain(summary)

    @operation("Looking at data")
    def profile(self, name: str, along, ranges=None, summary: bool = False,
                path: str = "", max_points: int = 400) -> dict:
        """An EDC or MDC as numbers: the values along one axis, the others
        integrated over ``ranges`` ({axis: (lo, hi)}). Hundreds of numbers
        cost many tokens: ``summary=True`` gives only the axis range and
        step, the maximum (where), the minimum, and the steepest fall and
        rise; ``path`` writes the whole curve to a CSV file (then read it
        with your own code); ``max_points`` thins what is returned."""
        workspace, (ident,) = self._workspace(name)
        out = workspace.profile(ident, along, ranges,
                                max_points=1 << 30 if summary else int(max_points),
                                path=native(path) or None)
        out["saved"] = native(out.get("saved")) or ""
        if summary:
            x = np.asarray(out.pop("x"), dtype=float)
            y = np.asarray(out.pop("y"), dtype=float)
            out.pop("every", None)
            good = np.isfinite(x) & np.isfinite(y)
            x, y = x[good], y[good]
            if x.size >= 3:
                order = np.argsort(x)
                x, y = x[order], y[order]
                smooth = np.convolve(y, np.ones(3) / 3.0, mode="same")
                slope = np.gradient(smooth, x)
                slope[:2] = slope[-2:] = 0.0
                out.update({
                    "range": [float(x[0]), float(x[-1])],
                    "step": float(np.median(np.diff(x))),
                    "max": [float(x[np.argmax(y)]), float(np.max(y))],
                    "min": [float(x[np.argmin(y)]), float(np.min(y))],
                    "steepest_fall_at": float(x[np.argmin(slope)]),
                    "steepest_rise_at": float(x[np.argmax(slope)])})
        return _plain(out)

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
                   fit_temperature: bool = False, picture: str = "") -> dict:
        """Fit the Fermi edge of the EDC summed over ``ranges`` of the other
        axes, within ``energy_window`` (lo, hi) on the row's own energy axis.
        The temperature is held unless ``fit_temperature``. Returns E_F,
        the resolution, their errors and the reduced chi2; a fit that finds
        no edge (normalised data, a window without the edge) is refused
        with the reason, the row's energy axis, and where the curve falls
        fastest. Each row has its own energy axis: choose the window per
        row (``fermi_edge_search`` lists the candidate edges), never reuse
        another row's. ``picture`` writes a PNG of the EDC, the window and
        the fitted curve -- for the person to check, also when the fit is
        refused."""
        workspace, (ident,) = self._workspace(name)
        try:
            out = workspace.fermi_edge(ident, energy_window, temperature,
                                       ranges, fit_temperature)
        except ValueError as exc:
            energy, edc = self._edc(workspace, ident, ranges)
            from arpes_viewer.tools.spectra.fermi import steepest_drop
            inside = np.ones(energy.size, bool)
            if energy_window:
                inside = (energy >= min(energy_window)) & (energy <= max(energy_window))
            hint = (f"; the energy axis runs {energy.min():.4f}..{energy.max():.4f} eV"
                    f" (step {abs(np.median(np.diff(energy))):.4g})")
            if inside.sum() >= 7:
                hint += (f"; inside the window the curve falls fastest at "
                         f"{steepest_drop(energy[inside], edc[inside]):.4f} eV")
            elif energy_window:
                hint += "; the window holds (almost) no points of it"
            if picture:
                self._edc_picture(picture, energy, edc, energy_window, None,
                                  f"{self._name(self._key(name))}: refused")
            raise ValueError(f"{exc}{hint}; fermi_edge_search(name) lists the "
                             f"candidate edges") from None
        self._record_edge(name, out, energy_window)
        if picture:
            energy, edc = self._edc(workspace, ident, ranges)
            out["picture"] = self._edc_picture(
                picture, energy, edc, energy_window, out["values"],
                f"{self._name(self._key(name))}: E_F = {out['values']['ef']:.4f} eV")
        return _plain(out)

    def _record_edge(self, name, out, energy_window):
        """Keep a Fermi edge fit with the row, as the Fermi edge fit tool
        does: the row is then a reference for ``fs_correction``."""
        import json
        from arpes_viewer.ui.viewers.windows import FERMI_FIT_KEY, fermi_fit_of
        key = self._key(name)
        record = self.A.loaded_items.get(key) or {}
        state = fermi_fit_of(record.get("properties") or {})
        values, errors = out.get("values", {}), out.get("errors", {})
        state["edge"] = {
            "ef": float(values["ef"]),
            "ef_err": float(errors.get("ef", float("nan"))),
            "resolution": float(values.get("resolution", float("nan"))),
            "temperature": float(values.get("temperature", float("nan"))),
            "window": [float(v) for v in energy_window] if energy_window else None}
        self.A._set_row_properties(key, {FERMI_FIT_KEY: json.dumps(
            state, separators=(",", ":"))})

    @staticmethod
    def _edc(workspace, ident, ranges):
        """The EDC the Fermi fit sees: energy ascending, other axes averaged."""
        e = workspace.axis_index(ident, "energy")
        values, (energy,) = workspace._window(ident, (e,), ranges)
        energy = np.asarray(energy, dtype=float)
        values = np.asarray(values, dtype=float)
        order = np.argsort(energy)
        return energy[order], values[order]

    @staticmethod
    def _edc_picture(path, energy, edc, window, values, title) -> str:
        """A PNG of an EDC, the fit window (grey) and the fitted edge (red)."""
        from PyQt5.QtCore import QPointF, QRectF, Qt
        from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
        path = native(path)
        if os.path.exists(path):
            raise FileExistsError(f"{path} exists; give a new name")
        width, height, m = 760, 460, 54
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        good = np.isfinite(edc)
        x0, x1 = float(energy.min()), float(energy.max())
        y0 = float(np.nanmin(edc)) if good.any() else 0.0
        y1 = float(np.nanmax(edc)) if good.any() else 1.0
        y1 = y1 if y1 > y0 else y0 + 1.0
        box = QRectF(m, 30, width - m - 20, height - 30 - m)

        def at(x, y):
            return QPointF(box.left() + (x - x0) / (x1 - x0 or 1) * box.width(),
                           box.bottom() - (y - y0) / (y1 - y0) * box.height())
        if window:
            lo, hi = sorted(float(v) for v in window)
            a, b = at(max(lo, x0), y0), at(min(hi, x1), y1)
            painter.fillRect(QRectF(a.x(), b.y(), b.x() - a.x(), a.y() - b.y()),
                             QColor(225, 225, 225))
        painter.setPen(QPen(QColor("#333333"), 1))
        painter.drawRect(box)

        def curve(xs, ys, colour, pen_width):
            line = QPainterPath()
            first = True
            for x, y in zip(xs, ys):
                if not np.isfinite(y):
                    first = True
                    continue
                point = at(float(x), float(y))
                line.moveTo(point) if first else line.lineTo(point)
                first = False
            painter.setPen(QPen(QColor(colour), pen_width))
            painter.drawPath(line)
        curve(energy, edc, "#1f4fa8", 1.4)
        if values:
            from arpes_viewer.tools.spectra.fermi import fermi_edge_model
            from arpes_viewer.tools.spectra.fermi import PARAMETERS
            lo, hi = (sorted(float(v) for v in window) if window else (x0, x1))
            xs = np.linspace(max(lo, x0), min(hi, x1), 300)
            curve(xs, fermi_edge_model(xs, **{k: values[k] for k in PARAMETERS}),
                  "#d62020", 2.0)
            ef = at(float(values["ef"]), y0)
            painter.setPen(QPen(QColor("#d62020"), 1, Qt.DashLine))
            painter.drawLine(QPointF(ef.x(), box.top()), QPointF(ef.x(), box.bottom()))
        painter.setPen(QColor("#111111"))
        painter.drawText(QRectF(m, 4, width - m, 22), Qt.AlignLeft, title)
        painter.drawText(QRectF(m, height - m + 6, 120, 20), Qt.AlignLeft, f"{x0:.3f}")
        painter.drawText(QRectF(width - 140, height - m + 6, 120, 20),
                         Qt.AlignRight, f"{x1:.3f}")
        painter.drawText(QRectF(m, height - 26, width - 2 * m, 20), Qt.AlignCenter,
                         "energy (eV) -- grey: fit window, red: fitted edge")
        painter.end()
        if not image.save(path, "PNG"):
            raise OSError(f"could not write {path}")
        return path

    @operation("Energy")
    def fermi_edge_search(self, name: str, ranges=None,
                          temperature: float = 30.0, fit: bool = True,
                          half_window: float = 0.15) -> dict:
        """Find where the Fermi edge may be on a row's own energy axis, for
        choosing the window of ``fermi_edge``: the drops of the EDC (summed
        over ``ranges``, raw data) that stand clearly above the noise,
        highest energy first. The Fermi edge is the *last* drop, after which
        the intensity stays at the floor -- not the steepest one: a band
        edge, or the strong drop under a weak tail of pass-energy-20 data,
        can be steeper. With ``fit`` each candidate is fitted on its
        ``window`` and judged (E_F inside the window, a real step, a
        resolution, chi2). Returns the axis, the candidates and advice: when
        two fit well, the data cannot decide -- ask the person, once, and
        apply the answer to the rows of the same photon and pass energy."""
        from arpes_viewer.tools.spectra.fermi import edge_candidates
        workspace, (ident,) = self._workspace(name)
        energy, edc = self._edc(workspace, ident, ranges)
        candidates = edge_candidates(energy, edc, half_window=float(half_window))
        good = []
        for candidate in candidates:
            if not fit:
                continue
            try:
                result = workspace.fermi_edge(ident, candidate["window"],
                                              temperature, ranges, False)
                candidate["fit"] = {
                    "ef": round(result["values"]["ef"], 5),
                    "ef_error": round(result["errors"].get("ef", float("nan")), 5),
                    "resolution": round(result["values"]["resolution"], 4),
                    "reduced_chi2": round(result["reduced_chi2"], 3)}
                good.append(candidate)
            except ValueError as exc:
                candidate["fit"] = f"refused: {exc}"
        if not candidates:
            advice = ("no clear drop on this axis: the edge may lie beyond the "
                      "axis, or the data are normalised; look at a picture")
        elif fit and len([c for c in good if c["after"] < 0.15]) > 1:
            advice = ("more than one candidate fits and falls to a low level: "
                      "the highest one is the usual Fermi edge, but compare "
                      "with rows of the same photon and pass energy, and ask "
                      "the person before choosing")
        elif fit and good and good[0]["highest"] and good[0]["after"] < 0.15:
            advice = (f"the highest candidate is the Fermi edge (the intensity "
                      f"stays at the floor above it): E_F = "
                      f"{good[0]['fit']['ef']:.4f} eV (window "
                      f"{good[0]['window'][0]:.3f}..{good[0]['window'][1]:.3f}); "
                      f"the lower ones are band features")
        elif fit and good:
            advice = (f"one candidate fits: E_F = {good[0]['fit']['ef']:.4f} eV "
                      f"(window {good[0]['window'][0]:.3f}..{good[0]['window'][1]:.3f})")
        else:
            advice = "take the highest candidate's window first"
        return _plain({"axis": [float(energy.min()), float(energy.max()),
                                float(np.median(np.diff(energy)))],
                       "candidates": candidates, "advice": advice})

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

    @operation("Energy")
    @_keeps_selection
    def fs_correction(self, name: str, points=None, reference: str = "",
                      mode: str = "channels", order: int = 2,
                      new_name: str = "") -> dict:
        """Fermi-surface correction (tool panel, Basic). Either by hand:
        ``points``, [(angle, E), ...] on the Fermi edge in the row's own
        units (at least ``order`` + 1); a polynomial of ``order`` through
        them is flattened, every angle column shifted. Or from a
        ``reference``: another row whose Fermi edge has been fitted
        (``fermi_edge``, or the Fermi edge fit tool), its fit applied --
        ``mode="offset"``, the energy axis shifted by its E_F;
        ``mode="channels"``, every channel on its own E - E_F from its
        channel-by-channel fit (blank borders and unfitted channels cut
        off). A map (or kz map) is corrected whole, along its slit. Before
        the k conversion. Returns the new row (and, by hand, the polynomial,
        highest power first, and the number of points)."""
        if (points is None) == (not reference):
            raise ValueError("give either points=[(angle, E), ...] on the "
                             "Fermi edge or reference=<a fitted row's name>")
        key = self._key(name)
        ref_key = self._key(reference) if reference else None
        self.select(self._name(key))
        before = set(self.A.loaded_items)
        dialog = self.A.open_fs_correction()
        if dialog is None:
            raise ValueError(f"{self._name(key)!r} cannot be corrected: a cut, "
                             f"or a map or kz map in angle, is")
        out = {}
        try:
            if points is not None:
                dialog.manual_radio.setChecked(True)
                dialog.go_next()
                for x, y in points:
                    dialog.add_point(float(x), float(y))
                dialog.go_next()
                dialog.order_box.setValue(int(order))
                if new_name:
                    dialog.name_box.setText(str(new_name))
                coefficients = dialog.coefficients()
                if coefficients is None:
                    raise ValueError(f"an order-{int(order)} fit needs at least "
                                     f"{int(order) + 1} points")
                out = {"coefficients": np.asarray(coefficients).tolist(),
                       "points": len(dialog.points())}
            else:
                keys = [k for _label, k, _fits in dialog.references()]
                if ref_key not in keys:
                    raise ValueError(
                        f"{reference!r} cannot be the reference: only another "
                        f"row whose Fermi edge has been fitted can "
                        f"(fermi_edge, or the Fermi edge fit tool)")
                dialog.reference_radio.setChecked(True)
                dialog.go_next()
                dialog.reference_combo.setCurrentIndex(keys.index(ref_key))
                if mode not in ("offset", "channels"):
                    raise ValueError("mode is 'offset' or 'channels'")
                radio = (dialog.channels_radio if mode == "channels"
                         else dialog.offset_radio)
                if not radio.isEnabled():
                    raise ValueError(
                        f"{reference!r} has no "
                        f"{'channel-by-channel' if mode == 'channels' else 'whole-edge'}"
                        f" Fermi fit to apply")
                radio.setChecked(True)
                out = {"mode": mode}
            dialog.accept()
        finally:
            if dialog.isVisible():
                dialog.reject()
        added = [self._name(k) for k in self.A.loaded_items if k not in before]
        if not added:
            raise ValueError("the correction made no row")
        if reference and new_name:
            added[-1] = self.rename(added[-1], new_name)
        out["row"] = added[-1]
        return _plain(out)

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
        from arpes_viewer.tools.runtime.naming import tagged
        return self._list_scan(scan, new_name or
                               tagged(self._name(self._key(name)), step))

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
        raw data first.

        For a map (axes 0 = deflector/polar, 1 = slit, 2 = energy):
        ``axes=(1, 2)`` divides every cut of the map (one slit x energy
        plane per deflector angle) by its own total -- what evens out the
        intensity from cut to cut; ``axes=2`` divides every EDC by its total;
        ``axes=(0, 1)`` every constant-energy plane. ``map_to_k`` can do the
        E - E_F shift and this in the same call (``ef``, ``normalise_axes``)
        so no intermediate rows are listed."""
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
    def minimum_gradient(self, name: str, form: str = "ratio",
                         floor: float = 0.05, ratio: float = 1.0,
                         new_name: str = "") -> str:
        """The minimum-gradient picture of a cut, or of every
        constant-energy plane of a map: bands are where the intensity's
        gradient is smallest. ``form`` "ratio" is I/|grad I| (the usual
        one: slow intensity changes cancel, empty regions stay dark),
        "inverse" 1/|grad I|, "modulus" |grad I| itself (bands dark).
        ``floor`` caps the brightness of flat patches (a fraction of the
        gradient's RMS; lower it on smoothed data); ``ratio`` above 1
        weighs the second axis less. First derivatives only, so less
        noisy than ``derivative`` or ``curvature`` -- but smooth noisy
        data first (``smooth``). A picture to find bands on, not a
        quantity: take numbers from a fit. Returns the new row."""
        from arpes_viewer.tools.processing.process import minimum_gradient
        data = self.data(name)
        values = np.asarray(data.values, dtype=float)
        options = {"form": form, "floor": floor, "ratio": ratio}
        if values.ndim == 2:
            out = minimum_gradient(values, data.axes, **options)
        else:
            out = np.stack([minimum_gradient(values[..., i], data.axes[:2],
                                             **options)
                            for i in range(values.shape[-1])], axis=-1)
        return self._derive(name, out, data.axes, "gradient", options,
                            new_name)

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
    def _chain_name(self, name, ef, normalise_axes, step):
        """The name of a chain's last row: one bracketed tag per step it
        ran, in order (tools.runtime.naming)."""
        from arpes_viewer.tools.runtime.naming import tagged
        out = self._name(self._key(name))
        if ef is not None:
            out = tagged(out, "shift_energy")
        if normalise_axes is not None:
            out = tagged(out, "normalise")
        return tagged(out, step)

    def _prepared(self, name, ef=None, normalise_axes=None,
                  normalise_window=None):
        """The row in a workspace, shifted to E - E_F (``ef``) and divided by
        its own intensity (``normalise_axes``) there, so that a chain of
        steps lists only its last row; each step goes into the history.
        Returns ``(workspace, ident)``."""
        from arpes_viewer.tools.processing.dataops import self_normalize
        from arpes_viewer.tools.processing.process import Step, record_step
        workspace, (ident,) = self._workspace(name)
        source = self._name(self._key(name))
        if ef is not None:
            ident = workspace.shift_energy(ident, float(ef))["id"]
            record = workspace.get(ident)
            record["scan"].info = record_step(
                dict(record["scan"].info or {}),
                Step("E - E_F", {"ef": float(ef)}, source=source))
        if normalise_axes is not None:
            record = workspace.get(ident)
            scan = record["scan"]
            dims = ((normalise_axes,) if np.ndim(normalise_axes) == 0
                    else tuple(normalise_axes))
            axes = [np.asarray(getattr(scan, slot), dtype=float)
                    for slot in scan.axis_slots("array")]
            scan.value = self_normalize(np.asarray(scan.array(), dtype=float),
                                        axes, dims, window=normalise_window)
            scan.info = record_step(dict(scan.info or {}), Step(
                "normalise", {"dims": list(dims), "window": normalise_window},
                source=source))
        return workspace, ident

    @operation("Momentum")
    @_keeps_selection
    def cut_to_k(self, name: str, gamma_slit_deg: float = 0.0,
                 deflector_deg: float = 0.0, gamma_deflector_deg: float = None,
                 azimuth_deg: float = 0.0, n_k: int = None,
                 new_name: str = "", ef: float = None,
                 normalise_axes=None) -> str:
        """A cut in momentum (k conversion, cut): normal emission at slit
        angle ``gamma_slit_deg``; the deflector or polar angle the cut was
        taken at and where Γ is on it, if off normal. A cut already on
        E - E_F stays on it. ``ef`` (the fitted E_F on the row's own axis)
        and ``normalise_axes`` (as ``normalise``) do the E - E_F shift and
        the normalisation in the same call, so the list gets only the final
        row; the history records every step. Returns the new row."""
        workspace, ident = self._prepared(name, ef, normalise_axes)
        result = workspace.convert_cut(
            ident, gamma_slit_deg=gamma_slit_deg, deflector_deg=deflector_deg,
            gamma_deflector_deg=gamma_deflector_deg, azimuth_deg=azimuth_deg,
            n_k=n_k, name=new_name or None)
        record = workspace.get(result["id"])
        if not new_name:
            record["name"] = self._chain_name(name, ef, normalise_axes, "k")
        return self._list_scan(record["scan"], record["name"])

    @operation("Momentum")
    @_keeps_selection
    def map_to_k(self, name: str, gamma_deflector_deg: float = 0.0,
                 gamma_slit_deg: float = 0.0, azimuth_deg: float = 0.0,
                 n_kx: int = None, n_ky: int = None, new_name: str = "",
                 ef: float = None, normalise_axes=None) -> str:
        """An angle map in momentum, (kx, ky, E) (k conversion, map): Γ at
        deflector/polar ``gamma_deflector_deg`` and slit ``gamma_slit_deg``,
        turned by ``azimuth_deg``. Convert a map already on E - E_F, so the
        result is too -- or give ``ef`` (the fitted E_F on the row's own
        axis) and, if wanted, ``normalise_axes`` ((1, 2): every cut of the
        map by its own total), and the shift, the normalisation and the
        conversion are one call that lists only the k-map. The kx grid
        defaults to twice the scanned angles, at most 100 points (never
        fewer than the scan has): one point per scan step gives streaks;
        ky to the slit's points. Returns the new row (a k-map)."""
        workspace, ident = self._prepared(name, ef, normalise_axes)
        result = workspace.convert_map(
            ident, gamma_deflector_deg=gamma_deflector_deg,
            gamma_slit_deg=gamma_slit_deg, azimuth_deg=azimuth_deg,
            n_kx=n_kx, n_ky=n_ky, name=new_name or None)
        record = workspace.get(result["id"])
        if not new_name:
            record["name"] = self._chain_name(name, ef, normalise_axes, "k")
        return self._list_scan(record["scan"], record["name"])

    @operation("Processing")
    @_keeps_selection
    def cut_arithmetic(self, name_a: str, name_b: str,
                       operation: str = "asymmetry", normalise: str = "total",
                       intensity_floor: float = 0.05, region=None,
                       ranges=None, new_name: str = "") -> dict:
        """Combine two cuts as the Cut arithmetic window does -- dichroism
        (LH vs LV, CR vs CL), a difference, a ratio: ``operation``
        "asymmetry" (A − B)/(A + B), "difference", "ratio" or "sum";
        ``normalise`` "total" (B scaled to A's total over the common area),
        "region" (over ``region`` (x0, y0, x1, y1)) or "none";
        ``intensity_floor`` hides points where A + B is below that fraction
        of its maximum. Both cuts are first cropped to the range they share
        (and to ``ranges``, ((x_lo, x_hi), (E_lo, E_hi)), if given); B is
        resampled onto A's grid. Use the same kind of cuts (both in k, both
        on E - E_F). The result is signed: show it with a diverging colour
        map ("redwhiteblue", flipped for red = positive) and symmetric
        levels. Returns the new row, B's scale factor, the summary and any
        polarisation warning."""
        from arpes_viewer.tools.processing.cutops import (combine,
                                                          polarisation_warnings)
        a, b = self.data(name_a), self.data(name_b)
        if np.ndim(a.values) != 2 or np.ndim(b.values) != 2:
            raise ValueError("cut_arithmetic takes two cuts (2-D rows)")
        bounds = []
        for i in range(2):
            lo = max(float(np.nanmin(a.axes[i])), float(np.nanmin(b.axes[i])))
            hi = min(float(np.nanmax(a.axes[i])), float(np.nanmax(b.axes[i])))
            if ranges is not None and ranges[i] is not None:
                lo, hi = max(lo, min(ranges[i])), min(hi, max(ranges[i]))
            if hi <= lo:
                raise ValueError(f"A and B share nothing on axis {i} "
                                 f"({a.labels[i]})")
            bounds.append((lo, hi))

        def cropped(data):
            keep = [(np.asarray(ax) >= lo - 1e-9) & (np.asarray(ax) <= hi + 1e-9)
                    for ax, (lo, hi) in zip(data.axes, bounds)]
            return (np.asarray(data.values, dtype=float)[np.ix_(*keep)],
                    [np.asarray(ax)[k] for ax, k in zip(data.axes, keep)])
        va, axa = cropped(a)
        vb, axb = cropped(b)
        result = combine(va, axa, vb, axb, operation=operation,
                         normalise=normalise, region=region,
                         intensity_floor=float(intensity_floor),
                         a_labels=a.labels, b_labels=b.labels)
        preset = "circular_dichroism" if operation == "asymmetry" else "linear_dichroism"
        warnings = polarisation_warnings(a.info, b.info, preset)
        row = self._derive(name_a, result.values, axa, "cut arithmetic",
                           {"operation": operation, "with": b.name,
                            "normalise": normalise, "scale_b": result.scale,
                            "intensity_floor": intensity_floor,
                            "bounds": bounds},
                           new_name or f"{a.name} {operation} {b.name}")
        return _plain({"row": row, "scale_b": float(result.scale),
                       "summary": result.summary(), "warnings": warnings})

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
        return _plain(Workspace.read_cif(native(path)))

    @operation("Momentum")
    @_keeps_selection
    def fermi_pocket(self, name: str, centre, r_min: float, r_max: float,
                     energy: float = None, half_width: float = None,
                     ef: float = 0.0, rays: int = 72, harmonics: int = 6,
                     symmetry: int = 1, spin: int = 2, pockets: int = 1,
                     cell=None, energies=None, recentre: bool = True,
                     picture: str = "", to_list: bool = False) -> dict:
        """UNDER TEST, and ONLY FOR QUASI-TWO-DIMENSIONAL SAMPLES (surface
        states, layered materials with negligible k_z dispersion): for a
        three-dimensional Fermi surface the area of a contour in one map
        is not a carrier density -- ask the person which it is, and say so
        with the numbers.

        The contour of one Fermi pocket of a k-map (``name``) and its
        area: rays from ``centre`` (kx, ky; any point inside the pocket)
        find the band between ``r_min`` and ``r_max`` (a ring holding this
        band only), on the plane at ``energy`` +- ``half_width`` (default:
        E_F = ``ef``, the map's own energy step and a half). The contour
        is a Fourier series up to ``harmonics``, with an n-fold
        ``symmetry`` about the centre if given; ``recentre`` moves the
        centre to the contour's middle and traces again.

        Returns ``area`` (A^-2) and ``area_error`` (statistical only),
        ``k_f`` and its extremes, ``rays_kept`` of ``rays`` (many dropped:
        look at the ``picture`` and close the ring), and for a quasi-2D
        sample ``density`` (cm^-2, ``spin`` states per k, ``pockets``
        equivalent pockets in the zone), ``frequency`` (T, of quantum
        oscillations), and with ``cell`` = (a, b, gamma_deg) of the plane
        ``zone_fraction`` and ``per_cell`` (carriers per cell). With
        ``energies`` (a list, the first where the pocket is clearest)
        also ``mass`` (cyclotron mass in m_e, positive for an electron
        pocket, negative for a hole pocket), ``area_at_ef`` and
        ``series`` (the area at each energy). ``picture`` writes a PNG of
        the window (plane, rays, contour) to check it; ``to_list`` adds
        the contour (and the area series) as curve rows."""
        from arpes_viewer.ui.panels.pocket import PocketDialog
        key = self._key(name)
        data = self.A.load_dataset(key)
        dialog = None
        try:
            if data.kind != "k_map":
                raise ValueError(f"{self._name(key)} is a {data.kind}: a Fermi "
                                 "pocket is traced on a k-map (map_to_k first)")
            dialog = PocketDialog((self._name(key), data), None,
                                  existing_names=self.A.listed_names)
            dialog._timer.blockSignals(True)       # traced when asked, below
            dialog.ef.setValue(float(ef))
            dialog.energy.setValue(float(ef if energy is None else energy))
            if half_width is not None:
                dialog.half_width.setValue(float(half_width))
            dialog.r_min.setValue(float(r_min))
            dialog.r_max.setValue(float(r_max))
            dialog.rays.setValue(int(rays))
            dialog.order.setValue(int(harmonics))
            dialog.fold.setValue(int(symmetry))
            dialog.spin_choice.setCurrentIndex(0 if int(spin) == 2 else 1)
            dialog.pockets.setValue(int(pockets))
            if cell:
                a, b, gamma = (list(cell) + [0.0, 90.0])[:3] if len(cell) < 3 \
                    else cell[:3]
                dialog.cell_a.setValue(float(a))
                dialog.cell_b.setValue(float(b or 0.0))
                dialog.cell_gamma.setValue(float(gamma or 90.0))
            else:
                dialog.cell_a.setValue(0.0)
            dialog.set_centre(float(centre[0]), float(centre[1]))
            if recentre and dialog.fitted is not None:
                dialog.recentre()
            if dialog.fitted is None:
                raise ValueError("no contour was found: "
                                 + _strip_tags(dialog.result_label.text()))
            series = None
            if energies is not None:
                series = dialog.run_series(np.asarray(energies, dtype=float),
                                           background=False)
            out = dict(dialog.numbers())
            if series is not None:
                out["series"] = {"energies": series.energies.tolist(),
                                 "areas": series.areas.tolist(),
                                 "area_errors": series.area_errors.tolist(),
                                 "carrier": series.carrier()}
                if series.carrier():
                    out["carrier"] = series.carrier()
            if picture:
                dialog.resize(1320, 900)
                dialog.grab().save(native(picture))
                out["picture"] = native(picture)
            if to_list:
                made = dialog.export()
                self.A._list_computed(made)
                out["rows"] = [d.source_label for d in made]
            return _plain(out)
        finally:
            if dialog is not None:
                dialog.close()
                dialog.deleteLater()
            data.close()

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
                     labels=True, left_labels: str = "",
                     view="oblique", size=(1600, 1600), panel_mm: float = 0.0,
                     text_pt: float = 8.0) -> dict:
        """A picture of the 3-D Brillouin zone (the 3D BZ window), for a
        schematic panel: ``planes`` as (h, k, l, height) with height in units
        of the reciprocal vector (0 through Γ, 0.5 the zone top); ``paths``
        like "G-M-K-G"; axes in the crystal frame (k_a, k_b, k_c) or, with
        ``frame="sample"``, the data's (k_x, k_y, k_z: k_z along
        ``surface_hkl``, k_x turned by ``azimuth_deg``); ``view`` "oblique",
        an axis name or a vector; ``labels`` True (every high-symmetry
        point), False (none) or the ones to show ("G, L" or ["Γ", "L"]);
        labels sized for a ``panel_mm`` wide panel at ``text_pt`` if given.
        Never overwrites ``path``."""
        path = native(path)
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
            if isinstance(labels, (str, list, tuple)):
                chosen = labels if isinstance(labels, str) else ", ".join(labels)
                dialog.labels_box.setChecked(bool(chosen.strip()))
                dialog.only_edit.setText(chosen)
            else:
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
                     title: str = "", high_factor: float = 1.0,
                     zone_color: str = None, zone_width: float = 0.6) -> dict:
        """A page of slices through a map (Slice series figure): one panel
        per value along ``axis`` (2 = energy), each the planes within
        ``half_width``, titled with the value asked for; colour map, levels
        (each panel's ``percentiles``, the span stretched by ``high_factor``
        so the strongest intensity is not saturated; ``shared=False`` keeps
        each panel's own), gamma at creation; the row's Brillouin zone on
        constant-energy panels, in ``zone_style`` ("solid", "dashed"),
        ``zone_color`` ("#RRGGBB", or "#AARRGGBB" for a see-through line,
        e.g. "#B8D62020") and ``zone_width`` (pt). Several maps side by
        side: ``slice_grid``. Returns the figure in numbers (its title names
        it for the other figure operations)."""
        self.select(name)
        window = self.A.open_slice_series(
            values=list(values), axis=int(axis), half_width=float(half_width),
            cols=int(cols), nominal_titles=nominal_titles, shared=shared,
            colormap=colormap, flip=flip, percentiles=tuple(percentiles),
            gamma=float(gamma), zone=bool(zone), zone_style=zone_style,
            high_factor=float(high_factor), zone_color=zone_color,
            zone_width=float(zone_width))
        return self._figure_made(window, title)

    @operation("Figures")
    def slice_grid(self, names, values, *, axis: int = 2,
                   half_width: float = 0.0, column_titles=None,
                   colormap: str = "gray", flip: bool = False,
                   percentiles=(0.0, 100.0), high_factor: float = 1.0,
                   gamma: float = 1.0, shared: bool = False, zone: bool = True,
                   zone_style: str = "solid", zone_color: str = None,
                   zone_width: float = 0.6, width_mm: float = 0.0,
                   title: str = "Slice grid") -> dict:
        """One figure of the same slices through several maps: a column per
        map (``names``; ``column_titles`` to name them, e.g. "LH", "LV"), a
        row per value along ``axis`` (2 = energy) -- a polarisation or
        temperature series. Each panel is titled "<column>, <value> <unit>";
        colour, levels, gamma and the Brillouin zone as in
        ``slice_series``. Returns the figure in numbers."""
        from arpes_viewer.ui.panels.figure import FigureWindow, slice_panels
        from arpes_viewer.ui.viewers.windows import keep_alive
        if isinstance(names, str):
            names = [names]
        heads = list(column_titles or [self._name(self._key(n)) for n in names])
        if len(heads) != len(names):
            raise ValueError("give one column title per map")
        columns = []
        for name in names:
            key = self._key(name)
            contour = self.A.map_contour(key)
            if contour is None:
                raise ValueError(f"{name!r} could not be opened")
            made_for_it = not contour.isVisible()
            try:
                slice_axes, labels = contour.slice_axes()
                panels = slice_panels(
                    contour.full_cube(), slice_axes, labels, axis=int(axis),
                    values=list(values), half_width=float(half_width),
                    colormap=colormap, flip=bool(flip),
                    percentiles=tuple(percentiles), gamma=float(gamma),
                    zone=contour.saved_zone() if zone else None,
                    zone_style=zone_style, high_factor=float(high_factor),
                    zone_color=zone_color, zone_width=float(zone_width))
            finally:
                if made_for_it and not contour.cut_windows:
                    contour.close()
            columns.append(panels)
        grid = []
        for row in range(len(values)):
            for head, panels in zip(heads, columns):
                panel = panels[row]
                panel.title = f"{head}, {panel.title}" if panel.title else head
                grid.append(panel)
        window = FigureWindow(grid, title, parent=None, dataset_source=None)
        window.figure.fit_grid(len(names))
        window.figure.letter_panels()
        window.figure.style.shared_levels = bool(shared)
        window.figure.style.equal_aspect = int(axis) == 2
        if width_mm:
            window.figure.style.width_mm = float(width_mm)
        window.refresh()
        window.show()
        keep_alive(window)
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
        window.load_picture(panel, native(path))
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
        path = native(path)
        if os.path.exists(path):
            raise FileExistsError(f"{path} exists; give a new name")
        out = self._figure(title).render(path, dpi=int(dpi) or None)
        out["png"] = native(out.get("png"))
        return out

    @operation("Figures")
    def figure_export(self, title: str = "", path: str = "") -> list:
        """Write the figure as PDF, SVG, PNG or TIFF (from the extension).
        Never overwrites. Returns the files written."""
        path = native(path)
        if os.path.exists(path):
            raise FileExistsError(f"{path} exists; give a new name")
        fmt = os.path.splitext(path)[1].lstrip(".").lower()
        fmt = {"tiff": "tif"}.get(fmt, fmt)
        return [native(p) for p in self._figure(title).write(path, fmt)]

    @operation("Figures")
    def figure_save(self, title: str = "", path: str = "",
                    with_data: bool = True) -> str:
        """Save the figure as an .afig file to open and edit again, with
        (``with_data``) the data of each panel in "data for <name>" beside
        it -- leave that out of anything shared. Never overwrites. The window
        keeps its title, so the other figure operations still find it by
        the same name."""
        path = native(path)
        if os.path.exists(path):
            raise FileExistsError(f"{path} exists; give a new name")
        window = self._figure(title)
        kept = window.windowTitle()
        try:
            return window.save_file(path, with_data=bool(with_data))
        finally:
            window.setWindowTitle(kept)

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
