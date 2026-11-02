"""
ui/panels/tightbinding.py
=========================
The tight-binding fit, step by step: **one band** on a Bravais lattice,
one hopping per symmetry orbit of neighbours -- or **two bands, hybridised**,
each such a band and coupled by V(k), the measured bands being the two
eigenvalues.

Opened from the tool panel's Figure tab (Tight-binding fit...), with a
map in momentum selected -- a k-map, or a converted kz map -- or with
nothing selected, to fit band points read from a file. Four steps:

1. **The lattice** -- 2-D layer or 3-D crystal (or the Brillouin-zone
   tool's last crystal), how it is turned against kx, and how many shells
   of neighbours get a hopping of their own.
2. **Band points** -- traced by ridge detection on constant-energy planes
   of the map (one energy or several), clicked on the plane, or read from
   a CSV (the ridge-detection window writes one).
3. **Fit** -- the hoppings with their errors, the rms misfit, and the
   model's contour drawn over the data at the energy shown.
4. **Use the model** -- its spectral function as a new map in the list,
   for side-by-side comparison, and the parameters to a file.

The model and the fit are :mod:`tools.crystal.tightbinding`, which imports
no Qt.
"""
from __future__ import annotations

import json

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QTransform
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QDoubleSpinBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QListWidget,
                             QPushButton, QRadioButton, QSlider, QSpinBox,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget, QAbstractItemView, QHeaderView)

from arpes_viewer.tools.crystal import last_crystal
from arpes_viewer.tools.crystal import tightbinding as TB
from arpes_viewer.tools.processing import ridge as RD
from arpes_viewer.ui.common.screen import fits_screen
from arpes_viewer.ui.common.stepper import Step, Stepper, guard_window
from arpes_viewer.ui.viewers.widgets import (MemoryData, apply_colormap, fit_frame_view,
                                plain_image_view, show_frame)

__all__ = ["TightBindingDialog"]


def _spin(value, lo, hi, decimals=4, suffix=""):
    box = QDoubleSpinBox()
    box.setDecimals(decimals)
    box.setRange(lo, hi)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    return box


@fits_screen
class TightBindingDialog(QDialog):
    """Fit a tight-binding band. ``dataset`` is ``(name, data)`` of a k_map
    or kz_map_k, or None (points from a file only)."""

    datasetsCreated = pyqtSignal(list)

    def __init__(self, dataset=None, parent=None, colormap="Greys",
                 existing_names=None):
        super().__init__(parent)
        self.setWindowTitle("Tight-binding fit")
        self.resize(1080, 720)
        self.name, self.data = dataset if dataset else ("points", None)
        self.colormap = colormap
        self._existing = existing_names or (lambda: [])
        self.k_points = np.zeros((0, 2))
        self.energies = np.zeros(0)
        self.branches = np.zeros(0, dtype=int)
        self.model = None
        self.result = None
        self._isocurves = []

        layout = QVBoxLayout(self)
        self.stepper = Stepper([self._step_lattice(), self._step_points(),
                                self._step_fit(), self._step_use()], self,
                               finish_text="Close")
        layout.addWidget(self.stepper)
        guard_window(self, self.stepper, "tight_binding", "Tight-binding fit",
                     close_on_finish=True)
        self._lattice_changed()

    # ==================================================================
    # Step 1: the lattice
    # ==================================================================
    def _step_lattice(self):
        page = QWidget()
        column = QVBoxLayout(page)
        mode = QHBoxLayout()
        self.mode_2d = QRadioButton("2-D layer (a, b, gamma)")
        self.mode_3d = QRadioButton("3-D crystal (space group)")
        self.mode_2d.setChecked(True)
        mode.addWidget(self.mode_2d)
        mode.addWidget(self.mode_3d)
        self.from_bz_button = QPushButton("Take the crystal from the "
                                          "Brillouin-zone tool")
        self.from_bz_button.setToolTip(last_crystal.describe())
        self.from_bz_button.clicked.connect(self.take_from_bz)
        mode.addWidget(self.from_bz_button)
        mode.addStretch(1)
        column.addLayout(mode)

        boxes = QHBoxLayout()
        self.group_2d = QGroupBox("2-D lattice")
        f2 = QFormLayout(self.group_2d)
        self.a2 = _spin(3.0, 0.1, 100.0, suffix=" Å")
        self.b2 = _spin(3.0, 0.1, 100.0, suffix=" Å")
        self.gamma2 = _spin(90.0, 1.0, 179.0, 3, " °")
        f2.addRow("a", self.a2)
        f2.addRow("b", self.b2)
        f2.addRow("gamma", self.gamma2)
        boxes.addWidget(self.group_2d)
        # The space group first, as in the Brillouin-zone tool: it greys
        # out the cell parameters it fixes, and they follow the free ones.
        from arpes_viewer.ui.common.cellinput import CellInput
        self.group_3d = QGroupBox("3-D crystal (space group first)")
        f3 = QVBoxLayout(self.group_3d)
        self.cell_input = CellInput(self.group_3d, lengths=(3.0, 3.0, 3.0))
        f3.addWidget(self.cell_input)
        self.space_group = self.cell_input.space_group_box
        self.space_group.setToolTip(
            self.space_group.toolTip() + " It also sets the centering, and "
            "so the primitive cell whose neighbours are counted.")
        boxes_3d = self.cell_input.boxes
        self.a3, self.b3, self.c3 = boxes_3d["a"], boxes_3d["b"], boxes_3d["c"]
        self.alpha3, self.beta3, self.gamma3 = (boxes_3d["alpha"], boxes_3d["beta"],
                                                boxes_3d["gamma"])
        boxes.addWidget(self.group_3d)

        geometry = QGroupBox("How the lattice sits on the map")
        fg = QFormLayout(geometry)
        self.azimuth = _spin(0.0, -180.0, 180.0, 3, " °")
        self.azimuth.setToolTip("The lattice's a axis measured from the "
                                "map's kx axis, counter-clockwise.")
        fg.addRow("Azimuth of a", self.azimuth)
        self.kz_plane = _spin(0.0, -50.0, 50.0, 4, " Å⁻¹")
        self.kz_plane.setToolTip("3-D crystal on a k-map: the k_z of the "
                                 "measured plane (from the photon energy "
                                 "and inner potential).")
        fg.addRow("k_z of the plane", self.kz_plane)
        self.kpar_angle = _spin(0.0, -180.0, 180.0, 3, " °")
        self.kpar_angle.setToolTip("Converted kz map: the in-plane direction "
                                   "k_par ran along, from kx.")
        fg.addRow("k_par direction", self.kpar_angle)
        self.n_shells = QSpinBox()
        self.n_shells.setRange(1, 10)
        self.n_shells.setValue(2)
        fg.addRow("Shells of neighbours", self.n_shells)
        boxes.addWidget(geometry)

        model_box = QGroupBox("Bands")
        fm = QFormLayout(model_box)
        self.one_band = QRadioButton("One band")
        self.two_bands = QRadioButton("Two bands, hybridised")
        self.one_band.setChecked(True)
        self.two_bands.setToolTip(
            "Two bands a and b on this lattice, coupled by V(k) = v0 + "
            "sum v_n S_n(k); the measured bands are the two eigenvalues. "
            "For an anticrossing, a hybridisation gap or a bilayer "
            "splitting.")
        fm.addRow(self.one_band)
        fm.addRow(self.two_bands)
        self.n_shells_b = QSpinBox()
        self.n_shells_b.setRange(1, 10)
        self.n_shells_b.setValue(2)
        self.n_shells_b.setToolTip("Hoppings of band b (the box at the left "
                                   "is band a's).")
        fm.addRow("Shells, band b", self.n_shells_b)
        self.n_hybrid = QSpinBox()
        self.n_hybrid.setRange(0, 6)
        self.n_hybrid.setValue(0)
        self.n_hybrid.setToolTip("Shells in the coupling beyond the constant "
                                 "v0: 0 is a k-independent V.")
        fm.addRow("Coupling shells", self.n_hybrid)
        boxes.addWidget(model_box)
        column.addLayout(boxes)
        self.shell_label = QLabel("")
        self.shell_label.setWordWrap(True)
        column.addWidget(self.shell_label)
        column.addStretch(1)

        for widget in (self.mode_2d, self.mode_3d):
            widget.toggled.connect(self._lattice_changed)
        for box in (self.a2, self.b2, self.gamma2, self.azimuth,
                    self.kz_plane, self.kpar_angle):
            box.valueChanged.connect(self._lattice_changed)
        self.cell_input.changed.connect(self._lattice_changed)
        self.n_shells.valueChanged.connect(self._lattice_changed)
        for widget in (self.one_band, self.two_bands):
            widget.toggled.connect(self._lattice_changed)
        self.n_shells_b.valueChanged.connect(self._lattice_changed)
        self.n_hybrid.valueChanged.connect(self._lattice_changed)

        text = ("<b>One band, or two.</b> <b>One band</b> is a single band "
                "on a lattice with one orbital per site: it cannot describe "
                "two bands, their crossing or a hybridisation gap -- fit "
                "each band on its own, and read the hoppings as that band's "
                "effective parameters. <b>Two bands, hybridised</b> fits "
                "two such bands and the coupling V(k) between them at once: "
                "the gap where they would cross is 2|V|. "
                "Describe the lattice the band lives on. A layered crystal "
                "measured at one photon energy is usually best fitted as a "
                "<b>2-D layer</b> (its in-plane a, b and gamma); a 3-D "
                "crystal needs the k_z of the plane the map cuts. The "
                "<b>azimuth</b> says how the lattice is turned against the "
                "map's kx axis -- step 3 can refine it. Each <b>shell</b> of "
                "neighbours -- the lattice vectors the symmetry makes "
                "equivalent: the space group's point group in 3-D, the "
                "lattice's own symmetry in 2-D -- gets one hopping, so two "
                "inequivalent neighbours at the same distance get one each. "
                "Start with 1-2 shells and add more only if the misfit "
                "needs them.")
        return Step("The lattice", text, page, ready=self._lattice_problem)

    def take_from_bz(self):
        values = last_crystal.load()
        if not values:
            self.stepper.missing.setText(last_crystal.describe())
            return False
        params = last_crystal.lattice_params(values)
        if params is None:
            a, b, gamma, azimuth = last_crystal.vectors_2d(values)
            self.mode_2d.setChecked(True)
            self.a2.setValue(a)
            self.b2.setValue(b)
            self.gamma2.setValue(gamma)
        else:
            self.mode_3d.setChecked(True)
            self.cell_input.set_cell(int(params.space_group or 1), params.a,
                                     params.b, params.c, params.alpha,
                                     params.beta, params.gamma)
            azimuth = float(values.get("azimuth_deg", 0.0))
        self.azimuth.setValue(azimuth)
        return True

    def _settings_applied(self):
        """After the remembered settings are back (signals blocked): the
        space group's constraints, and the shells, again."""
        self.cell_input.apply_constraints()
        self._lattice_changed()

    def lattice_vectors(self):
        """Primitive real-space vectors (rows), turned by the azimuth."""
        if self.mode_2d.isChecked():
            vectors = TB.lattice_2d(self.a2.value(), self.b2.value(),
                                    self.gamma2.value())
        else:
            from arpes_viewer.tools.crystal.lattice import LatticeParams, primitive_vectors
            vectors = primitive_vectors(LatticeParams(
                self.a3.value(), self.b3.value(), self.c3.value(),
                self.alpha3.value(), self.beta3.value(), self.gamma3.value(),
                space_group=self.space_group.value()))
        return TB.rotate(vectors, self.azimuth.value())

    def lattice_symmetry(self):
        """The operations that split the shells, as integer matrices on the
        lattice coordinates: the space group's point group (with
        inversion) for a 3-D crystal, the lattice's holohedry for a 2-D
        layer (no basis is given, so nothing lower can be known)."""
        if self.mode_2d.isChecked():
            return TB.lattice_symmetry(self.lattice_vectors())
        from arpes_viewer.tools.crystal.lattice import (
            LatticeParams, point_group_operations, primitive_vectors)
        params = LatticeParams(
            self.a3.value(), self.b3.value(), self.c3.value(),
            self.alpha3.value(), self.beta3.value(), self.gamma3.value(),
            space_group=self.space_group.value())
        return TB.lattice_symmetry(primitive_vectors(params),
                                   point_group_operations(params))

    def _shells(self):
        return TB.shells(self.lattice_vectors(), self.n_shells.value(),
                         symmetry=self.lattice_symmetry())

    def _lattice_problem(self):
        try:
            self._shells()
        except (ValueError, AssertionError) as exc:
            return str(exc)
        return ""

    def _lattice_changed(self, *_):
        three = self.mode_3d.isChecked()
        self.group_2d.setVisible(not three)
        self.group_3d.setVisible(three)
        kz_map = self.data is not None and self.data.kind == "kz_map_k"
        self.kz_plane.setEnabled(three and not kz_map)
        self.kpar_angle.setEnabled(kz_map)
        problem = self._lattice_problem()
        if problem:
            self.shell_label.setText(f"<b>Not a lattice:</b> {problem}")
        else:
            vectors = self.lattice_vectors()
            found = self._shells()
            source = ("the lattice's symmetry" if self.mode_2d.isChecked()
                      else f"space group {self.space_group.value()}")
            two = self.two_bands.isChecked()
            self.n_shells_b.setEnabled(two)
            self.n_hybrid.setEnabled(two)
            if hasattr(self, "branch_combo"):
                self.branch_combo.setEnabled(two)
                self.branch_label.setEnabled(two)
            if hasattr(self, "hold_t1"):
                self.hold_t1.setEnabled(not two)
                self.hold_value.setEnabled(not two)
            if two:
                widest = max(self.n_shells.value(), self.n_shells_b.value(),
                             self.n_hybrid.value())
                found = TB.shells(vectors, widest,
                                  symmetry=self.lattice_symmetry())
            head = ("Two bands, hybridised: band a uses t1..t"
                    f"{self.n_shells.value()}, band b t1..t"
                    f"{self.n_shells_b.value()}, the coupling v0"
                    + (f"..v{self.n_hybrid.value()}" if self.n_hybrid.value()
                       else "") + "." if two else "One band.")
            self.shell_label.setText(
                f"{head} Shells (orbits under {source}): " + ";  ".join(
                    f"t{i + 1}: {len(v)} neighbours at {d:.4g} Å "
                    f"{TB.shell_label(vectors, v)}"
                    for i, (d, v) in enumerate(found)))
        if hasattr(self, "stepper"):
            self.stepper.refresh()

    # ==================================================================
    # Step 2: band points
    # ==================================================================
    def _step_points(self):
        page = QWidget()
        row = QHBoxLayout(page)
        left = QVBoxLayout()
        self.view = plain_image_view()
        self.view.setMinimumSize(420, 360)
        self.view.scene.sigMouseClicked.connect(self._on_click)
        left.addWidget(self.view, 1)
        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Energy"))
        self.energy_slider = QSlider(Qt.Horizontal)
        self.energy_slider.valueChanged.connect(self._show_plane)
        slider_row.addWidget(self.energy_slider, 1)
        self.energy_label = QLabel("")
        slider_row.addWidget(self.energy_label)
        left.addLayout(slider_row)
        row.addLayout(left, 3)
        self.points_scatter = pg.ScatterPlotItem(
            size=5, pen=None, brush=pg.mkBrush(255, 210, 0, 230))
        self.other_scatter = pg.ScatterPlotItem(
            size=3, pen=None, brush=pg.mkBrush(120, 120, 120, 150))
        self.view.view.addItem(self.other_scatter)
        self.view.view.addItem(self.points_scatter)

        right = QVBoxLayout()
        trace = QGroupBox("Trace with ridges")
        tf = QFormLayout(trace)
        self.ridge_sigma = _spin(0.02, 1e-4, 1.0, 4, " Å⁻¹")
        self.ridge_sigma.setToolTip("Smoothing width along both momentum "
                                    "axes: about the band's width.")
        tf.addRow("Smoothing", self.ridge_sigma)
        self.ridge_threshold = _spin(15.0, 0.0, 100.0, 1, " %")
        tf.addRow("Threshold", self.ridge_threshold)
        self.trace_button = QPushButton("Trace this energy")
        self.trace_button.setToolTip("Ridge points of the plane shown, added "
                                     "at its energy.")
        self.trace_button.clicked.connect(self.trace_plane)
        tf.addRow(self.trace_button)
        right.addWidget(trace)
        self.click_box = QCheckBox("Click on the plane to add points")
        right.addWidget(self.click_box)
        branch_row = QHBoxLayout()
        self.branch_label = QLabel("New points on:")
        branch_row.addWidget(self.branch_label)
        self.branch_combo = QComboBox()
        self.branch_combo.addItem("either band (decided by the fit)", TB.AUTO)
        self.branch_combo.addItem("the lower band", TB.LOWER)
        self.branch_combo.addItem("the upper band", TB.UPPER)
        self.branch_combo.setToolTip(
            "Two bands: which band the next traced or clicked points belong "
            "to. 'Either' lets the fit put each point on the nearer band; "
            "labelling one contour of each is usually enough.")
        branch_row.addWidget(self.branch_combo, 1)
        right.addLayout(branch_row)
        self.file_button = QPushButton("Read points from a file...")
        self.file_button.setToolTip("CSV with kx, ky[, kz] and energy "
                                    "columns -- the ridge-detection window's "
                                    "file is read as it is.")
        self.file_button.clicked.connect(lambda: self.read_file())
        right.addWidget(self.file_button)
        right.addWidget(QLabel("Points, by energy:"))
        self.energy_list = QListWidget()
        right.addWidget(self.energy_list, 1)
        buttons = QHBoxLayout()
        remove = QPushButton("Remove energy")
        remove.clicked.connect(self.remove_selected_energy)
        clear = QPushButton("Clear all")
        clear.clicked.connect(self.clear_points)
        buttons.addWidget(remove)
        buttons.addWidget(clear)
        right.addLayout(buttons)
        row.addLayout(right, 2)

        if self.data is None:
            for widget in (self.view, self.energy_slider, trace, self.click_box):
                widget.setEnabled(False)
        else:
            energy = self._energy_axis()
            self.energy_slider.setRange(0, energy.size - 1)
            self.energy_slider.setValue(self._nearest_energy(0.0))
            x, y = self._plane_axes()
            step = float(np.median(np.abs(np.diff(x)))) if x.size > 1 else 0.01
            self.ridge_sigma.setValue(2 * step)

        text = ("<b>One band:</b> give the fit points on <b>that band "
                "only</b> -- points on a second band are misfit (a few are "
                "set aside as outliers; many spoil the fit). <b>Two "
                "bands:</b> trace both, leaving <i>New points on</i> at "
                "<i>either band</i>, and click a few points of each band with "
                "it set to <i>lower</i> or <i>upper</i> (blue / pink) so the "
                "fit knows which is which. On a map: move "
                "to an energy (E_F first) and press <b>Trace this energy</b> "
                "-- ridge detection puts points along the contour -- or tick "
                "<b>Click</b> and click on it. <b>Do two or three energies</b> "
                "if you can: points at one energy fix the band's shape but "
                "not its energy scale, and the fit then has to hold the "
                "first hopping fixed. Points can also come from a file. "
                "Remove an energy that traced something other than the band.")
        return Step("Band points", text, page, ready=self._points_problem,
                    enter=self._show_plane)

    # -- the map ---------------------------------------------------------
    def _energy_axis(self):
        return np.asarray(self.data.scan.z, dtype=float)

    def _plane_axes(self):
        return (np.asarray(self.data.scan.x, dtype=float),
                np.asarray(self.data.scan.k, dtype=float))

    def _nearest_energy(self, value):
        return int(np.argmin(np.abs(self._energy_axis() - value)))

    def current_energy(self):
        return float(self._energy_axis()[self.energy_slider.value()])

    def _plane(self):
        return np.asarray(self.data.scan.value[:, :, self.energy_slider.value()],
                          dtype=float)

    def _show_plane(self, *_):
        if self.data is None:
            return
        x, y = self._plane_axes()
        first = self.view.image is None
        show_frame(self.view, self._plane(), x, y, auto_levels=True)
        apply_colormap(self.view, self.colormap, False)
        labels = dict(self.data.scan.labels or {})
        self.view.view.setLabel("bottom", labels.get("x", "kx"))
        self.view.view.setLabel("left", labels.get("k", "ky"))
        if first:
            fit_frame_view(self.view, x, y)
        self.energy_label.setText(f"{self.current_energy():.4f} eV")
        self._draw_points()
        self._draw_model()

    def _map_k(self, u, v):
        """A point of the plane (its two axes) as a k vector of the
        lattice's dimension."""
        three = self.mode_3d.isChecked()
        if self.data is not None and self.data.kind == "kz_map_k":
            phi = np.deg2rad(self.kpar_angle.value())
            kz, kpar = np.asarray(u, float), np.asarray(v, float)
            kx, ky = kpar * np.cos(phi), kpar * np.sin(phi)
            return np.column_stack([kx, ky, kz] if three else [kx, ky])
        u, v = np.asarray(u, float), np.asarray(v, float)
        if three:
            return np.column_stack([u, v, np.full(u.size, self.kz_plane.value())])
        return np.column_stack([u, v])

    def _plane_of(self, k):
        """Inverse of :meth:`_map_k`, for drawing points on the plane."""
        k = np.atleast_2d(k)
        if self.data is not None and self.data.kind == "kz_map_k":
            phi = np.deg2rad(self.kpar_angle.value())
            kpar = k[:, 0] * np.cos(phi) + k[:, 1] * np.sin(phi)
            kz = k[:, 2] if k.shape[1] > 2 else np.zeros(len(k))
            return kz, kpar
        return k[:, 0], k[:, 1]

    def current_branch(self) -> int:
        if not self.two_bands.isChecked():
            return TB.AUTO
        return int(self.branch_combo.currentData())

    def add_points(self, k, energy, branch=None):
        k = np.atleast_2d(np.asarray(k, dtype=float))
        if not len(k):
            return
        branch = self.current_branch() if branch is None else branch
        dim = 3 if self.mode_3d.isChecked() else 2
        if k.shape[1] < dim:
            k = np.column_stack([k, np.full(len(k), self.kz_plane.value())])
        k = k[:, :dim]
        if self.k_points.shape[1] != dim:
            self.k_points = np.zeros((0, dim))
        self.k_points = np.vstack([self.k_points, k])
        self.energies = np.concatenate([self.energies,
                                        np.broadcast_to(energy, len(k))])
        self.branches = np.concatenate([
            self.branches, np.broadcast_to(np.asarray(branch, dtype=int),
                                           len(k))]).astype(int)
        self._refresh_list()

    def trace_plane(self):
        x, y = self._plane_axes()
        sigma = self.ridge_sigma.value()
        result = RD.ridges(self._plane(), x, y, sigma, sigma,
                           threshold=self.ridge_threshold.value() / 100.0)
        energy = self.current_energy()
        self._drop_energy(energy, self.current_branch()
                          if self.two_bands.isChecked() else None)
        if len(result.points):
            self.add_points(self._map_k(result.points[:, 0], result.points[:, 1]),
                            energy)
        self._draw_points()
        return len(result.points)

    def _on_click(self, event):
        if not self.click_box.isChecked() or event.button() != Qt.LeftButton:
            return
        box = self.view.view.vb
        if not box.sceneBoundingRect().contains(event.scenePos()):
            return
        point = box.mapSceneToView(event.scenePos())
        self.add_points(self._map_k([point.x()], [point.y()]), self.current_energy())
        self._draw_points()

    def read_file(self, path=None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Band points", "", "Tables (*.csv *.txt *.dat);;All files (*)")
            if not path:
                return None
        try:
            k, energies, branches = TB.read_points(path, with_branch=True)
        except (OSError, ValueError) as exc:
            self.stepper.missing.setText(f"Could not read the points: {exc}")
            return None
        if k.shape[1] == 3 and not self.mode_3d.isChecked():
            k = k[:, :2]
        if branches.any():
            self.two_bands.setChecked(True)
        for value in np.unique(energies):
            here = energies == value
            for side in np.unique(branches[here]):
                chosen = here & (branches == side)
                self.add_points(k[chosen], value, int(side))
        self._draw_points()
        return len(energies)

    def _drop_energy(self, energy, branch=None):
        """Forget the points at ``energy`` (only those on ``branch``, if
        given: tracing the upper band keeps the lower's points)."""
        keep = np.abs(self.energies - energy) > 1e-9
        if branch is not None:
            keep |= self.branches != branch
        self.k_points, self.energies = self.k_points[keep], self.energies[keep]
        self.branches = self.branches[keep]
        self._refresh_list()

    def remove_selected_energy(self):
        item = self.energy_list.currentItem()
        if item is None:
            return
        self._drop_energy(float(item.data(Qt.UserRole)))
        self._draw_points()

    def clear_points(self):
        self.k_points, self.energies = np.zeros((0, 2)), np.zeros(0)
        self.branches = np.zeros(0, dtype=int)
        self._refresh_list()
        self._draw_points()

    def _refresh_list(self):
        self.energy_list.clear()
        for value in np.unique(self.energies):
            here = np.abs(self.energies - value) < 1e-9
            count = int(np.sum(here))
            text = f"E = {value:+.4f} eV: {count} points"
            lower = int(np.sum(here & (self.branches == TB.LOWER)))
            upper = int(np.sum(here & (self.branches == TB.UPPER)))
            if lower or upper:
                text += f" ({lower} lower, {upper} upper)"
            self.energy_list.addItem(text)
            self.energy_list.item(self.energy_list.count() - 1).setData(
                Qt.UserRole, float(value))
        if hasattr(self, "stepper"):
            self.stepper.refresh()

    def _draw_points(self):
        if self.data is None or not len(self.energies):
            self.points_scatter.setData([], [])
            self.other_scatter.setData([], [])
            return
        here = np.abs(self.energies - self.current_energy()) < 1e-9
        u, v = self._plane_of(self.k_points)
        colours = {TB.AUTO: (255, 210, 0, 230), TB.LOWER: (40, 200, 255, 230),
                   TB.UPPER: (255, 80, 200, 230)}
        brushes = [pg.mkBrush(*colours.get(int(b), colours[TB.AUTO]))
                   for b in self.branches[here]]
        self.points_scatter.setData(u[here], v[here], brush=brushes)
        self.other_scatter.setData(u[~here], v[~here])

    def _parameter_count(self) -> int:
        if self.two_bands.isChecked():
            return (3 + self.n_shells.value() + self.n_shells_b.value()
                    + self.n_hybrid.value())
        return self.n_shells.value() + 1

    def _points_problem(self):
        need = self._parameter_count() + 1
        if len(self.energies) < need:
            return (f"{len(self.energies)} points; at least {need} are needed "
                    f"for {self._parameter_count()} parameters.")
        if self.two_bands.isChecked() and len(np.unique(self.energies)) < 2:
            return ("Two bands need points at two or more energies: one "
                    "contour fixes no energy scale.")
        return ""

    # ==================================================================
    # Step 3: fit
    # ==================================================================
    def _step_fit(self):
        page = QWidget()
        column = QVBoxLayout(page)
        options = QHBoxLayout()
        self.hold_t1 = QCheckBox("Hold t1 at")
        self.hold_value = _spin(-1.0, -50.0, 50.0, 4, " eV")
        self.hold_t1.setToolTip(
            "Needed when every point has the same energy (one contour): such "
            "points fix the band's shape, not its energy scale.")
        options.addWidget(self.hold_t1)
        options.addWidget(self.hold_value)
        self.fit_azimuth = QCheckBox("Refine the azimuth (±")
        self.azimuth_span = _spin(5.0, 0.5, 60.0, 1, "°)")
        options.addWidget(self.fit_azimuth)
        options.addWidget(self.azimuth_span)
        self.fit_button = QPushButton("Fit")
        self.fit_button.setStyleSheet("font-weight: bold;")
        self.fit_button.clicked.connect(self.run_fit)
        options.addWidget(self.fit_button)
        options.addStretch(1)
        column.addLayout(options)
        self.result_table = QTableWidget(0, 3)
        self.result_table.setHorizontalHeaderLabels(["Parameter", "Value (eV)",
                                                     "±"])
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        column.addWidget(self.result_table, 1)
        self.fit_label = QLabel("")
        self.fit_label.setWordWrap(True)
        column.addWidget(self.fit_label)
        text = ("Press <b>Fit</b>. The hoppings come with their standard "
                "errors, and the model's contours are drawn on the plane in "
                "step 2 (go back to look -- red, at the energy shown). With "
                "points at a single energy, <b>hold t1</b>: the result is "
                "then the band's shape, in units of t1. <b>Refine the "
                "azimuth</b> when the lattice's orientation on the map is "
                "known only roughly. An orange note means the points cannot "
                "tell the shells apart: use fewer. <b>Two bands</b>: the fit "
                "is nonlinear, started from one-band fits of the two groups "
                "of points; the table gives band a, band b and the coupling "
                "(v0, v1, ...), both bands are drawn (red, orange), and the "
                "smallest gap between them is given -- 2|V| where the bare "
                "bands cross.")
        return Step("Fit", text, page, ready=lambda: "" if self.model is not None
                    else "Press Fit.", enter=self._enter_fit)

    def _enter_fit(self):
        if self.two_bands.isChecked():
            return
        single = len(np.unique(self.energies)) <= 1
        if single and not self.hold_t1.isChecked():
            self.hold_t1.setChecked(True)

    def run_fit(self):
        options = {}
        two = self.two_bands.isChecked()
        fitter = TB.fit_two_band if two else TB.fit
        if two:
            options.update(n_shells_b=self.n_shells_b.value(),
                           n_hybrid=self.n_hybrid.value(),
                           branch=self.branches)
        elif self.hold_t1.isChecked():
            options["t1"] = self.hold_value.value()
        try:
            options["symmetry"] = self.lattice_symmetry()
        except ValueError as exc:
            self.fit_label.setText(f"<b>Could not fit:</b> {exc}")
            return None
        from arpes_viewer.ui.common.jobs import busy_work

        try:
            if self.fit_azimuth.isChecked() and self.k_points.shape[1] >= 2:
                base = TB.rotate(self.lattice_vectors(), -self.azimuth.value())
                # a fit at every azimuth of the span: the slow one
                model = busy_work(self, "Fitting, the azimuth refined",
                                  TB.fit_azimuth, self.k_points, self.energies,
                                  base, self.n_shells.value(),
                                  around=self.azimuth.value(),
                                  span=self.azimuth_span.value(),
                                  # each two-band fit is nonlinear: fewer
                                  steps=21 if two else 81,
                                  fitter=fitter, **options)
                self.azimuth.blockSignals(True)
                self.azimuth.setValue(model.azimuth_deg)
                self.azimuth.blockSignals(False)
            else:
                model = busy_work(self, "Fitting", fitter, self.k_points,
                                  self.energies, self.lattice_vectors(),
                                  self.n_shells.value(), **options)
                model.azimuth_deg = self.azimuth.value()
        except (ValueError, np.linalg.LinAlgError) as exc:
            self.fit_label.setText(f"<b>Could not fit:</b> {exc}")
            return None
        self.model = model
        rows = model.table()
        self.result_table.setRowCount(len(rows))
        for i, (name, value, error, _unit) in enumerate(rows):
            self.result_table.setItem(i, 0, QTableWidgetItem(name))
            self.result_table.setItem(i, 1, QTableWidgetItem(f"{value:.6g}"))
            held = not np.isfinite(error)
            self.result_table.setItem(i, 2, QTableWidgetItem(
                "held" if held else f"{error:.2g}"))
        text = (f"rms misfit {model.rms * 1000:.2f} meV over {model.n_points} "
                f"points; azimuth {model.azimuth_deg:.2f}°.")
        if model.outliers:
            text += (f" {model.outliers} point(s) lay far off the band (a "
                     f"ridge traced on something else) and were given no "
                     f"weight.")
        if two:
            gap, where = model.gap(self._gap_points())
            text += (f" Two bands: the smallest gap between them is "
                     f"{gap * 1000:.1f} meV, at k = ("
                     + ", ".join(f"{v:.3f}" for v in where) + ") Å⁻¹; "
                     f"{int(np.sum(model.branch == TB.LOWER))} points on the "
                     f"lower band, {int(np.sum(model.branch == TB.UPPER))} on "
                     f"the upper.")
        elif model.shape_only or self.hold_t1.isChecked():
            text += " Energies are in units of the held t1 (shape only)."
        if model.warning:
            text += f"<br><span style='color:#b0602a'>{model.warning}</span>"
        self.fit_label.setText(text)
        self._draw_model()
        self.stepper.refresh()
        return model

    def _gap_points(self):
        """Where to look for the smallest gap: the plane's grid, or a grid
        around the points."""
        x, y, _energy = self._model_grid()
        return self._map_k(*[g.ravel() for g in np.meshgrid(x, y, indexing="ij")])

    def _draw_model(self):
        for item in self._isocurves:
            self.view.view.removeItem(item)
        self._isocurves = []
        if self.model is None or self.data is None:
            return
        x, y = self._plane_axes()
        k = self._map_k(*[g.ravel() for g in np.meshgrid(x, y, indexing="ij")])
        dx = (x[-1] - x[0]) / max(x.size - 1, 1)
        dy = (y[-1] - y[0]) / max(y.size - 1, 1)
        pens = ("#e0302a", "#f08a1c")
        for band, colour in zip(self.model.bands(k), pens):
            energy = band.reshape(x.size, y.size)
            curve = pg.IsocurveItem(data=energy.T, level=self.current_energy(),
                                    pen=pg.mkPen(colour, width=2))
            transform = QTransform()
            transform.translate(x[0], y[0])
            transform.scale(dx or 1.0, dy or 1.0)
            curve.setTransform(transform)
            self.view.view.addItem(curve)
            self._isocurves.append(curve)

    # ==================================================================
    # Step 4: use the model
    # ==================================================================
    def _step_use(self):
        page = QWidget()
        column = QVBoxLayout(page)
        form = QFormLayout()
        self.width_box = _spin(0.03, 1e-4, 2.0, 4, " eV")
        self.width_box.setToolTip("Lorentzian half-width given to the model's "
                                  "band, so it can be looked at like data.")
        form.addRow("Band width (HWHM)", self.width_box)
        column.addLayout(form)
        buttons = QHBoxLayout()
        self.model_button = QPushButton("Model to list")
        self.model_button.setToolTip(
            "The model's spectral function A(k, E) on the map's own grid (or "
            "a grid around the points), as a new map: open it beside the "
            "data, or subtract the two.")
        self.model_button.clicked.connect(self.model_to_list)
        buttons.addWidget(self.model_button)
        save = QPushButton("Save parameters...")
        save.clicked.connect(lambda: self.save_parameters())
        buttons.addWidget(save)
        copy = QPushButton("Copy results")
        copy.clicked.connect(self.copy_results)
        buttons.addWidget(copy)
        buttons.addStretch(1)
        column.addLayout(buttons)
        self.use_label = QLabel("")
        self.use_label.setWordWrap(True)
        column.addWidget(self.use_label)
        column.addStretch(1)
        text = ("The fit as something to look at and keep. <b>Model to "
                "list</b> makes the model's band a map like the data -- each "
                "energy plane its constant-energy contour, broadened by the "
                "width set here -- so it opens in the same viewer and goes "
                "into the figure composer beside the measurement. "
                "<b>Save parameters</b> writes the lattice, the shells and "
                "the hoppings to a JSON file.")
        return Step("Use the model", text, page)

    def _model_grid(self):
        if self.data is not None:
            x, y = self._plane_axes()
            return x, y, self._energy_axis()
        k = self.k_points
        span = max(np.ptp(k[:, 0]), np.ptp(k[:, 1])) * 0.6 + 0.1
        cx, cy = k[:, 0].mean(), k[:, 1].mean()
        x = np.linspace(cx - span, cx + span, 201)
        y = np.linspace(cy - span, cy + span, 201)
        lo, hi = float(self.energies.min()), float(self.energies.max())
        pad = max(0.1, 0.2 * (hi - lo))
        return x, y, np.linspace(lo - pad, hi + pad, 121)

    def build_model_map(self):
        x, y, energy = self._model_grid()
        k = self._map_k(*[g.ravel() for g in np.meshgrid(x, y, indexing="ij")])
        width = self.width_box.value()
        values = np.zeros((x.size, y.size, energy.size))
        for band in self.model.bands(k):
            band = band.reshape(x.size, y.size)
            values += (width / np.pi) / ((energy[None, None, :]
                                          - band[:, :, None]) ** 2 + width ** 2)
        kind = self.data.kind if self.data is not None else "k_map"
        labels = (dict(self.data.scan.labels or {}) if self.data is not None
                  else {"x": "kx (Å⁻¹)", "k": "ky (Å⁻¹)",
                        "z": "E - E_F (eV)"})
        parameters = self.parameters()
        taken = set(self._existing())
        name, n = f"{self.name} TB model", 2
        while name in taken:
            name, n = f"{self.name} TB model {n}", n + 1
        return MemoryData(kind, (x, y, energy), values.astype(np.float32), labels,
                          source_label=name,
                          parameters={k: (json.dumps(v) if isinstance(v, (list, dict))
                                          else v) for k, v in parameters.items()},
                          prefix="tb",
                          source_path=getattr(self.data, "path", "") if self.data else "")

    def model_to_list(self):
        if self.model is None:
            return None
        self.result = self.build_model_map()
        self.datasetsCreated.emit([self.result])
        self.use_label.setText(f"Added {self.result.source_label} to the list.")
        return self.result

    def parameters(self) -> dict:
        m = self.model
        if isinstance(m, TB.TwoBandFit):
            return self._two_band_parameters(m)
        return {"model": "one band, one hopping per symmetry orbit",
                "lattice_vectors_A": m.vectors.tolist(),
                "space_group": (self.space_group.value()
                                if self.mode_3d.isChecked() else None),
                "azimuth_deg": m.azimuth_deg,
                "shell_distances_A": [d for d, _ in m.shells],
                "neighbours": [len(v) for _, v in m.shells],
                "shell_vectors_lattice": [
                    TB.integer_coordinates(m.vectors, v).tolist()
                    for _, v in m.shells],
                "e0_eV": m.e0, "e0_err_eV": m.e0_err,
                "t_eV": m.t.tolist(), "t_err_eV": [float(e) for e in m.t_err],
                "rms_eV": m.rms, "points": m.n_points,
                "shape_only": bool(m.shape_only or self.hold_t1.isChecked()),
                "kz_plane_invA": self.kz_plane.value()
                if self.mode_3d.isChecked() else None}

    def _two_band_parameters(self, m) -> dict:
        out = {"model": "two bands, hybridised: E = (ea+eb)/2 +- "
                        "sqrt(((ea-eb)/2)^2 + V^2), one hopping per "
                        "symmetry orbit",
               "lattice_vectors_A": m.vectors.tolist(),
               "space_group": (self.space_group.value()
                               if self.mode_3d.isChecked() else None),
               "azimuth_deg": m.azimuth_deg,
               "rms_eV": m.rms, "points": m.n_points,
               "points_lower": int(np.sum(m.branch == TB.LOWER)),
               "points_upper": int(np.sum(m.branch == TB.UPPER)),
               "kz_plane_invA": self.kz_plane.value()
               if self.mode_3d.isChecked() else None}
        for prefix, shells, values, errors in m.groups():
            key = {"a": "band_a", "b": "band_b", "v": "coupling"}[prefix]
            out[key] = {
                "onsite_eV" if prefix != "v" else "v0_eV": float(values[0]),
                "onsite_err_eV" if prefix != "v" else "v0_err_eV": float(errors[0]),
                "hoppings_eV": [float(v) for v in values[1:]],
                "hoppings_err_eV": [float(e) for e in errors[1:]],
                "shell_distances_A": [d for d, _ in shells],
                "shell_vectors_lattice": [
                    TB.integer_coordinates(m.vectors, v).tolist()
                    for _, v in shells]}
        gap, where = m.gap(self._gap_points())
        out["smallest_gap_eV"] = gap
        out["smallest_gap_at_invA"] = [float(v) for v in where]
        return out

    def save_parameters(self, path=None):
        if self.model is None:
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, "Tight-binding parameters", f"{self.name}_tb.json",
                "JSON (*.json)")
            if not path:
                return None
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.parameters(), handle, indent=2,
                      default=lambda v: None if v != v else v)
        self.use_label.setText(f"Wrote {path}.")
        return path

    def copy_results(self):
        if self.model is None:
            return ""
        lines = [f"{n}\t{v:.6g}\t{e:.2g}" for n, v, e, _u in self.model.table()]
        lines.append(f"rms\t{self.model.rms:.6g}")
        text = "\n".join(lines)
        QApplication.clipboard().setText(text)
        return text
