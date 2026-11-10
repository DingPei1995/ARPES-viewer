"""
ui/panels/pocket.py
===================
The Fermi-pocket window: the contour of one pocket of a k-map, its area,
and what the area means for a **quasi-two-dimensional** sample. Under test
(new in 1.3.3).

Opened from the tool panel (Advanced -> Fermi pocket (quasi-2D)...) with a
map in momentum selected. The constant-energy plane on the left, with the
centre (drag the target, or type it), the ring the band is looked for in
(dashed), the fitted k_F of every ray (yellow; red crosses: rays dropped)
and the contour through them. On the right, k_F against the angle, one ray
with its fit, and -- after **Area against energy** -- the area at a range
of energies with the cyclotron mass.

The window says at its top what the numbers rest on: they are a property
of the Fermi surface only when the bands do not disperse along k_z. The
computation is :mod:`tools.spectra.pocket`, which imports no Qt.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                             QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                             QHeaderView, QLabel, QPushButton, QSplitter,
                             QTableWidget, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

from arpes_viewer.loader.scan import axis_slots
from arpes_viewer.tools.spectra import pocket as PK
from arpes_viewer.ui.common.paths import native
from arpes_viewer.ui.common.screen import fits_screen
from arpes_viewer.ui.panels.process import spin, whole
from arpes_viewer.ui.viewers.widgets import (apply_colormap, plain_image_view,
                                             show_frame, strip_stock_menu)

__all__ = ["PocketDialog", "NOTICE_HTML"]

NOTICE_HTML = (
    "<b>Under test</b> (new in 1.3.3): check every number against the "
    "picture, and please report what looks wrong.<br>"
    "<b>Quasi-two-dimensional samples only.</b> The area of a contour in a "
    "k-map is a property of the Fermi surface only when the bands do not "
    "disperse along k<sub>z</sub> -- a surface state, a single layer, a "
    "layered material whose Fermi surface is a cylinder. Then one map is "
    "the whole Fermi surface, and the area gives the carrier density, the "
    "quantum-oscillation frequency and the cyclotron mass. For a "
    "three-dimensional Fermi surface the map is one curved sheet through "
    "it, at a k<sub>z</sub> set by the photon energy and smeared by the "
    "escape depth: the contour is not an extremal orbit, and the numbers "
    "below mean nothing.")


def _energy_at_ef(data) -> float:
    """E_F on the map's energy axis: 0 when the axis is E - E_F."""
    info = getattr(data.scan, "info", {}) or {}
    labels = getattr(data.scan, "labels", {}) or {}
    for key in info:
        if str(key).rsplit(".", 1)[-1].lower() == "ef_subtracted":
            return 0.0
    label = str(labels.get("z", ""))
    if any(mark in label for mark in ("E_F", "E-Ef", "E − E_F")):
        return 0.0
    return float("nan")


@fits_screen
class PocketDialog(QDialog):
    """The Fermi pocket of ``data`` (a k-map, ``(name, data)``)."""

    datasetsCreated = pyqtSignal(list)

    def __init__(self, dataset, parent=None, colormap="gray",
                 existing_names=None):
        super().__init__(parent)
        self.name, self.data = dataset
        if self.data.kind != "k_map":
            raise ValueError("a Fermi pocket is traced on a map converted "
                             "to momentum (a k-map)")
        self.setWindowTitle(f"Fermi pocket (quasi-2D, under test) — {self.name}")
        self.resize(1320, 900)
        self.colormap = colormap
        self._existing = existing_names or (lambda: [])
        slots = axis_slots("k_map", "constructor")
        self.axes = [np.asarray(getattr(self.data.scan, s), dtype=float)
                     for s in slots]
        labels = dict(self.data.scan.labels or {})
        self.labels = [labels.get(s, s) for s in slots]
        self.values = self.data.scan.value        # may be lazy: read by plane
        self.contour = None
        self.fitted = None
        self.series = None
        self.kept = []
        kx, ky, energy = self.axes

        layout = QVBoxLayout(self)
        notice = QLabel(NOTICE_HTML)
        notice.setWordWrap(True)
        notice.setStyleSheet("background-color: #fff6d6; border: 1px solid "
                             "#e8d48a; border-radius: 4px; padding: 5px; "
                             "color: #5a4a10;")
        layout.addWidget(notice)

        # -- the pictures ----------------------------------------------------
        split = QSplitter(Qt.Horizontal)
        self.image = plain_image_view(self.labels[0], self.labels[1])
        self.image.view.setAspectLocked(True)
        apply_colormap(self.image, colormap, False)
        pen = pg.mkPen("#35d0ff", width=2)
        self.contour_line = pg.PlotCurveItem(pen=pen)
        self.ring_lines = [pg.PlotCurveItem(pen=pg.mkPen("#ffffff", width=1,
                                                         style=Qt.DashLine))
                           for _ in range(2)]
        self.points = pg.ScatterPlotItem(size=6, pen=None,
                                         brush=pg.mkBrush(255, 210, 0, 230))
        self.dropped = pg.ScatterPlotItem(size=7, symbol="x",
                                          pen=pg.mkPen("#ff4040", width=1.5),
                                          brush=None)
        self.ray_line = pg.PlotCurveItem(pen=pg.mkPen("#ff9a3c", width=1))
        self.target = pg.TargetItem(size=14, pos=(0.0, 0.0),
                                    pen=pg.mkPen("#ff3030", width=2))
        self.target.setZValue(20)
        for item in (*self.ring_lines, self.ray_line, self.contour_line,
                     self.dropped, self.points, self.target):
            self.image.view.addItem(item)
        self.target.sigPositionChangeFinished.connect(self._target_moved)
        split.addWidget(self.image)

        self.plots = QTabWidget()
        self.angle_plot = pg.PlotWidget()
        self.angle_plot.setLabel("bottom", "Angle about the centre (deg)")
        self.angle_plot.setLabel("left", "k_F (Å⁻¹)")
        self.ray_plot = pg.PlotWidget()
        self.ray_plot.setLabel("bottom", "Distance from the centre (Å⁻¹)")
        self.ray_plot.setLabel("left", "Intensity")
        self.energy_plot = pg.PlotWidget()
        self.energy_plot.setLabel("bottom", "Energy (eV)")
        self.energy_plot.setLabel("left", "Area (Å⁻²)")
        for plot in (self.angle_plot, self.ray_plot, self.energy_plot):
            strip_stock_menu(plot.getPlotItem())
        ray_page = QWidget()
        ray_box = QVBoxLayout(ray_page)
        ray_box.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.ray_angle = spin(0.0, 0.0, 360.0, 5.0, 1, " °")
        self.ray_angle.setWrapping(True)
        self.ray_angle.setToolTip("Which ray is shown (orange on the map): "
                                  "the data along it and the fitted peak.")
        self.ray_angle.valueChanged.connect(self._show_ray)
        self.ray_note = QLabel("")
        row.addWidget(QLabel("Ray at"))
        row.addWidget(self.ray_angle)
        row.addWidget(self.ray_note, 1)
        ray_box.addLayout(row)
        ray_box.addWidget(self.ray_plot, 1)
        self.plots.addTab(self.angle_plot, "k_F against angle")
        self.plots.addTab(ray_page, "One ray")
        self.plots.addTab(self.energy_plot, "Area against energy")
        split.addWidget(self.plots)
        split.setSizes([640, 620])
        layout.addWidget(split, 1)

        # -- the settings ------------------------------------------------------
        controls = QHBoxLayout()
        box = QGroupBox("1. The plane")
        form = QFormLayout(box)
        ef = _energy_at_ef(self.data)
        step = abs(float(energy[-1] - energy[0])) / max(energy.size - 1, 1)
        self.ef = spin(0.0 if np.isfinite(ef) else float(energy.max()),
                       -1e5, 1e5, 0.001, 4, " eV")
        self.ef.setToolTip("E_F on this map's energy axis: 0 for a map on "
                           "E − E_F. Fit the Fermi level first (Basic tab).")
        form.addRow("E_F at", self.ef)
        self.energy = spin(self.ef.value(), float(energy.min()),
                           float(energy.max()), max(step, 1e-4), 4, " eV")
        self.energy.setToolTip("The energy of the plane the contour is "
                               "traced on: E_F for the Fermi surface.")
        form.addRow("Energy", self.energy)
        self.half_width = spin(max(1.5 * step, 0.002), 0.0, 5.0,
                               max(step, 1e-4), 4, " eV")
        self.half_width.setToolTip(
            "The plane is the mean over the energy ± this. Wider: less "
            "noise, but at E_F the Fermi cut-off empties the upper half of "
            "the window, so the plane is that of a slightly lower energy "
            "-- Area against energy reads the area at E_F free of that.")
        form.addRow("± half width", self.half_width)
        for widget in (self.ef, self.energy, self.half_width):
            widget.setMinimumWidth(125)
        if not np.isfinite(ef):
            warn = QLabel("<span style='color:#b00'>This map's energy axis "
                          "is not E − E_F: set E_F, or fit it first.</span>")
            warn.setWordWrap(True)
            form.addRow(warn)
        controls.addWidget(box, 2)

        box = QGroupBox("2. The pocket")
        form = QFormLayout(box)
        self.centre_x = spin(0.0, float(kx.min()), float(kx.max()), 0.005, 4)
        self.centre_y = spin(0.0, float(ky.min()), float(ky.max()), 0.005, 4)
        if not kx.min() <= 0.0 <= kx.max():
            self.centre_x.setValue(float(kx.mean()))
        if not ky.min() <= 0.0 <= ky.max():
            self.centre_y.setValue(float(ky.mean()))
        row = QHBoxLayout()
        row.addWidget(self.centre_x)
        row.addWidget(self.centre_y)
        self.recentre_button = QPushButton("Centre on the contour")
        self.recentre_button.setToolTip(
            "Move the centre to the centre of area of the contour found. "
            "The area does not depend on the centre, but the rays cross "
            "the band squarely from the middle, and a symmetry is only "
            "right about the middle.")
        self.recentre_button.clicked.connect(self.recentre)
        row.addWidget(self.recentre_button)
        form.addRow("Centre (drag the red target)", row)
        reach = 0.5 * min(float(np.ptp(kx)), float(np.ptp(ky)))
        self.r_min = spin(0.1 * reach, 0.0, 10.0, 0.01, 4, " Å⁻¹")
        self.r_max = spin(0.8 * reach, 0.0, 10.0, 0.01, 4, " Å⁻¹")
        for box_, text in ((self.r_min, "inner"), (self.r_max, "outer")):
            box_.setToolTip(
                f"The {text} radius of the ring (dashed) the band is looked "
                f"for in. Close it around this pocket's band, so that no "
                f"other band is inside it.")
        row = QHBoxLayout()
        row.addWidget(self.r_min)
        row.addWidget(QLabel("to"))
        row.addWidget(self.r_max)
        form.addRow("Look between", row)
        self.rays = whole(72, 12, 720, 12)
        self.rays.setToolTip("How many rays go out from the centre, at "
                             "equal angles; each gives one k_F.")
        self.order = whole(6, 0, 40)
        self.order.setToolTip(
            "The contour is a Fourier series of the radius against the "
            "angle, up to this harmonic. 0 is a circle, 2 allows an "
            "ellipse; raise it for a pocket with corners, lower it when "
            "the contour follows the noise.")
        self.fold = whole(1, 1, 12)
        self.fold.setToolTip(
            "A rotation axis through the centre: 1 for none. With 2, 3, 4 "
            "or 6 only the harmonics that symmetry allows are kept -- "
            "fewer parameters, and gaps in the data are bridged by it. "
            "Only right with the centre on the axis.")
        row = QHBoxLayout()
        for label, widget in (("Rays", self.rays), ("Harmonics", self.order),
                              ("Symmetry", self.fold)):
            row.addWidget(QLabel(label))
            row.addWidget(widget)
        form.addRow(row)
        controls.addWidget(box, 4)

        box = QGroupBox("3. Counting (quasi-2D)")
        form = QFormLayout(box)
        self.spin_choice = QComboBox()
        self.spin_choice.addItems(["2 (spin-degenerate band)",
                                   "1 (spin-split: one contour per spin)"])
        self.spin_choice.setToolTip(
            "How many electrons each k state of this contour holds: 2 for "
            "a spin-degenerate band, 1 when spin-orbit or exchange "
            "splitting gives each spin its own contour (a Rashba surface "
            "state, a topological surface state).")
        form.addRow("States per k", self.spin_choice)
        self.pockets = whole(1, 1, 48)
        self.pockets.setToolTip(
            "How many pockets like this one the Brillouin zone holds: 1 "
            "for a pocket at Γ, 3 for pockets at the three M points of a "
            "hexagonal zone, 2 at its K and K′, ...")
        form.addRow("Equivalent pockets in the zone", self.pockets)
        info = getattr(self.data.scan, "info", {}) or {}

        def recorded(key, default):
            try:
                return float(info.get(f"bz.{key}", default))
            except (TypeError, ValueError):
                return default
        self.cell_a = spin(recorded("a", 0.0), 0.0, 1e3, 0.01, 4, " Å")
        self.cell_b = spin(recorded("b", 0.0), 0.0, 1e3, 0.01, 4, " Å")
        self.cell_gamma = spin(recorded("gamma", 90.0), 1.0, 179.0, 1.0, 2, " °")
        for widget in (self.cell_a, self.cell_b, self.cell_gamma):
            widget.setToolTip(
                "The unit cell of the measured plane (the surface): a, b "
                "and the angle between them. Its Brillouin zone has the "
                "area (2π)²/(a b sin γ), which turns the pocket's area "
                "into carriers per cell. Leave a at 0 if not known (b = 0 "
                "means b = a).")
        row = QHBoxLayout()
        for widget in (self.cell_a, self.cell_b, self.cell_gamma):
            row.addWidget(widget)
        form.addRow("In-plane cell a, b, γ", row)
        self.carrier = QComboBox()
        self.carrier.addItems(["electron pocket", "hole pocket"])
        self.carrier.setToolTip(
            "Whether the states inside the contour are filled (electron "
            "pocket) or empty (hole pocket). Area against energy sets it "
            "from the sign of dA/dE: an electron pocket grows with energy.")
        form.addRow("This is a", self.carrier)
        controls.addWidget(box, 3)
        layout.addLayout(controls)

        # -- the result ----------------------------------------------------------
        lower = QHBoxLayout()
        column = QVBoxLayout()
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        column.addWidget(self.result_label, 1)
        row = QHBoxLayout()
        self.e_from = spin(max(float(energy.min()), self.ef.value() - 0.2),
                           float(energy.min()), float(energy.max()),
                           max(step, 1e-3), 4, " eV")
        self.e_steps = whole(9, 3, 200)
        self.series_button = QPushButton("Area against energy")
        self.series_button.setToolTip(
            "Trace the same pocket at a range of energies, from the plane "
            "above down (or up) to the energy given, each contour looked "
            "for near the one before. Gives dA/dE -- the cyclotron mass, "
            "and whether this is an electron or a hole pocket -- and the "
            "area at E_F read off the line.")
        self.series_button.clicked.connect(lambda: self.run_series())
        row.addWidget(self.series_button)
        row.addWidget(QLabel("from the plane's energy to"))
        row.addWidget(self.e_from)
        row.addWidget(QLabel("in"))
        row.addWidget(self.e_steps)
        row.addWidget(QLabel("planes"))
        row.addStretch(1)
        column.addLayout(row)
        row = QHBoxLayout()
        for text, slot, tip in (
                ("Keep this pocket", self.keep,
                 "Add this pocket to the table on the right, to count "
                 "several pockets of one Fermi surface together."),
                ("Contour to list", self.export,
                 "Add k_F against angle (with its error, the peak width and "
                 "the contour) to the main list as curves -- and the area "
                 "against energy, if it was run."),
                ("Save table...", lambda: self.save_table(),
                 "Write the rays, the contour and the numbers as a CSV file.")):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        column.addLayout(row)
        lower.addLayout(column, 3)

        column = QVBoxLayout()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Pocket", "Area (Å⁻²)", "× pockets × spin", "Carriers / cell",
             "n (10¹² cm⁻²)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMaximumHeight(130)
        column.addWidget(self.table)
        row = QHBoxLayout()
        self.total_label = QLabel("")
        self.total_label.setWordWrap(True)
        self.total_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        remove = QPushButton("Remove")
        remove.clicked.connect(self.remove_kept)
        row.addWidget(self.total_label, 1)
        row.addWidget(remove)
        column.addLayout(row)
        lower.addLayout(column, 2)
        layout.addLayout(lower)

        # A change retraces after a short pause (72 small fits: a fraction
        # of a second), so the picture follows the controls.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.update_trace)
        for widget in (self.ef, self.energy, self.half_width, self.centre_x,
                       self.centre_y, self.r_min, self.r_max, self.rays,
                       self.order, self.fold, self.pockets, self.cell_a,
                       self.cell_b, self.cell_gamma):
            widget.setKeyboardTracking(False)
            widget.valueChanged.connect(self._changed)
        for widget in (self.spin_choice, self.carrier):
            widget.currentIndexChanged.connect(self._changed)
        self.show_plane(auto_range=True)
        self.update_trace()

    # -- settings ----------------------------------------------------------------
    def _changed(self, *_):
        self._timer.start()

    def centre(self):
        return self.centre_x.value(), self.centre_y.value()

    def set_centre(self, x: float, y: float):
        for box, value in ((self.centre_x, x), (self.centre_y, y)):
            box.blockSignals(True)
            box.setValue(float(value))
            box.blockSignals(False)
        self.update_trace()

    def _target_moved(self, *_):
        position = self.target.pos()
        self.set_centre(position.x(), position.y())

    def spin_degeneracy(self) -> int:
        return 2 if self.spin_choice.currentIndex() == 0 else 1

    def cell(self):
        """The in-plane cell's area (A^2), or None when a is not given."""
        if self.cell_a.value() <= 0:
            return None
        return PK.cell_area(self.cell_a.value(), self.cell_b.value() or None,
                            self.cell_gamma.value())

    def settings(self) -> dict:
        return {"energy": self.energy.value(),
                "half_width": self.half_width.value(), "ef": self.ef.value(),
                "centre": list(self.centre()), "r_min": self.r_min.value(),
                "r_max": self.r_max.value(), "rays": self.rays.value(),
                "harmonics": self.order.value(), "symmetry": self.fold.value(),
                "spin": self.spin_degeneracy(), "pockets": self.pockets.value(),
                "carrier": "electron" if self.carrier.currentIndex() == 0
                else "hole"}

    # -- the plane and the contour ---------------------------------------------------
    def plane(self, energy: float = None):
        return PK.energy_plane(
            self.values, self.axes,
            self.energy.value() if energy is None else energy,
            self.half_width.value())[0]

    def show_plane(self, auto_range: bool = False):
        self._plane = self.plane()
        finite = self._plane[np.isfinite(self._plane)]
        levels = ((float(finite.min()), float(np.percentile(finite, 99.7)))
                  if finite.size else None)
        show_frame(self.image, self._plane, self.axes[0], self.axes[1],
                   levels=levels, auto_range=auto_range)
        apply_colormap(self.image, self.colormap, False)

    def update_trace(self, *_):
        """Trace the pocket with the settings shown; returns the numbers
        (:meth:`numbers`), or None when no contour was found."""
        self._timer.stop()
        self.series = None if self._series_stale() else self.series
        self.show_plane()
        cx, cy = self.centre()
        self.target.blockSignals(True)
        self.target.setPos(cx, cy)
        self.target.blockSignals(False)
        ring = np.linspace(0.0, 2.0 * np.pi, 181)
        for line, radius in zip(self.ring_lines,
                                (self.r_min.value(), self.r_max.value())):
            line.setData(cx + radius * np.cos(ring), cy + radius * np.sin(ring))
        self.contour = self.fitted = None
        try:
            self.contour = PK.trace(self._plane, self.axes[0], self.axes[1],
                                    (cx, cy), self.r_min.value(),
                                    self.r_max.value(), n_angles=self.rays.value())
            self.contour.energy = self.energy.value()
            if not self.contour.enough():
                raise ValueError(
                    f"only {int(self.contour.ok.sum())} of "
                    f"{self.contour.ok.size} rays found a band: check the "
                    f"centre and the ring (the dashed circles must hold "
                    f"this pocket's band, all the way round)")
            self.fitted = self.contour.fourier(self.order.value(),
                                               self.fold.value())
        except ValueError as exc:
            self._draw()
            self.result_label.setText(f"<span style='color:#b00'>{exc}</span>")
            return None
        self._draw()
        return self._report()

    def _series_stale(self) -> bool:
        return (self.series is not None
                and getattr(self, "_series_settings", None) != self._series_key())

    def _series_key(self):
        s = self.settings()
        return (tuple(s["centre"]), s["r_min"], s["r_max"], s["rays"],
                s["harmonics"], s["symmetry"], s["half_width"], s["ef"])

    def _draw(self):
        contour, fitted = self.contour, self.fitted
        self.angle_plot.clear()
        if contour is None:
            for item in (self.points, self.dropped):
                item.setData([], [])
            self.contour_line.setData([], [])
            self._show_ray()
            return
        x, y = contour.xy()
        self.points.setData(x, y)
        bad = ~contour.ok & np.isfinite(contour.radius)
        self.dropped.setData(
            contour.centre[0] + contour.radius[bad] * np.cos(contour.angles[bad]),
            contour.centre[1] + contour.radius[bad] * np.sin(contour.angles[bad]))
        degrees = np.degrees(contour.angles)
        ok = contour.ok
        self.angle_plot.plot(degrees[ok], contour.radius[ok], pen=None,
                             symbol="o", symbolSize=5, symbolBrush="#bd4921",
                             symbolPen=None)
        self.angle_plot.addItem(pg.ErrorBarItem(
            x=degrees[ok], y=contour.radius[ok],
            height=2 * np.nan_to_num(contour.radius_error[ok]),
            pen=pg.mkPen("#bd4921")))
        if bad.any():
            self.angle_plot.plot(degrees[bad], contour.radius[bad], pen=None,
                                 symbol="x", symbolSize=7,
                                 symbolPen=pg.mkPen("#ff4040"), symbolBrush=None)
        if fitted is not None:
            phi = np.linspace(0.0, 2.0 * np.pi, 361)
            radius = fitted.radius(phi)
            self.contour_line.setData(contour.centre[0] + radius * np.cos(phi),
                                      contour.centre[1] + radius * np.sin(phi))
            self.angle_plot.plot(np.degrees(phi), radius,
                                 pen=pg.mkPen("#0d7377", width=2))
        else:
            self.contour_line.setData([], [])
        self._show_ray()

    def _show_ray(self, *_):
        self.ray_plot.clear()
        contour = self.contour
        if contour is None:
            self.ray_line.setData([], [])
            self.ray_note.setText("")
            return
        angle = np.radians(self.ray_angle.value())
        index = int(np.argmin(np.abs(np.angle(np.exp(1j * (contour.angles - angle))))))
        phi = contour.angles[index]
        cx, cy = contour.centre
        self.ray_line.setData(
            [cx + contour.ring[0] * np.cos(phi), cx + contour.ring[1] * np.cos(phi)],
            [cy + contour.ring[0] * np.sin(phi), cy + contour.ring[1] * np.sin(phi)])
        self.ray_plot.plot(contour.radii, contour.profiles[index], pen=None,
                           symbol="o", symbolSize=4, symbolBrush="#555",
                           symbolPen=None)
        model = contour.models[index]
        if np.isfinite(model).any():
            self.ray_plot.plot(contour.radii, model, connect="finite",
                               pen=pg.mkPen("#0d7377" if contour.ok[index]
                                            else "#ff4040", width=2))
        if contour.ok[index]:
            self.ray_note.setText(
                f"{np.degrees(phi):.0f}°: k_F = {contour.radius[index]:.4f} ± "
                f"{contour.radius_error[index]:.2g} Å⁻¹, FWHM "
                f"{contour.width[index]:.3g} Å⁻¹")
        else:
            self.ray_note.setText(f"{np.degrees(phi):.0f}°: dropped — "
                                  f"{contour.why[index] or 'no fit'}")

    def recentre(self):
        """Move the centre to the contour's centre of area and retrace."""
        if self.fitted is None:
            return None
        # without the symmetry: a contour made n-fold about the centre has
        # its middle there by construction, wherever the pocket is
        free = self.contour.fourier(max(self.order.value(), 4), 1)
        x, y = free.centroid(self.contour.centre)
        self.set_centre(x, y)
        return x, y

    # -- the numbers ---------------------------------------------------------------------
    def numbers(self):
        """Everything worked out for the contour shown, as a dict (see
        :func:`tools.spectra.pocket.numbers`), or None without one."""
        if self.fitted is None:
            return None
        area, error = self.fitted.area()
        out = PK.numbers(area, error, spin=self.spin_degeneracy(),
                         pockets=self.pockets.value(), cell=self.cell())
        r_low, a_low, r_high, a_high = self.fitted.extremes()
        out.update({
            "energy": self.energy.value(), "ef": self.ef.value(),
            "centre": list(self.contour.centre),
            "rays": int(self.contour.ok.size),
            "rays_kept": int(self.contour.ok.sum()),
            "polygon_area": self.contour.polygon_area(),
            "k_f_min": r_low, "k_f_min_angle": float(np.degrees(a_low)),
            "k_f_max": r_high, "k_f_max_angle": float(np.degrees(a_high)),
            "mean_width": float(np.nanmedian(self.contour.width[self.contour.ok])),
            "carrier": "electron" if self.carrier.currentIndex() == 0 else "hole",
            "notice": PK.NOTICE})
        if self.series is not None:
            mass, mass_error = self.series.mass()
            area_ef, area_ef_error = self.series.area_at_ef()
            velocity, velocity_error = self.series.fermi_velocity()
            out.update({"mass": mass, "mass_error": mass_error,
                        "area_at_ef": area_ef, "area_at_ef_error": area_ef_error,
                        "band_edge": self.series.band_edge(),
                        "fermi_velocity": velocity,
                        "fermi_velocity_error": velocity_error})
        return out

    def _report(self):
        n = self.numbers()
        if n is None:
            return None
        lines = [
            f"<b>Area {n['area']:.4g} ± {n['area_error']:.2g} Å⁻²</b> at "
            f"E = {n['energy']:.4g} eV ({n['rays_kept']} of {n['rays']} rays "
            f"kept; the polygon through them: {n['polygon_area']:.4g} Å⁻²). "
            f"k_F from {n['k_f_min']:.4g} Å⁻¹ (at {n['k_f_min_angle']:.0f}°) "
            f"to {n['k_f_max']:.4g} Å⁻¹ (at {n['k_f_max_angle']:.0f}°); a "
            f"circle of this area has k_F = {n['k_f']:.4g} Å⁻¹."]
        if n["rays_kept"] < 0.7 * n["rays"]:
            lines.append("<span style='color:#b00'>Many rays were dropped: "
                         "look at them (One ray), and close the ring around "
                         "this band or give a symmetry.</span>")
        counted = (f"For a quasi-2D sample: n = {n['density'] / 1e12:.4g} ± "
                   f"{n['density_error'] / 1e12:.2g} × 10¹² cm⁻² "
                   f"({n['spin']} per k × {n['pockets']} pocket(s))")
        if "per_cell" in n:
            counted += (f"; {100 * n['zone_fraction']:.3g} % of the zone "
                        f"({n['zone_area']:.4g} Å⁻²), "
                        f"{n['per_cell']:.4g} ± {n['per_cell_error']:.2g} "
                        f"carriers per cell")
        counted += (f"; quantum-oscillation frequency "
                    f"{n['frequency']:.4g} ± {n['frequency_error']:.2g} T.")
        lines.append(counted)
        if "mass" in n and np.isfinite(n["mass"]):
            kind = self.series.carrier()
            lines.append(
                f"From {int(np.isfinite(self.series.areas).sum())} energies: "
                f"m_c = (ħ²/2π) dA/dE = {n['mass']:.3g} ± "
                f"{n['mass_error']:.2g} mₑ"
                + (f" — {'an electron' if kind == 'electron' else 'a hole'} "
                   f"pocket" if kind else " — the sign is not significant")
                + f"; area at E_F off the line {n['area_at_ef']:.4g} ± "
                  f"{n['area_at_ef_error']:.2g} Å⁻²; mean v_F = "
                  f"{n['fermi_velocity']:.3g} eV·Å; the line reaches zero "
                  f"area at E = {n['band_edge']:.3g} eV (the band edge, if "
                  f"parabolic).")
        lines.append(
            "<i>The errors are statistical (the scatter of the rays). The "
            "energy window, the momentum conversion (work function, where "
            "Γ is) and the resolution are not in them, and are usually "
            "larger.</i>")
        self.result_label.setText("<br>".join(lines))
        return n

    # -- area against energy -----------------------------------------------------------
    def run_series(self, energies=None, background: bool = True):
        """The area at a range of energies (see the button's tip); returns
        the :class:`tools.spectra.pocket.PocketSeries`. ``background=False``
        computes it here, with no progress window (a script, a test)."""
        from arpes_viewer.ui.common.jobs import JobCancelled, busy, run_blocking
        if self.fitted is None:
            return None
        if energies is None:
            energies = np.linspace(self.energy.value(), self.e_from.value(),
                                   self.e_steps.value())
        s = self.settings()
        values = np.asarray(self.values, dtype=float)   # read here, once

        def work(report):
            return PK.series(values, self.axes, s["centre"], energies,
                             s["r_min"], s["r_max"],
                             half_width=s["half_width"], n_angles=s["rays"],
                             order=s["harmonics"], fold=s["symmetry"],
                             ef=s["ef"], progress=report)
        try:
            self.series = (work(lambda *_a: None)
                           if busy() or not background else
                           run_blocking(self, "Area against energy", work))
        except JobCancelled:
            return None
        self._series_settings = self._series_key()
        kind = self.series.carrier()
        if kind:
            self.carrier.blockSignals(True)
            self.carrier.setCurrentIndex(0 if kind == "electron" else 1)
            self.carrier.blockSignals(False)
        self._draw_series()
        self.plots.setCurrentWidget(self.energy_plot)
        self._report()
        return self.series

    def _draw_series(self):
        self.energy_plot.clear()
        series = self.series
        if series is None:
            return
        good = np.isfinite(series.areas)
        self.energy_plot.plot(series.energies[good], series.areas[good],
                              pen=None, symbol="o", symbolSize=6,
                              symbolBrush="#bd4921", symbolPen=None)
        self.energy_plot.addItem(pg.ErrorBarItem(
            x=series.energies[good], y=series.areas[good],
            height=2 * np.nan_to_num(series.area_errors[good]),
            pen=pg.mkPen("#bd4921")))
        line = series.line()
        if line is not None:
            span = np.array([min(series.energies.min(), series.ef),
                             max(series.energies.max(), series.ef)])
            self.energy_plot.plot(span, line.value(span - series.ef),
                                  pen=pg.mkPen("#0d7377", width=2))
        self.energy_plot.addItem(pg.InfiniteLine(
            pos=series.ef, angle=90, pen=pg.mkPen("#888", style=Qt.DotLine)))

    # -- several pockets -------------------------------------------------------------------
    def keep(self):
        """Add the pocket shown to the table of pockets counted together."""
        n = self.numbers()
        if n is None:
            return None
        n = dict(n, name=f"{'e' if n['carrier'] == 'electron' else 'h'}"
                         f"{len(self.kept) + 1} at "
                         f"({n['centre'][0]:.3g}, {n['centre'][1]:.3g})")
        self.kept.append(n)
        self._fill_table()
        return n

    def remove_kept(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()},
                      reverse=True) or ([len(self.kept) - 1] if self.kept else [])
        for row in rows:
            del self.kept[row]
        self._fill_table()

    def totals(self) -> dict:
        """The pockets kept, counted together: electrons minus holes."""
        sign = lambda n: 1.0 if n["carrier"] == "electron" else -1.0
        out = {"pockets": len(self.kept),
               "density": sum(sign(n) * n["density"] for n in self.kept),
               "electrons": sum(n["density"] for n in self.kept
                                if n["carrier"] == "electron"),
               "holes": sum(n["density"] for n in self.kept
                            if n["carrier"] == "hole")}
        if self.kept and all("per_cell" in n for n in self.kept):
            out["per_cell"] = sum(sign(n) * n["per_cell"] for n in self.kept)
            out["per_cell_error"] = float(np.sqrt(sum(
                n["per_cell_error"] ** 2 for n in self.kept)))
        return out

    def _fill_table(self):
        self.table.setRowCount(len(self.kept))
        for row, n in enumerate(self.kept):
            cells = [n["name"], f"{n['area']:.4g} ± {n['area_error']:.2g}",
                     f"× {n['pockets']} × {n['spin']}",
                     (f"{n['per_cell']:.4g}" if "per_cell" in n else "—"),
                     f"{n['density'] / 1e12:.4g}"]
            for column, text in enumerate(cells):
                self.table.setItem(row, column, QTableWidgetItem(text))
        total = self.totals()
        if not self.kept:
            self.total_label.setText("")
            return
        text = (f"<b>Electrons − holes</b>: "
                f"{total['density'] / 1e12:.4g} × 10¹² cm⁻²")
        if "per_cell" in total:
            text += (f" = {total['per_cell']:.4g} ± "
                     f"{total['per_cell_error']:.2g} per cell (Luttinger "
                     f"count, quasi-2D)")
        self.total_label.setText(text)

    # -- keeping it ------------------------------------------------------------------------
    def _unique(self, name: str) -> str:
        taken, base, n = set(self._existing()), name, 2
        while name in taken:
            name = f"{base} ({n})"
            n += 1
        return name

    def export(self):
        """The contour (and the area against energy) as curve datasets in
        the main list; returns them."""
        if self.contour is None or self.fitted is None:
            return []
        from arpes_viewer.ui.viewers.curves import curve_dataset
        import arpes_viewer.tools.spectra.curves as C
        contour = self.contour
        degrees = np.degrees(contour.angles)
        radius = np.where(contour.ok, contour.radius, np.nan)
        x, values, names = C.table(degrees, [
            ("k_F", radius), ("σ k_F", np.where(contour.ok, contour.radius_error,
                                                np.nan)),
            ("FWHM", np.where(contour.ok, contour.width, np.nan)),
            ("contour", self.fitted.radius(contour.angles))])
        parameters = {key: value for key, value in self.numbers().items()
                      if not isinstance(value, (list, tuple))}
        parameters.update({"centre_x": contour.centre[0],
                           "centre_y": contour.centre[1],
                           **{k: v for k, v in self.settings().items()
                              if k in ("half_width", "r_min", "r_max",
                                       "harmonics", "symmetry")}})
        info = dict(getattr(self.data.scan, "info", {}) or {})
        made = [curve_dataset(
            "mdc", x, values, names,
            x_label="Angle about the pocket centre (deg)",
            value_label="k_F (Å⁻¹)", name=self._unique(f"{self.name} [pocket]"),
            step="fermi_pocket", parameters=parameters, source_info=info,
            prefix="proc.pocket", source=self.name)]
        if self.series is not None:
            x, values, names = C.table(self.series.energies, [
                ("Area", self.series.areas), ("σ Area", self.series.area_errors)])
            made.append(curve_dataset(
                "edc", x, values, names, x_label=self.labels[2],
                value_label="Pocket area (Å⁻²)",
                name=self._unique(f"{self.name} [pocket area]"),
                step="fermi_pocket_series", parameters=parameters,
                source_info=info, prefix="proc.pocket", source=self.name))
        self.datasetsCreated.emit(made)
        return made

    def save_table(self, path: str = ""):
        if self.contour is None or self.fitted is None:
            return None
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save the pocket", f"{self.name}_pocket.csv",
                "CSV (*.csv)")
        if not path:
            return None
        contour = self.contour
        notes = [f"# {PK.NOTICE}"]
        notes += [f"# {key}: {value}" for key, value in self.numbers().items()
                  if key != "notice"]
        for kept in self.kept:
            notes.append(f"# kept pocket {kept['name']}: area {kept['area']:.6g}"
                         f" A^-2, {kept['carrier']}, x{kept['pockets']} x"
                         f"{kept['spin']}")
        if self.series is not None:
            for energy, area, error in zip(self.series.energies,
                                           self.series.areas,
                                           self.series.area_errors):
                notes.append(f"# area at E = {energy:.6g}: {area:.6g} +- "
                             f"{error:.3g}")
        x, y = (contour.centre[0] + contour.radius * np.cos(contour.angles),
                contour.centre[1] + contour.radius * np.sin(contour.angles))
        table = np.column_stack([
            np.degrees(contour.angles), contour.radius, contour.radius_error,
            contour.width, contour.ok.astype(float), x, y,
            self.fitted.radius(contour.angles)])
        np.savetxt(path, table, delimiter=",", comments="",
                   header="\n".join(notes) + "\nangle_deg,k_f,k_f_error,fwhm,"
                          "kept,kx,ky,contour")
        self.result_label.setText(self.result_label.text()
                                  + f"<br>Saved to {native(path)}")
        return path
