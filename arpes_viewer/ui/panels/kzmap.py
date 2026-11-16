"""
ui/panels/kzmap.py
==================
The kz map processing window: pick one box, calibrate the whole scan.

A photon-energy scan arrives from the loader stacked as measured, on the
first spectrum's energy axis, because nothing in the files says where the
Fermi level of each spectrum actually is (see ``loader/beamlines/cassiopee.py``). This
is where that gets fixed, using the only reliable reference there is -- the
edge in each spectrum.

The shape of it
---------------
The slit cut -- angle against energy, summed over photon energy -- opens
alongside, and the box dragged on it says two things at once: which angle
channels to sum into an EDC, and over what energy range to fit. That box is
then used *by index* in every spectrum of the scan. Deliberately: an index
range is the same detector channels and the same analyser window everywhere,
while an energy range would mean something different in each spectrum, since
these are precisely the spectra whose energy scales do not yet agree. Using
energies here would make the fit depend on the misalignment it is meant to
measure.

Three ways to the Fermi levels
------------------------------
1. **Fit the edge in a box** (the default, as above): every spectrum's edge
   fitted.
2. **By hand on the Scan-axis cut**: *Pick E_F on the Scan-axis cut* opens
   the cut of photon energy against energy, where clicks put points on the
   Fermi edge at a few photon energies; a polynomial through them gives
   E_F(hv). One function over the whole scan by default; *Segments* splits
   it into several, each fitted to its own points (at a grating change,
   say), the breaks placed automatically or typed.
3. **From a reference kz map**: the E_F(hv) of another kz map aligned
   before (by any of the three), as the Fermi surface correction takes a
   fitted reference. Spectra outside the reference's photon energies are
   cut off.

Whichever was used, the levels are kept with the result and with the row
aligned (``tools.momentum.kzmap.KZ_FIT_KEY``), so either can serve as a
later scan's reference.

Everything the fitting, shifting and cropping actually does lives in
:mod:`tools.momentum.kzmap`, which imports no Qt and can be run from a script. This
file is the window around it.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QFormLayout, QGroupBox,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPushButton, QRadioButton, QSizePolicy, QSpinBox,
                             QStackedWidget, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from arpes_viewer.ui.common.screen import fits_screen
from arpes_viewer.tools.momentum import kzmap
from arpes_viewer.tools.processing.process import Step, record_step
from arpes_viewer.ui.common import jobs as nxs_jobs
from arpes_viewer.ui.viewers.widgets import add_button, ButtonRow, MemoryData

__all__ = ["KzMapProcessDialog"]


@fits_screen
class KzMapProcessDialog(QDialog):
    """Fit the Fermi edge of every spectrum of a kz map and align them.

    Modeless: the box is dragged on another window, so this one must not
    block it.
    """

    datasetsCreated = pyqtSignal(list)

    def __init__(self, contour):
        super().__init__(contour)
        self.setWindowTitle("kz map processing")
        self.setModal(False)
        self.resize(600, 760)
        self.scan_window = None
        self._scan_opened_here = False
        self.contour = contour
        self.result = None

        self.hv, self.angles, self.energy, _cube = contour.data.angle_cube
        self.hv = np.asarray(self.hv, dtype=float)
        self.angles = np.asarray(self.angles, dtype=float)
        self.energy = np.asarray(self.energy, dtype=float)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Drag a box on the slit cut that has just opened. It needs to "
            "cover a Fermi edge, with points clearly above and clearly below "
            "it: the angle range says which channels are summed into the EDC, "
            "and the energy range is what the fit runs over.\n\n"
            "That same box is then used, by detector index, on every "
            "spectrum of the scan.")
        intro.setWordWrap(True)
        self.intro = intro

        # -- how the Fermi levels are found ---------------------------------
        method_box = QGroupBox("How the Fermi level of each spectrum is found")
        method_layout = QVBoxLayout(method_box)
        self.box_radio = QRadioButton(
            "Fit the edge in a box on the slit cut (every spectrum fitted)")
        self.manual_radio = QRadioButton(
            "By hand: click E_F on the Scan-axis cut, a function through the points")
        self.reference_radio = QRadioButton(
            "From a reference: a kz map aligned before")
        self.box_radio.setChecked(True)
        for radio in (self.box_radio, self.manual_radio, self.reference_radio):
            method_layout.addWidget(radio)
            radio.toggled.connect(self._method_changed)
        if not self.references():
            self.reference_radio.setEnabled(False)
            self.reference_radio.setToolTip(
                "No other kz map of the main list has been aligned yet: align "
                "the reference first (any of the other two ways).")
        layout.addWidget(method_box)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)
        box_page = QWidget()
        box_layout = QVBoxLayout(box_page)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.addWidget(intro)

        # -- what is currently picked ---------------------------------------
        picked = QGroupBox("The box")
        picked_layout = QVBoxLayout(picked)
        self.region_label = QLabel("Nothing picked yet.")
        self.region_label.setWordWrap(True)
        picked_layout.addWidget(self.region_label)
        row = QHBoxLayout()
        self.edge_button = QPushButton("Back to the edge")
        self.edge_button.setToolTip(
            "Every angle channel, and the energy range around where the edge "
            "appears to be in the scan as a whole. This is where the box "
            "starts.")
        self.edge_button.clicked.connect(self.select_edge)
        self.whole_button = QPushButton("Use the whole cut")
        self.whole_button.setToolTip(
            "Every angle channel and the full energy range. Slower, and on a "
            "wide window the far tails pull the fit a little; useful when the "
            "edge is not where the automatic guess put it.")
        self.whole_button.clicked.connect(self.select_everything)
        row.addWidget(self.edge_button)
        row.addWidget(self.whole_button)
        row.addStretch(1)
        picked_layout.addLayout(row)
        box_layout.addWidget(picked)

        # -- the fit --------------------------------------------------------
        options = QGroupBox("Fitting")
        form = QFormLayout(options)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.1, 1000.0)
        self.temperature.setDecimals(1)
        self.temperature.setSuffix(" K")
        self.temperature.setValue(_temperature_of(contour.data))
        self.temperature.setToolTip(
            "Held during the fit. On a single edge the temperature and the "
            "resolution are not separable -- the width is "
            "sqrt((3.53kT)^2 + FWHM^2) -- so fitting both gives two numbers "
            "that mean nothing apart.")
        form.addRow("Temperature", self.temperature)

        self.hold_temperature = QCheckBox("Hold the temperature")
        self.hold_temperature.setChecked(True)
        form.addRow("", self.hold_temperature)
        box_layout.addWidget(options)
        self.pages.addWidget(box_page)
        self.pages.addWidget(self._manual_page())
        self.pages.addWidget(self._reference_page())

        shared = QGroupBox("The result")
        shared_form = QFormLayout(shared)
        self.normalise = QCheckBox(
            "Normalise each spectrum by its total intensity")
        self.normalise.setChecked(True)
        self.normalise.setToolTip(
            "The photon flux and the analyser transmission both vary by a "
            "large factor across a wide photon-energy scan, so raw counts in "
            "a kz map are largely a picture of the beamline. Dividing each "
            "spectrum by its own total leaves the shape of each, which is "
            "what a kz map is read for.\n\n"
            "Done after aligning and cropping, so every total is a sum over "
            "the same energy range.")
        shared_form.addRow("", self.normalise)
        layout.addWidget(shared)

        # -- the answer -----------------------------------------------------
        found = QGroupBox("Fermi level against photon energy")
        found_layout = QVBoxLayout(found)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", contour.data.scan.labels.get("x", "hv (eV)"))
        self.plot.setLabel("left", "E_F (eV)")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setMinimumHeight(170)
        found_layout.addWidget(self.plot)
        self.curve = self.plot.plot([], [], pen=pg.mkPen("#1f77b4", width=2),
                                    symbol="o", symbolSize=5,
                                    symbolBrush="#1f77b4")
        self.failed_curve = self.plot.plot(
            [], [], pen=None, symbol="x", symbolSize=9,
            symbolPen=pg.mkPen("#d62728", width=2))
        self.note = QLabel(
            "A smooth curve here means the fits are sound. Scatter means "
            "some of them found something other than the edge.")
        self.note.setWordWrap(True)
        found_layout.addWidget(self.note)
        layout.addWidget(found, stretch=1)

        buttons = ButtonRow()
        self.fit_button = add_button(buttons,"Fit and assemble",
                                            QDialogButtonBox.AcceptRole)
        self.fit_button.clicked.connect(self.run)
        add_button(buttons,"Close", QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._open_the_cut()
        self.finished.connect(lambda *_: self._release())
        self._method_changed()

    # -- the slit cut and its box ------------------------------------------
    def _open_the_cut(self):
        """Open (or raise) the slit cut and turn its selection box on."""
        self.contour.open_cut("slit")
        self.cut_window = self.contour.cut_windows.get("slit")
        if self.cut_window is None:
            self.region_label.setText(
                "The slit cut could not be opened, so there is nothing to "
                "pick a box on.")
            self.fit_button.setEnabled(False)
            return
        view = self.cut_window.view
        view.set_selection_visible(True)
        view.selectionChanged.connect(self._box_moved)
        self.select_edge()

    #: How much energy either side of the apparent edge the starting box
    #: covers. Wide enough to hold the edge and a stretch of the flat regions
    #: on both sides, which is what the fit needs, and no wider: on the real
    #: 41-spectrum scan this takes the fitting from 37 s to under 4, and the
    #: answer is slightly *better*, because a window stretching far past the
    #: edge lets the tails pull the background terms around.
    EDGE_HALF_WIDTH_EV = 0.35

    def select_edge(self):
        """Put the box around wherever the edge looks to be.

        Guessed from the whole scan summed into one EDC -- every spectrum has
        the same edge to within the misalignment being measured, so the sum
        locates it well enough to start from even though it is exactly what
        blurs it.
        """
        window = getattr(self, "cut_window", None)
        if window is None:
            return
        lo, hi = float(self.energy.min()), float(self.energy.max())
        try:
            from arpes_viewer.tools.spectra.fermi import initial_guess
            edc = np.nansum(np.asarray(self.contour.full_cube(), dtype=float),
                            axis=(0, 1))
            centre = float(initial_guess(self.energy, edc,
                                         self.temperature.value())["ef"])
        except Exception:                                   # noqa: BLE001
            centre = 0.5 * (lo + hi)        # no guess: the middle will do
        half = self.EDGE_HALF_WIDTH_EV
        low = max(lo, centre - half)
        high = min(hi, centre + half)
        if high - low < 8 * abs(self.energy[1] - self.energy[0]):
            low, high = lo, hi              # too narrow to fit in: take it all
        window.view.set_selection_corners(
            float(self.angles.min()), low, float(self.angles.max()), high)
        self._box_moved()

    def _release(self):
        scan = getattr(self, "scan_window", None)
        if scan is not None:
            try:
                scan.view.stop_point_picking()
                scan.view.clear_overlays()
                if self._scan_opened_here:
                    scan.close()
            except RuntimeError:
                pass
        window = getattr(self, "cut_window", None)
        if window is None:
            return
        try:
            window.view.selectionChanged.disconnect(self._box_moved)
        except TypeError:
            pass          # already gone, which is the normal case on close

    def select_everything(self):
        window = getattr(self, "cut_window", None)
        if window is None:
            return
        window.view.set_selection_corners(
            float(self.angles.min()), float(self.energy.min()),
            float(self.angles.max()), float(self.energy.max()))
        self._box_moved()

    def _box_moved(self, *_):
        region = self.index_region()
        if region is None:
            self.region_label.setText("Nothing picked yet.")
            self.fit_button.setEnabled(False)
            return
        (a0, a1), (e0, e1) = region
        self.region_label.setText(
            f"Angle channels {a0}-{a1}  "
            f"({self.angles[a0]:.3f} to {self.angles[a1]:.3f}), "
            f"{a1 - a0 + 1} summed into the EDC.\n"
            f"Fitting over energy {min(self.energy[e0], self.energy[e1]):.4f} "
            f"to {max(self.energy[e0], self.energy[e1]):.4f} eV "
            f"({abs(e1 - e0) + 1} points).")
        # A fit needs points on both sides of the edge; eight is what
        # tools.spectra.fermi itself insists on.
        if self.method() == "box":
            self.fit_button.setEnabled(abs(e1 - e0) + 1 >= 8)

    def index_region(self):
        """The box as inclusive index bounds, or None."""
        window = getattr(self, "cut_window", None)
        if window is None:
            return None
        return window.view.selection_index_ranges()

    # -- doing it ----------------------------------------------------------
    def run(self):
        """Align by the method chosen: the box's edge fits (as before),
        the points clicked, or the reference."""
        if self.method() == "manual":
            return self.run_manual()
        if self.method() == "reference":
            return self.run_reference()
        region = self.index_region()
        if region is None:
            return None
        cube = np.asarray(self.contour.full_cube(), dtype=float)
        energy = self.energy
        temperature = float(self.temperature.value())
        fixed = ("temperature",) if self.hold_temperature.isChecked() else ()
        normalise = self.normalise.isChecked()
        name = self.contour.filename

        def work(report):
            def tick(done, total):
                report(done / max(1, total),
                       f"Fitting the Fermi edge, spectrum {done + 1} of {total}")
            return kzmap.process_kz_map(
                cube, energy, region, temperature=temperature, fixed=fixed,
                normalise=normalise, progress=tick)

        self._running_method = "box"
        started = nxs_jobs.run_job(
            self, "kz map processing", work,
            on_done=self._finish,
            on_error=lambda exc: self._failed(exc),
            on_cancel=lambda: self.note.setText("Cancelled."))
        if not started:
            # Another job is already running; run_job says so itself.
            return None
        return True

    def _failed(self, exc):
        self.note.setText(f"<span style='color:#c00'>{exc}</span>")

    def _finish(self, result):
        self._used_method = getattr(self, "_running_method", "box")
        self.result = result
        self._draw(result)
        dataset = self._dataset(result)
        self.datasetsCreated.emit([dataset])
        self.note.setText(
            result.summary().replace("\n", "<br>")
            + f"<br><b>Added to the list as &ldquo;{dataset.source_label}"
              f"&rdquo;.</b>")

    def _draw(self, result):
        hv = self.hv[self._kept(result)]
        ok = result.ok
        self.curve.setData(hv[ok], result.ef[ok])
        self.failed_curve.setData(hv[~ok], result.ef[~ok])

    def _kept(self, result):
        kept = getattr(result, "kept", None)
        return np.ones(self.hv.size, bool) if kept is None else np.asarray(kept, bool)

    def _dataset(self, result):
        """The aligned cube as a dataset the main list can take."""
        data = self.contour.data
        scan = data.scan
        labels = dict(scan.labels or {})
        labels["z"] = "E - E_F (eV)"
        method = getattr(self, "_used_method", "box")
        kept = self._kept(result)
        hv = self.hv[kept]

        parameters = {"method": {"box": "edge fit in a box",
                                 "manual": "by hand on the Scan-axis cut",
                                 "reference": "from a reference kz map"}[method]}
        if method == "box":
            region = self.index_region()
            parameters.update({
                "angle_index_from": int(region[0][0]),
                "angle_index_to": int(region[0][1]),
                "energy_index_from": int(region[1][0]),
                "energy_index_to": int(region[1][1]),
                "temperature_K": float(self.temperature.value()),
                "temperature_held": bool(self.hold_temperature.isChecked()),
                "spectra_fitted": int(result.ok.sum()),
                "spectra_interpolated": int((~result.ok).sum()),
            })
        elif method == "manual":
            parameters.update({
                "points": [list(map(float, p)) for p in self.points()],
                "order": int(self.order_box.value()),
                "segments": [[lo, hi, c] for lo, hi, c in self._pieces],
            })
        else:
            choice = self.reference_choice() or {}
            parameters.update({
                "reference": choice.get("label", ""),
                "spectra_cut_off": int((~kept).sum()),
            })
        parameters.update({
            "normalised_by_total": bool(result.normalised),
            "fermi_level_spread_eV": float(result.spread),
            "energy_trimmed_eV": float(result.trimmed),
        })
        info = record_step(dict(scan.info),
                           Step("kz_align", parameters, source=self.contour.filename))
        record = kzmap.fit_record(hv, result.ef, result.ok,
                                  method=parameters["method"],
                                  source=self.contour.filename)
        info[kzmap.KZ_FIT_KEY] = record
        # The row aligned can now be another scan's reference too.
        keep = getattr(self.contour, "_set_row_properties", None)
        if callable(keep):
            keep({kzmap.KZ_FIT_KEY: record})
        # The per-spectrum Fermi levels are the calibration this produced.
        # They are what makes the result checkable later, and what a second
        # scan of the same sample would be compared against.
        info["kz.fermi_level_eV"] = np.asarray(result.ef, dtype=float)
        info["kz.fermi_level_fitted"] = np.asarray(result.ok, dtype=bool)

        name = _unique(f"{self.contour.filename} [E-E_F]",
                       self.contour.existing_names())
        return MemoryData(
            data.kind, (hv, self.angles, result.energy), result.cube,
            labels, source_label=name, parameters=parameters,
            prefix="kz_align", source_path=getattr(data, "path", ""),
            source_info=info, source_motors=dict(scan.fourd_info))


    # -- which method ------------------------------------------------------
    def method(self) -> str:
        if self.manual_radio.isChecked():
            return "manual"
        if self.reference_radio.isChecked():
            return "reference"
        return "box"

    def _method_changed(self, *_):
        if not hasattr(self, "pages"):
            return
        method = self.method()
        index = {"box": 0, "manual": 1, "reference": 2}[method]
        self.pages.setCurrentIndex(index)
        # Only the page shown takes room: a stack is otherwise as tall as
        # its tallest page, which pushed the plot below the window.
        for i in range(self.pages.count()):
            page = self.pages.widget(i)
            policy = QSizePolicy.Preferred if i == index else QSizePolicy.Ignored
            page.setSizePolicy(policy, policy)
        self.pages.adjustSize()
        self.fit_button.setText({"box": "Fit and assemble",
                                 "manual": "Align on the function",
                                 "reference": "Align on the reference"}[method])
        scan = self.scan_window
        if scan is not None and method != "manual":
            try:
                scan.view.stop_point_picking()
                scan.view.clear_overlays()
            except RuntimeError:
                self.scan_window = None
        if method == "manual":
            if scan is not None:
                self._start_picking()
            self._refresh_manual()
        elif method == "reference":
            self._show_reference()
        else:
            self._box_moved()

    # -- by hand on the Scan-axis cut --------------------------------------
    def _manual_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(
            "Press the button to open the Scan-axis cut (photon energy "
            "against energy), then click where you see the Fermi edge, at "
            "several photon energies spread over the scan, ends included. "
            "A polynomial through the points gives E_F at every photon "
            "energy: one function over the whole scan, or one per segment.")
        hint.setWordWrap(True)
        box.addWidget(hint)
        self.pick_button = QPushButton("Pick E_F on the Scan-axis cut")
        self.pick_button.setToolTip(
            "Opens (or raises) the Scan-axis cut; each left click there adds "
            "a point (photon energy, E_F) to the table.")
        self.pick_button.clicked.connect(self.open_scan_cut)
        box.addWidget(self.pick_button)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Photon energy (eV)", "E_F (eV)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(150)
        self.table.itemChanged.connect(lambda *_: self._refresh_manual())
        box.addWidget(self.table)
        row = QHBoxLayout()
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self.remove_selected)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_points)
        row.addWidget(remove)
        row.addWidget(clear)
        row.addStretch(1)
        box.addLayout(row)

        form = QFormLayout()
        self.order_box = QSpinBox()
        self.order_box.setRange(0, 4)
        self.order_box.setValue(1)
        self.order_box.setToolTip(
            "Polynomial order of each function: 0 a constant, 1 a straight "
            "line (the usual drift of a monochromator's calibration), 2 a "
            "parabola. Each function needs order + 1 points.")
        self.order_box.valueChanged.connect(lambda *_: self._refresh_manual())
        form.addRow("Order", self.order_box)
        self.segments_box = QSpinBox()
        self.segments_box.setRange(1, 8)
        self.segments_box.setValue(1)
        self.segments_box.setToolTip(
            "1: one function over the whole scan (the default). More: the "
            "scan split into segments, each with a function of its own "
            "fitted to its own points -- where the calibration jumps, at a "
            "grating or undulator-harmonic change.")
        self.segments_box.valueChanged.connect(self._segments_changed)
        form.addRow("Segments", self.segments_box)
        self.breaks_edit = QLineEdit()
        self.breaks_edit.setPlaceholderText("automatic: equal numbers of points")
        self.breaks_edit.setToolTip(
            "Photon energies (eV) where one segment ends and the next begins, "
            "separated by commas. Empty: placed so each segment has about the "
            "same number of points.")
        self.breaks_edit.setEnabled(False)
        self.breaks_edit.editingFinished.connect(self._refresh_manual)
        form.addRow("Breaks (eV)", self.breaks_edit)
        box.addLayout(form)
        self.manual_note = QLabel("")
        self.manual_note.setWordWrap(True)
        box.addWidget(self.manual_note)
        self._pieces = []
        return page

    def open_scan_cut(self):
        """Open (or raise) the Scan-axis cut and pick E_F on it."""
        window = self.contour.cut_windows.get("deflector")
        if window is None:
            window = self.contour.open_cut("deflector")
            self._scan_opened_here = True
        self.scan_window = window
        if window is None:
            return None
        self._start_picking()
        window.raise_()
        window.activateWindow()
        self._refresh_manual()
        return window

    def _start_picking(self):
        try:
            self.scan_window.view.start_point_picking(self._on_pick)
        except RuntimeError:
            self.scan_window = None

    def _on_pick(self, x: float, y: float):
        if self.method() == "manual":
            self.add_point(x, y)

    def add_point(self, hv: float, ef: float):
        row = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(row)
        for column, value in enumerate((hv, ef)):
            self.table.setItem(row, column, QTableWidgetItem(f"{value:.6g}"))
        self.table.blockSignals(False)
        self._refresh_manual()

    def points(self):
        out = []
        for row in range(self.table.rowCount()):
            try:
                out.append((float(self.table.item(row, 0).text()),
                            float(self.table.item(row, 1).text())))
            except (AttributeError, ValueError):
                continue
        return out

    def remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        self.table.blockSignals(True)
        for row in rows:
            self.table.removeRow(row)
        self.table.blockSignals(False)
        self._refresh_manual()

    def clear_points(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)
        self._refresh_manual()

    def _segments_changed(self, *_):
        self.breaks_edit.setEnabled(self.segments_box.value() > 1)
        if self.segments_box.value() <= 1:
            self.breaks_edit.clear()
        self._refresh_manual()

    def breaks(self):
        """The photon energies between segments: typed, or placed so each
        segment has about as many points as the others."""
        if self.segments_box.value() <= 1:
            return []
        typed = self.breaks_edit.text().replace(";", ",").strip()
        if typed:
            values = []
            for part in typed.split(","):
                part = part.strip()
                if part:
                    values.append(float(part))
            return sorted(values)
        return kzmap.segment_breaks([p[0] for p in self.points()],
                                    self.segments_box.value())

    def manual_levels(self):
        """``(ef, pieces)`` from the points, or raises ValueError."""
        try:
            breaks = self.breaks()
        except ValueError:
            raise ValueError("the breaks are photon energies separated by commas")
        return kzmap.levels_from_points(self.points(), self.hv,
                                        order=self.order_box.value(),
                                        breaks=breaks)

    def _refresh_manual(self, *_):
        if not hasattr(self, "manual_note") or self.method() != "manual":
            return
        points = self.points()
        view = self.scan_window.view if self.scan_window is not None else None
        try:
            if view is not None:
                view.show_picked_points([p[0] for p in points], [p[1] for p in points])
        except RuntimeError:
            self.scan_window, view = None, None
        try:
            ef, pieces = self.manual_levels()
        except ValueError as exc:
            self._pieces = []
            if view is not None:
                view.show_overlay_path(None, None)
            self.curve.setData([], [])
            self.manual_note.setText(f"{len(points)} point(s): {exc}.")
            self.fit_button.setEnabled(False)
            return
        self._pieces = pieces
        order = np.argsort(self.hv)
        if view is not None:
            view.show_overlay_path(self.hv[order], ef[order], dashed=True)
        self.curve.setData(self.hv[order], ef[order])
        self.failed_curve.setData([], [])
        segments = len(pieces)
        self.manual_note.setText(
            f"{len(points)} points, {segments} function"
            f"{'s' if segments > 1 else ''} of order {self.order_box.value()}; "
            f"E_F from {np.nanmin(ef):.4f} to {np.nanmax(ef):.4f} eV over the "
            f"scan. The curve is drawn dashed on the Scan-axis cut.")
        self.fit_button.setEnabled(True)

    def run_manual(self):
        try:
            ef, _pieces = self.manual_levels()
            result = kzmap.align_to_levels(
                np.asarray(self.contour.full_cube(), dtype=float), self.energy,
                ef, normalise=self.normalise.isChecked())
        except ValueError as exc:
            self._failed(exc)
            return None
        self._running_method = "manual"
        self._finish(result)
        return True

    # -- from a reference --------------------------------------------------
    def references(self):
        """``(label, key, fit)`` of the kz maps of the main list whose Fermi
        levels are recorded -- this map's own row left out."""
        if getattr(self, "_references", None) is None:
            source = getattr(self.contour, "_kz_references", None)
            listed = source() if callable(source) else []
            own = getattr(self.contour, "_row_key", None)
            self._references = [(label, key, fit) for label, key, fit in listed
                                if own is None or key != own]
        return self._references

    def _reference_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(
            "Choose the reference: a kz map of the main list aligned before "
            "(any way). Its Fermi level against photon energy is read from "
            "it, interpolated onto this scan's photon energies and applied; "
            "spectra outside its photon-energy range are cut off. Both scans "
            "must have their energy axes on the same scale (as loaded), and "
            "the same monochromator and analyser settings.")
        hint.setWordWrap(True)
        box.addWidget(hint)
        form = QFormLayout()
        self.reference_combo = QComboBox()
        for label, _key, _fit in self.references():
            self.reference_combo.addItem(label)
        self.reference_combo.currentIndexChanged.connect(self._show_reference)
        form.addRow("Reference", self.reference_combo)
        box.addLayout(form)
        self.reference_note = QLabel("")
        self.reference_note.setWordWrap(True)
        self.reference_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.reference_note)
        box.addStretch(1)
        return page

    def reference_choice(self):
        """``{"key", "label", "fit"}``, or None."""
        entries = self.references()
        index = self.reference_combo.currentIndex()
        if not 0 <= index < len(entries):
            return None
        label, key, fit = entries[index]
        return {"key": key, "label": label.split("   [")[0], "fit": fit}

    def reference_levels(self):
        choice = self.reference_choice()
        if choice is None:
            raise ValueError("choose a reference")
        fit = choice["fit"]
        return kzmap.levels_from_reference(self.hv, fit["hv"], fit["ef"])

    def _show_reference(self, *_):
        if not hasattr(self, "reference_note") or self.method() != "reference":
            return
        choice = self.reference_choice()
        if choice is None:
            self.reference_note.setText("Choose a reference.")
            self.fit_button.setEnabled(False)
            return
        fit = choice["fit"]
        ref_hv = np.asarray(fit["hv"], float)
        lines = [f"{choice['label']}: {ref_hv.size} Fermi levels, "
                 f"{ref_hv.min():.6g} to {ref_hv.max():.6g} eV "
                 f"({fit.get('method') or 'aligned'})."]
        try:
            ef, inside = self.reference_levels()
        except ValueError as exc:
            self.reference_note.setText("\n".join(lines + [str(exc)]))
            self.curve.setData([], [])
            self.fit_button.setEnabled(False)
            return
        self.curve.setData(self.hv[inside], ef[inside])
        self.failed_curve.setData([], [])
        lines.append(f"{int(inside.sum())} of this scan's {self.hv.size} "
                     f"spectra lie in its range"
                     + ("." if inside.all() else
                        f"; the other {int((~inside).sum())} are cut off."))
        self.reference_note.setText("\n".join(lines))
        self.fit_button.setEnabled(True)

    def run_reference(self):
        try:
            ef, inside = self.reference_levels()
            result = kzmap.align_to_levels(
                np.asarray(self.contour.full_cube(), dtype=float), self.energy,
                ef, normalise=self.normalise.isChecked(), keep=inside)
        except ValueError as exc:
            self._failed(exc)
            return None
        self._running_method = "reference"
        self._finish(result)
        return True


def _temperature_of(data, default: float = 30.0) -> float:
    from arpes_viewer.ui.viewers.windows import metadata_temperature
    return metadata_temperature(data, default)


def _unique(name: str, taken) -> str:
    taken = set(taken or ())
    if name not in taken:
        return name
    index = 2
    while f"{name} ({index})" in taken:
        index += 1
    return f"{name} ({index})"
