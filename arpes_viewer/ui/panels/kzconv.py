"""
ui/panels/kzconv.py
===================
The kz-to-momentum window: convert a photon-energy scan, and settle V0.

The conversion itself is arithmetic (:mod:`tools.momentum.kzconv`). What needs a
window is the inner potential, because the experiment does not measure it:
it is chosen so that the pattern the data shows repeats with the lattice's
own period. So the window is built around that choice --

* a preview of one energy slice, reconverted as the parameters change,
* the Brillouin-zone boundaries drawn over it, from the space group and
  lattice constants,
* V0 from where Γ is (the photon energy at which normal emission passes
  through it),
* a two-point measurement for reading a period straight off the picture
  and asking which lattice planes could produce it,
* and the measured plane in the 3-D zone.

Each preview is one energy slice, a few milliseconds, which is what lets the
inner potential be a thing you drag rather than a thing you re-run.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QFormLayout, QGroupBox,
                             QHBoxLayout, QLabel, QPushButton, QSlider,
                             QSpinBox, QTextEdit, QVBoxLayout,
                             QWidget)

from arpes_viewer.ui.common.screen import fits_screen
from arpes_viewer.tools.crystal import cleavage
from arpes_viewer.tools.momentum import kzconv
from arpes_viewer.tools.crystal.lattice import LatticeParams, validate_lattice_parameters
from arpes_viewer.tools.processing.process import Step, record_step
from arpes_viewer.ui.common import jobs as nxs_jobs
from arpes_viewer.tools.output import colormaps
from arpes_viewer.tools.runtime import remembered
from arpes_viewer.ui.viewers.widgets import (add_button, ButtonRow, LevelBar,
                                             MemoryData, scroll_strip,
                                             section_label)

__all__ = ["KzConversionDialog"]

#: How bent the Fermi edge may be across the analyser angle before the
#: conversion is worth warning about, in eV. A tenth of an electronvolt of
#: bend turns into a visible bend in k_z, and the conversion cannot tell it
#: from dispersion.
FLATNESS_WARNING_EV = 0.03


@fits_screen
class KzConversionDialog(QDialog):
    """Convert a kz map to momentum, choosing the inner potential."""

    datasetsCreated = pyqtSignal(list)

    def __init__(self, contour):
        super().__init__(contour)
        self.setWindowTitle("kz map -> momentum")
        self.setModal(False)
        self.resize(940, 820)
        self.contour = contour
        self._pick_points = []
        self._picking = False

        data = contour.data
        self.hv, self.angle, self.energy, _cube = data.angle_cube
        self.hv = np.asarray(self.hv, dtype=float)
        self.angle = np.asarray(self.angle, dtype=float)
        self.energy = np.asarray(self.energy, dtype=float)

        layout = QVBoxLayout(self)
        layout.addWidget(self._flatness_banner())

        body = QHBoxLayout()
        body.addWidget(self._settings_panel(), stretch=0)
        body.addWidget(self._preview_panel(), stretch=1)
        layout.addLayout(body, stretch=1)

        buttons = ButtonRow()
        self.convert_button = add_button(buttons,"Convert the whole cube",
                                                 QDialogButtonBox.AcceptRole)
        self.convert_button.clicked.connect(self.convert)
        add_button(buttons,"Close", QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # A kz map of the same size as one converted before is nearly always
        # the same crystal again (another polarisation): start from that
        # conversion's V0, geometry, grid and lattice.
        self.restored = remembered.recall(self.REMEMBERED, self._shape())
        if self.restored:
            self.restore(self.restored)
        else:
            self.default_grid()
        self.refresh()

    # -- remembered between scans of one size ------------------------------
    #: the key the settings are remembered under (tools.runtime.remembered)
    REMEMBERED = "kz_conversion"

    #: the boxes that carry over -- not the work function or the
    #: manipulator theta, which each file records for itself
    _CARRIED = ("inner_potential", "effective_mass", "angle_offset", "n_kz",
                "n_kpar", "space_group", "lat_a", "lat_b", "lat_c",
                "lat_alpha", "lat_beta", "lat_gamma", "kpar_rotation")

    def _shape(self):
        return (self.hv.size, self.angle.size, self.energy.size)

    def remembered_settings(self) -> dict:
        settings = {name: getattr(self, name).value() for name in self._CARRIED}
        settings["surface_hkl"] = list(self.surface_hkl())
        return settings

    def restore(self, settings: dict):
        # The space group first: it fixes some of the cell, and the cell
        # decides which surface normals are on offer.
        for name in self._CARRIED:
            if name in settings:
                box = getattr(self, name)
                box.setValue(type(box.value())(settings[name]))
        wanted = settings.get("surface_hkl")
        if wanted is not None:
            for index in range(self.normal_index.count()):
                data = self.normal_index.itemData(index)
                if data is not None and _same_direction(data[0], wanted):
                    self.normal_index.setCurrentIndex(index)
                    break

    # -- is the Fermi surface flat enough? ---------------------------------
    def _flatness_banner(self) -> QLabel:
        """Say so, up front, if the Fermi edge still bends across the slit.

        Not a refusal: there are reasons to convert an uncorrected cube, and
        a scan taken well away from E_F has no edge to flatten. But the
        conversion reads the energy axis literally, and a bend it inherits
        is a bend in k_z that looks exactly like dispersion -- which is the
        one artefact nobody spots afterwards.
        """
        banner = QLabel()
        banner.setWordWrap(True)
        try:
            cube = np.asarray(self.contour.full_cube(), dtype=float)
            spread, _positions, _angles = kzconv.edge_flatness(
                cube, self.angle, self.energy)
        except Exception:                                   # noqa: BLE001
            banner.setVisible(False)
            return banner
        if spread > FLATNESS_WARNING_EV:
            banner.setStyleSheet(
                "QLabel { background: #fff3cd; color: #664d03; padding: 8px; "
                "border: 1px solid #ffe69c; border-radius: 4px; }")
            banner.setText(
                f"<b>The Fermi edge still bends by {spread:.3f} eV across the "
                f"analyser angle.</b> Straighten it first -- the tool panel's "
                f"Fermi surface correction (Basic) -- or that bend is "
                f"converted into k_z and comes out looking like dispersion. "
                f"Converting anyway is allowed; this is a reminder, not a "
                f"refusal.")
        else:
            banner.setStyleSheet(
                "QLabel { background: #e7f5e9; color: #14532d; padding: 8px; "
                "border: 1px solid #b7e0c0; border-radius: 4px; }")
            banner.setText(
                f"The Fermi edge is flat across the analyser angle to "
                f"{spread:.3f} eV. Good to convert.")
        return banner

    # -- the settings ------------------------------------------------------
    @staticmethod
    def _row(*items):
        """Several inputs on one line of a form: labels (str) and widgets."""
        row = QWidget()
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        for item in items:
            if isinstance(item, str):
                box.addWidget(QLabel(item))
            else:
                box.addWidget(item, stretch=1)
        return row

    def _settings_panel(self) -> QWidget:
        holder = QWidget()
        holder.setMaximumWidth(380)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)

        physics = QGroupBox("Final state")
        form = QFormLayout(physics)
        form.setVerticalSpacing(4)
        self.inner_potential = self._spin(12.0, -30.0, 200.0, 0.5, " eV")
        self.inner_potential.setToolTip(
            "V0, the inner potential: how far the final-state band bottom "
            "sits below the vacuum level. Not measured by the experiment -- "
            "chosen so the k_z pattern repeats with the lattice period, or "
            "from where Γ is (Γ at hν → Set V0).")
        # V0 from where Γ is: a kz map is usually taken so that one photon
        # energy passes through Γ at normal emission, and that is enough to
        # fix V0 once the zone order is chosen.
        self.gamma_hv = self._spin(float(np.median(self.hv)),
                                   float(self.hv.min()), float(self.hv.max()),
                                   0.5, " eV")
        self.gamma_hv.setToolTip(
            "The photon energy at which normal emission passes through Γ. "
            "“Set V0” then chooses the inner potential that puts Γ there "
            "(the zone order nearest the present V0; the order is shown).")
        self.gamma_button = QPushButton("Set V0")
        self.gamma_button.setToolTip(self.gamma_hv.toolTip())
        self.gamma_button.clicked.connect(self.set_v0_from_gamma)
        form.addRow("V0", self.inner_potential)
        form.addRow("Γ at hν", self._row(self.gamma_hv, self.gamma_button))
        self.gamma_note = QLabel("")
        self.gamma_note.setWordWrap(True)
        self.gamma_note.setVisible(False)
        form.addRow(self.gamma_note)

        self.effective_mass = self._spin(1.0, 0.05, 10.0, 0.05, "")
        self.effective_mass.setToolTip(
            "Final-state effective mass, in units of the free electron mass. "
            "1.0 is the free-electron final state; leave it there unless you "
            "have a reason.")
        self.work_function = self._spin(self._work_function_from_file(),
                                        0.0, 20.0, 0.05, " eV")
        self.work_function.setToolTip(
            "The analyser work function, used to turn a photon energy into a "
            "kinetic energy. Read from the file where the loader recorded "
            "one; change it if you know better.")
        form.addRow("m*", self._row(self.effective_mass, "W", self.work_function))

        # Optional: hv - E_kin(E_F) measured at each photon energy, after the
        # Fermi level has been flattened per photon energy.
        self.measured_phi = kzconv.measured_work_functions(
            self.contour.data.scan.info)
        self.calibrate_hv = QCheckBox("Calibrate hν from each fitted E_F")
        self.calibrate_hv.setChecked(False)
        if self.measured_phi is None:
            self.calibrate_hv.setEnabled(False)
            self.calibrate_hv.setToolTip(
                "Off unless the Fermi level was fitted per photon energy "
                "(kz map → Align E_F) on a scan whose loader recorded each "
                "spectrum's kinetic-energy window. Without it the single "
                "work function W is used for every photon energy.")
        else:
            phi = self.measured_phi
            self.calibrate_hv.setToolTip(
                "Use hν − E_kin(E_F) measured at each photon energy "
                f"({phi.min():.3f} to {phi.max():.3f} eV here) instead of "
                "the single work function. Corrects a monochromator whose "
                "hν is off, or an analyser work function unlike the table. "
                "Optional: the default is the single work function, with the "
                "Fermi level already flattened.")
        form.addRow(self.calibrate_hv)
        column.addWidget(physics)

        geometry = QGroupBox("Geometry")
        form = QFormLayout(geometry)
        form.setVerticalSpacing(4)
        self.angle_offset = self._spin(0.0, -90.0, 90.0, 0.1, "°")
        self.angle_offset.setToolTip(
            "Where normal emission sits on the analyser slit. Subtracted "
            "from the slit angle before anything else.")
        form.addRow("Normal emission at", self.angle_offset)

        # The manipulator theta, relative to normal emission. Off by
        # default: a kz map is normally taken with the slit through Γ, so
        # the polar angle to correct is zero whatever the motor reads --
        # the file records the motor's absolute position, which is not the
        # angle from normal emission and must not be used as one.
        self.theta_correct = QCheckBox("θ offset from Γ")
        self.theta_correct.setChecked(False)
        self.theta_correct.setToolTip(
            "Only if the slit was not through Γ: the manipulator's polar "
            "angle away from normal emission tilts the detector arc out of "
            "the plane holding the slit, which adds a second in-plane "
            "momentum component that has to come out of k_z.")
        self.theta_position = self._spin(0.0, -90.0, 90.0, 0.1, "°")
        self.theta_position.setEnabled(False)
        file_theta = self._theta_from_file()
        self.theta_position.setToolTip(
            "Theta relative to normal emission (theta − theta at Γ), not the "
            f"motor's absolute reading ({file_theta:g}° in this file).")
        form.addRow(self._row(self.theta_correct, self.theta_position))
        self.theta_correct.toggled.connect(self.theta_position.setEnabled)
        self.theta_correct.toggled.connect(self.refresh)
        column.addWidget(geometry)

        grid = QGroupBox("Output grid")
        form = QFormLayout(grid)
        form.setVerticalSpacing(4)
        self.n_kz = QSpinBox(); self.n_kz.setRange(16, 2048); self.n_kz.setValue(256)
        self.n_kpar = QSpinBox(); self.n_kpar.setRange(16, 2048); self.n_kpar.setValue(256)
        for box in (self.n_kz, self.n_kpar):
            box.setKeyboardTracking(False)
        self.grid_button = QPushButton("Match")
        self.grid_button.setToolTip(
            "Match the measurement: k// gets one point per analyser angle "
            "channel and k_z the number that makes its step the same "
            "(square pixels) -- the default for a new scan.")
        self.grid_button.clicked.connect(self.default_grid)
        form.addRow("Points k_z", self._row(self.n_kz, "k//", self.n_kpar,
                                             self.grid_button))
        # Which energy slice the preview shows: the slider beside the
        # preview drives this box, which keeps the exact value.
        self.preview_energy = self._spin(0.0, float(self.energy.min()),
                                          float(self.energy.max()), 0.01, " eV")
        self.preview_energy.setValue(float(np.clip(0.0, self.energy.min(),
                                                   self.energy.max())))
        self.preview_energy.setToolTip(
            "Which energy slice the preview shows (also the slider beside "
            "the preview). The Fermi level is usually where the k_z "
            "periodicity is clearest.")
        column.addWidget(grid)

        column.addWidget(self._lattice_group())
        column.addStretch(1)

        for box in (self.inner_potential, self.effective_mass,
                    self.work_function, self.angle_offset,
                    self.theta_position, self.preview_energy, self.n_kz,
                    self.n_kpar):
            box.valueChanged.connect(self.refresh)
        self.calibrate_hv.toggled.connect(self.refresh)
        return holder

    def _lattice_group(self) -> QGroupBox:
        group = QGroupBox("Lattice (for the zone lines and the period)")
        form = QFormLayout(group)
        form.setVerticalSpacing(4)
        self.space_group = QSpinBox()
        self.space_group.setRange(1, 230)
        self.space_group.setValue(194)
        self.space_group.setToolTip(
            "The space group, which fixes the centering -- and the centering "
            "decides the k_z period: a body-centred lattice repeats every "
            "4*pi/a along [001], not 2*pi/a.")
        form.addRow("Space group", self.space_group)
        self.lat_a = self._spin(3.2, 0.1, 100.0, 0.01, " Å")
        self.lat_b = self._spin(3.2, 0.1, 100.0, 0.01, " Å")
        self.lat_c = self._spin(6.0, 0.1, 100.0, 0.01, " Å")
        self.lat_alpha = self._spin(90.0, 1.0, 179.0, 0.5, "°")
        self.lat_beta = self._spin(90.0, 1.0, 179.0, 0.5, "°")
        self.lat_gamma = self._spin(120.0, 1.0, 179.0, 0.5, "°")
        for box in (self.lat_a, self.lat_b, self.lat_c, self.lat_alpha,
                    self.lat_beta, self.lat_gamma):
            box.setToolTip("Greyed out means the space group fixes this one.")
        for box in (self.lat_a, self.lat_b, self.lat_c):
            box.setDecimals(3)
        for box in (self.lat_alpha, self.lat_beta, self.lat_gamma):
            box.setDecimals(1)
        form.addRow("a, b, c", self._row(self.lat_a, self.lat_b, self.lat_c))
        form.addRow("α, β, γ", self._row(self.lat_alpha, self.lat_beta,
                                         self.lat_gamma))
        self.normal_index = QComboBox()
        self.normal_index.setToolTip(
            "Which planes the crystal cleaved along. It sets the k_z period "
            "the zone lines are drawn with. Measure it with the two-point "
            "tool if unsure.")
        form.addRow("Normal (hkl)", self.normal_index)

        # Which way the slit runs in the surface. The zone a k_z map cuts is
        # the plane holding the normal *and* this direction. It is given as
        # a turn about the normal from a reference axis -- the first of a*,
        # b*, c* not along the normal (a* for a (001) surface) -- since the
        # slit often runs along no named direction. The (hkl) boxes are kept
        # (at 0 0 0, the reference) but not shown.
        self.kpar_h, self.kpar_k, self.kpar_l = (self._miller(0) for _ in range(3))
        self.kpar_rotation = self._spin(0.0, -180.0, 180.0, 1.0, "°")
        self.kpar_rotation.setToolTip(
            "The direction k// runs along, as a turn about the surface "
            "normal from the first of a*, b*, c* that is not along it (a* "
            "for a (001) surface). Any angle: the slit need not run along a "
            "high-symmetry direction. Check it with the 3D BZ view.")
        form.addRow("Rotate k// by", self.kpar_rotation)

        self.zone_lines = QCheckBox("Zone lines")
        self.zone_lines.setChecked(True)
        self.zone_lines.setToolTip("Draw the zone boundaries on the preview.")
        self.plane_button = QPushButton("k_z plane in 3D BZ...")
        self.plane_button.setToolTip(
            "A turnable 3-D view of the Brillouin zone with the plane this "
            "map measures (the surface normal and the k// direction, "
            "through Γ) in it -- the BZ overlap tool's own cut-plane view. "
            "It follows the lattice, normal and rotation settings here.")
        self.plane_button.clicked.connect(self.open_plane_preview)
        form.addRow(self._row(self.zone_lines, self.plane_button))
        self.space_group.valueChanged.connect(self._apply_constraints)
        self.lat_a.valueChanged.connect(self._sync_mirrored_lengths)
        for widget in (self.space_group, self.lat_a, self.lat_b, self.lat_c,
                       self.lat_alpha, self.lat_beta, self.lat_gamma):
            widget.valueChanged.connect(self._lattice_changed)
        for widget in (self.kpar_h, self.kpar_k, self.kpar_l,
                       self.kpar_rotation):
            widget.valueChanged.connect(self.refresh)
        self.normal_index.currentIndexChanged.connect(self.refresh)
        self.zone_lines.toggled.connect(self.refresh)
        self._apply_constraints()
        self._lattice_changed()
        return group

    @staticmethod
    def _miller(value):
        box = QSpinBox()
        box.setRange(-20, 20)
        box.setValue(value)
        box.setKeyboardTracking(False)
        return box

    def _apply_constraints(self, *_):
        """Disable and drive the cell parameters the space group fixes.

        The same rule as the Brillouin-zone dialog's: a hexagonal group
        has gamma = 120 whether or not anyone typed it, and a cell that
        contradicts its own space group builds the wrong reciprocal lattice
        -- every period but the one along c comes out wrong.
        """
        from arpes_viewer.tools.crystal.lattice import free_parameters
        try:
            constraints = free_parameters(int(self.space_group.value()))
        except Exception:                                   # noqa: BLE001
            return
        self._mirrors = dict(constraints.mirrors)
        lengths = {"a": self.lat_a, "b": self.lat_b, "c": self.lat_c}
        for name, box in lengths.items():
            box.setEnabled(name not in constraints.mirrors)
        angles = {"alpha": self.lat_alpha, "beta": self.lat_beta,
                  "gamma": self.lat_gamma}
        for name, box in angles.items():
            fixed = constraints.fixed_angles.get(name)
            box.setEnabled(fixed is None)
            if fixed is not None:
                box.blockSignals(True)
                box.setValue(float(fixed))
                box.blockSignals(False)
        self._sync_mirrored_lengths()

    def _sync_mirrored_lengths(self, *_):
        lengths = {"a": self.lat_a, "b": self.lat_b, "c": self.lat_c}
        for target, source in getattr(self, "_mirrors", {}).items():
            box = lengths[target]
            box.blockSignals(True)
            box.setValue(lengths[source].value())
            box.blockSignals(False)

    @staticmethod
    def _spin(value, low, high, step, suffix):
        box = QDoubleSpinBox()
        box.setRange(low, high)
        box.setDecimals(3)
        box.setSingleStep(step)
        box.setValue(value)
        box.setSuffix(suffix)
        box.setKeyboardTracking(False)
        return box

    # -- what the file already knows ---------------------------------------
    def _work_function_from_file(self) -> float:
        info = self.contour.data.scan.info or {}
        for key in ("cassiopee.work_function_eV", "work_function_eV",
                    "analyser_work_function_eV"):
            value = info.get(key)
            if isinstance(value, (int, float)) and np.isfinite(value):
                return float(value)
            if isinstance(value, np.ndarray) and value.size:
                return float(np.nanmean(value))
        return 4.5

    def _theta_from_file(self) -> float:
        info = self.contour.data.scan.info or {}
        value = info.get("cassiopee.sample_theta_deg")
        if isinstance(value, (int, float)) and np.isfinite(value):
            return float(value)
        return 0.0

    # -- the preview -------------------------------------------------------
    def _preview_panel(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)

        # The colour controls of the data viewers: colour map and Flip, then
        # the level bar (levels, Clip, percentages, gamma) above the image.
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(section_label("Colormap"))
        self.colormap_combo = QComboBox()
        names = list(colormaps.COLORMAP_NAMES)
        current = str(self.contour.colormap)
        if current not in names:
            names.insert(0, current)
        self.colormap_combo.addItems(names)
        self.colormap_combo.setCurrentText(current)
        self.flip_cb = QCheckBox("Flip")
        self.flip_cb.setChecked(bool(self.contour.flip))
        bar.addWidget(self.colormap_combo)
        bar.addWidget(self.flip_cb)
        bar.addStretch(1)
        column.addLayout(bar)
        self.level_bar = LevelBar(self)
        column.addWidget(scroll_strip(self.level_bar))
        self.colormap_combo.currentTextChanged.connect(self._apply_colormap)
        self.flip_cb.toggled.connect(self._apply_colormap)
        self.level_bar.levelsChanged.connect(lambda *_: self._show_plane())
        self.level_bar.gammaChanged.connect(lambda *_: self._show_plane())

        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "k_z (Å⁻¹)")
        self.plot.setLabel("left", "k// (Å⁻¹)")
        self.plot.setAspectLocked(True)
        self.image = pg.ImageItem()
        self.plot.addItem(self.image)
        self.zone_item = pg.PlotDataItem(pen=pg.mkPen("#e8e8e8", width=1,
                                                       style=Qt.DashLine))
        self.plot.addItem(self.zone_item)
        self.pick_item = pg.PlotDataItem(
            pen=pg.mkPen("#ff7f0e", width=2), symbol="o", symbolSize=9,
            symbolBrush="#ff7f0e")
        self.plot.addItem(self.pick_item)
        picture = QHBoxLayout()
        picture.addWidget(self.plot, stretch=1)
        # Beside the picture: the energy of the slice, a slider one drags
        # through the cube.
        energy_column = QVBoxLayout()
        self.energy_slider = QSlider(Qt.Vertical)
        self.energy_slider.setRange(0, max(self.energy.size - 1, 0))
        self.energy_slider.setValue(self._energy_index(self.preview_energy.value()))
        self.energy_slider.setToolTip("Energy of the slice shown. Drag "
                                      "through the cube.")
        self.energy_slider.valueChanged.connect(self._slider_moved)
        self.preview_energy.valueChanged.connect(self._energy_typed)
        energy_column.addWidget(QLabel("E"), alignment=Qt.AlignHCenter)
        energy_column.addWidget(self.energy_slider, stretch=1)
        self.preview_energy.setMaximumWidth(96)
        energy_column.addWidget(self.preview_energy)
        picture.addLayout(energy_column)
        column.addLayout(picture, stretch=1)

        row = QHBoxLayout()
        self.pick_button = QPushButton("Measure a k_z period...")
        self.pick_button.setCheckable(True)
        self.pick_button.setToolTip(
            "Click two points on the preview that are the same feature one "
            "zone apart. Their k_z separation is then matched against every "
            "lattice plane, which says which way the crystal cleaved.")
        self.pick_button.toggled.connect(self._toggle_picking)
        row.addWidget(self.pick_button)
        row.addStretch(1)
        column.addLayout(row)

        self.report = QTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumHeight(150)
        column.addWidget(self.report)
        return page

    # -- settings in one place ---------------------------------------------
    def settings(self) -> dict:
        """The conversion's parameters. ``work_function`` is one number, or
        one per photon energy when the hv calibration is on; the theta is
        the offset from normal emission, zero unless that is ticked."""
        calibrated = (self.calibrate_hv.isChecked()
                      and self.measured_phi is not None)
        return dict(
            inner_potential=float(self.inner_potential.value()),
            work_function=(np.asarray(self.measured_phi, dtype=float)
                           if calibrated else float(self.work_function.value())),
            effective_mass=float(self.effective_mass.value()),
            angle_offset=float(self.angle_offset.value()),
            theta_position=(float(self.theta_position.value())
                            if self.theta_correct.isChecked() else 0.0))

    # -- the grid, Γ, the slider ------------------------------------------
    def default_grid(self):
        """Points that keep the measurement's own detail (see
        :func:`tools.momentum.kzconv.default_grid`)."""
        try:
            n_kz, n_kpar = kzconv.default_grid(self.hv, self.angle,
                                               self.energy, **self.settings())
        except Exception:                                   # noqa: BLE001
            return None
        for box, value in ((self.n_kz, n_kz), (self.n_kpar, n_kpar)):
            box.blockSignals(True)
            box.setValue(int(value))
            box.blockSignals(False)
        self.refresh()
        return n_kz, n_kpar

    def set_v0_from_gamma(self):
        """The V0 that puts Γ at normal emission at the chosen hν."""
        settings = self.settings()
        phi = settings["work_function"]
        hv = float(self.gamma_hv.value())
        if np.ndim(phi):
            phi = float(np.interp(hv, self.hv, phi))
        try:
            v0, order = kzconv.inner_potential_for_gamma(
                hv, self.surface_period(), work_function=phi,
                effective_mass=settings["effective_mass"],
                near=float(self.inner_potential.value()))
        except Exception as exc:                            # noqa: BLE001
            self.gamma_note.setVisible(True)
            self.gamma_note.setText(f"<span style='color:#c00'>{exc}</span>")
            return None
        self.inner_potential.setValue(v0)
        self.gamma_note.setVisible(True)
        note = (f"Γ of zone order n = {order} at {hv:g} eV "
                f"(k_z = {order * self.surface_period():.3f} Å⁻¹).")
        if v0 < 0:
            note += (" <span style='color:#a60'>V0 is negative: unusual for "
                     "a free-electron final state -- check hν, the work "
                     "function and the surface normal.</span>")
        self.gamma_note.setText(note)
        return v0, order

    def _energy_index(self, value) -> int:
        return int(np.argmin(np.abs(self.energy - float(value))))

    def _slider_moved(self, index):
        value = float(self.energy[int(index)])
        if abs(self.preview_energy.value() - value) > 1e-9:
            self.preview_energy.setValue(value)

    def _energy_typed(self, value):
        index = self._energy_index(value)
        if self.energy_slider.value() != index:
            self.energy_slider.blockSignals(True)
            self.energy_slider.setValue(index)
            self.energy_slider.blockSignals(False)

    def lattice(self) -> LatticeParams:
        return LatticeParams(
            a=float(self.lat_a.value()), b=float(self.lat_b.value()),
            c=float(self.lat_c.value()), alpha=float(self.lat_alpha.value()),
            beta=float(self.lat_beta.value()),
            gamma=float(self.lat_gamma.value()),
            space_group=int(self.space_group.value()))

    def surface_hkl(self) -> tuple:
        """The chosen surface normal's Miller indices; (0 0 1) if none."""
        data = self.normal_index.currentData()
        if data is None:
            return (0, 0, 1)
        return tuple(int(v) for v in data[0])

    def kpar_hkl(self) -> tuple:
        return (int(self.kpar_h.value()), int(self.kpar_k.value()),
                int(self.kpar_l.value()))

    def surface_period(self) -> float:
        """The k_z period the chosen surface normal implies, A^-1."""
        data = self.normal_index.currentData()
        if data is None:
            return 2.0 * np.pi / float(self.lat_c.value())
        return float(data[1])

    def _lattice_changed(self, *_):
        """Refill the surface-normal choices for the current lattice."""
        # Kept by its indices, not its text: the text carries the period,
        # which changes with every lattice constant, so matching on it
        # dropped the user's choice back to the first entry on every edit.
        previous = self.normal_index.currentData()
        previous = tuple(previous[0]) if previous is not None else (0, 0, 1)
        self.normal_index.blockSignals(True)
        self.normal_index.clear()
        complaints = []
        try:
            params = self.lattice()
            # Returns warnings rather than raising: which of the two the
            # user got wrong -- the lengths or the space group -- is their
            # call, so it is reported beside the choices, not enforced.
            complaints = validate_lattice_parameters(params)
            for hkl, length, _direction in cleavage.reciprocal_lengths(
                    params, max_index=2)[:12]:
                name = "(" + " ".join(str(int(v)) for v in hkl) + ")"
                self.normal_index.addItem(
                    f"{name}   period {length:.4f} Å⁻¹", (hkl, length))
        except Exception as exc:                            # noqa: BLE001
            self.normal_index.addItem(f"lattice not usable: {exc}", None)
        for index in range(self.normal_index.count()):
            data = self.normal_index.itemData(index)
            if data is not None and _same_direction(data[0], previous):
                self.normal_index.setCurrentIndex(index)
                break
        self.normal_index.blockSignals(False)
        self._lattice_complaints = list(complaints)
        self.refresh()

    # -- drawing -----------------------------------------------------------
    def refresh(self, *_):
        """Reconvert the one preview slice and redraw.

        Does nothing until the preview exists: the settings panel is built
        first and its widgets are already connected to this, so the lattice
        box fires one refresh before there is anything to draw on.
        """
        if not hasattr(self, "image"):
            return
        try:
            kz_axis, kpar_axis, plane = self._preview_slice()
        except Exception as exc:                            # noqa: BLE001
            self.report.setHtml(f"<span style='color:#c00'>{exc}</span>")
            return
        self._preview = (kz_axis, kpar_axis, plane)
        finite = plane[np.isfinite(plane)]
        lo, hi = ((float(finite.min()), float(finite.max())) if finite.size
                  else (0.0, 1.0))
        first = not getattr(self, "_levels_set", False)
        user = None if first else self.level_bar.levels()
        keep = (user is not None
                and not self.level_bar.spans_full_range(*user))
        self.level_bar.set_data_range(lo, hi, keep_levels=keep)
        self.level_bar.set_histogram(finite)
        if first:
            self._levels_set = True
            self._apply_colormap()
        self._show_plane()
        self.image.setRect(pg.QtCore.QRectF(
            kz_axis[0], kpar_axis[0],
            kz_axis[-1] - kz_axis[0], kpar_axis[-1] - kpar_axis[0]))
        self._draw_zone_lines(kz_axis, kpar_axis)
        self._write_report(kz_axis, kpar_axis, plane)
        preview = getattr(self, "_plane_preview", None)
        if preview is not None and preview.isVisible():
            preview.refresh()

    def _show_plane(self):
        """The preview slice in the colour window, with the gamma applied
        inside it -- as the data viewers draw an image."""
        preview = getattr(self, "_preview", None)
        if preview is None:
            return
        plane = preview[2]
        lo, hi = self.level_bar.levels()
        if not hi > lo:
            hi = lo + 1.0
        with np.errstate(invalid="ignore"):
            norm = np.clip((plane - lo) / (hi - lo), 0.0, 1.0)
        gamma = self.level_bar.gamma()
        if gamma != 1.0:
            norm = norm ** gamma
        # The plane is (k_z, k//); the program draws images row-major
        # (pg imageAxisOrder="row-major": rows go up the picture), so it is
        # handed over transposed -- k_z across, k// up, as the axes and the
        # zone lines say.
        self.image.setImage(np.ascontiguousarray(norm.T), autoLevels=False,
                            levels=(0.0, 1.0))

    def _apply_colormap(self, *_):
        """The contour's own colormap on the preview.

        ``ui.viewers.widgets.apply_colormap`` drives a ``pg.ImageView``; this is a
        bare ``ImageItem``, whose colour table is set directly. It is the
        same lookup table either way, so the preview and the window that
        opened it match.
        """
        name = (self.colormap_combo.currentText()
                if hasattr(self, "colormap_combo") else self.contour.colormap)
        flip = (self.flip_cb.isChecked() if hasattr(self, "flip_cb")
                else self.contour.flip)
        try:
            lut = np.asarray(colormaps.get_lut(name, flip=flip))
            self.image.setLookupTable(lut)
        except Exception:                                   # noqa: BLE001
            pass        # a preview in the default colours is no disaster

    def _preview_slice(self):
        index = int(np.argmin(np.abs(self.energy
                                     - float(self.preview_energy.value()))))
        # Only the one plane: this runs on every change of every box, and
        # reading (and converting to float) the whole cube for it made each
        # keystroke cost a full read of the map.
        plane = np.asarray(self.contour.slab((slice(None), slice(None), index)),
                           dtype=float)
        one = np.asarray([float(self.energy[index])])
        kz_axis, kpar_axis, _e, out = kzconv.to_kz_cube(
            self.hv, self.angle, one, plane[:, :, None],
            n_kz=int(self.n_kz.value()), n_kpar=int(self.n_kpar.value()),
            **self.settings())
        return kz_axis, kpar_axis, out[:, :, 0]

    def _draw_zone_lines(self, kz_axis, kpar_axis):
        """The Brillouin zone as this map cuts it.

        A k_z map is a plane through k-space holding the surface normal and
        the slit direction, so what it shows of the zone is that plane's
        cut through every copy of it -- for a (001) surface of a simple
        lattice a row of rectangles, but for anything else (a centred
        lattice, a (110) or (111) surface) hexagons and rhombi whose
        boundaries are neither perpendicular to k_z nor at multiples of the
        period. Drawn as one polyline with gaps.
        """
        self._zone_error = None
        if not self.zone_lines.isChecked():
            self.zone_item.setData([], [])
            return
        try:
            polygons = self.zone_polygons(kz_axis, kpar_axis)
        except Exception as exc:                            # noqa: BLE001
            self._zone_error = str(exc)
            self.zone_item.setData([], [])
            return
        # Each edge once: neighbouring zones share their edges, and a
        # dashed line drawn twice comes out solid.
        from arpes_viewer.tools.crystal.bz2d import unique_edges
        xs, ys = [], []
        for (x0, y0), (x1, y1) in unique_edges(polygons):
            xs += [x0, x1, np.nan]
            ys += [y0, y1, np.nan]
        self.zone_item.setData(np.array(xs), np.array(ys), connect="finite")

    def zone_polygons(self, kz_axis, kpar_axis):
        """``[(k_z, k_par), ...]`` polygons of the zone over these axes."""
        from arpes_viewer.tools.crystal.bz3d import kz_frame, kz_zone_cuts
        zone, b = self._zone()
        frame = kz_frame(self.lattice(), self.surface_hkl(), self.kpar_hkl(),
                         float(self.kpar_rotation.value()))
        return kz_zone_cuts(zone, b, frame,
                            (float(np.min(kz_axis)), float(np.max(kz_axis))),
                            (float(np.min(kpar_axis)), float(np.max(kpar_axis))))

    def _zone(self):
        """The (conventional) first zone and its primitive reciprocal
        vectors, cached on the lattice -- the preview redraws on every
        change of V0, which leaves the zone alone."""
        from arpes_viewer.tools.crystal.lattice import primitive_vectors, reciprocal_vectors
        from arpes_viewer.tools.crystal.bz3d import wigner_seitz_cell
        params = self.lattice()
        key = (params.a, params.b, params.c, params.alpha, params.beta,
               params.gamma, params.space_group)
        cached = getattr(self, "_zone_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1], cached[2]
        b = reciprocal_vectors(primitive_vectors(params))
        zone = wigner_seitz_cell(b)
        self._zone_cache = (key, zone, b)
        return zone, b

    # -- the measured plane in the 3-D zone ---------------------------------
    # The BZ overlap tool's cut-plane view (CutPlanePreviewDialog) asks its
    # owner for the geometry through cut_geometry, cut_description,
    # high_symmetry, points_in_plane and preview_closed; this window answers
    # them for the plane a k_z map measures, so the same view shows it.
    def open_plane_preview(self):
        """The 3-D view of the zone with the measured k_z plane in it."""
        from arpes_viewer.ui.viewers.windows import CutPlanePreviewDialog
        preview = getattr(self, "_plane_preview", None)
        if preview is not None and preview.isVisible():
            preview.refresh()
            preview.raise_()
            preview.activateWindow()
            return preview
        preview = CutPlanePreviewDialog(self)
        preview.setWindowTitle("k_z plane in the 3D Brillouin zone")
        self._plane_preview = preview
        preview.show()
        preview.raise_()
        return preview

    def preview_closed(self):
        self._plane_preview = None

    def _kz_axes(self):
        """``(along_kz, along_kpar, across)``, Cartesian unit vectors."""
        from arpes_viewer.tools.crystal.bz3d import kz_frame
        return kz_frame(self.lattice(), self.surface_hkl(), self.kpar_hkl(),
                        float(self.kpar_rotation.value()))

    def cut_geometry(self):
        """``(zone, b, b_conventional, normal, point, u, v)`` of the plane
        the map measures: it holds the surface normal (k_z) and the slit
        direction (k_par) and passes through Γ, so its normal is the third
        axis of the k_z frame."""
        from arpes_viewer.tools.crystal.bz3d import plane_cut
        from arpes_viewer.tools.crystal.lattice import (conventional_vectors,
                                                        reciprocal_vectors)
        zone, b = self._zone()
        b_conventional = reciprocal_vectors(conventional_vectors(self.lattice()))
        _along_kz, _along_kpar, across = self._kz_axes()
        point = np.zeros(3)
        u, v = plane_cut(zone.faces, across, point)
        return zone, b, b_conventional, across, point, u, v

    def cut_description(self) -> str:
        try:
            along_kz, along_kpar, _across = self._kz_axes()
        except Exception as exc:                            # noqa: BLE001
            return str(exc)
        h, k, l = self.surface_hkl()
        text = (f"The measured plane: k_z along ({h} {k} {l}), k// along "
                f"{np.round(along_kpar, 3).tolist()} (Cartesian, a along x), "
                f"through Γ.")
        preview = getattr(self, "_preview", None)
        if preview is not None:
            kz_axis, kpar_axis, _plane = preview
            period = self.surface_period()
            text += (f" Measured k_z {kz_axis[0]:.3f} to {kz_axis[-1]:.3f} Å⁻¹ "
                     f"({kz_axis[0] / period:.2f} to {kz_axis[-1] / period:.2f} "
                     f"periods of {period:.4f} Å⁻¹), k// {kpar_axis[0]:.3f} "
                     f"to {kpar_axis[-1]:.3f} Å⁻¹, at V0 = "
                     f"{self.inner_potential.value():.1f} eV.")
        if self.theta_correct.isChecked() and self.theta_position.value():
            text += (" (The theta offset tilts the measured surface slightly "
                     "out of this plane; not drawn.)")
        return text

    def high_symmetry(self):
        """``(representatives, copies)`` of the named points (cached)."""
        from arpes_viewer.tools.crystal.highsym import (equivalent_points,
                                                        high_symmetry_points)
        params = self.lattice()
        key = (params.a, params.b, params.c, params.alpha, params.beta,
               params.gamma, params.space_group)
        cached = getattr(self, "_highsym_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1], cached[2]
        representatives = high_symmetry_points(params)
        zone, _b = self._zone()
        copies = equivalent_points(params, representatives, zone)
        self._highsym_cache = (key, representatives, copies)
        return representatives, copies

    def points_in_plane(self):
        """The named points the measured plane holds: ``[(label, k), ...]``."""
        from arpes_viewer.tools.crystal.highsym import points_on_plane
        _representatives, copies = self.high_symmetry()
        across = self._kz_axes()[2]
        return [(p.label, p.k) for p in
                points_on_plane(copies, across, 0.0, tol=1e-4)]

    def _write_report(self, kz_axis, kpar_axis, plane):
        period = self.surface_period()
        coverage = 100.0 * float(np.isfinite(plane).mean())
        lines = [
            f"k_z {kz_axis[0]:.3f} to {kz_axis[-1]:.3f} Å⁻¹ "
            f"({(kz_axis[-1] - kz_axis[0]) / period:.2f} zones of "
            f"{period:.4f} Å⁻¹)",
            f"k// {kpar_axis[0]:.3f} to {kpar_axis[-1]:.3f} Å⁻¹",
            f"grid step k_z {(kz_axis[-1] - kz_axis[0]) / max(kz_axis.size - 1, 1):.4f}, "
            f"k// {(kpar_axis[-1] - kpar_axis[0]) / max(kpar_axis.size - 1, 1):.4f} "
            f"Å⁻¹",
            f"{coverage:.0f}% of the grid is covered by the measurement",
        ]
        if getattr(self, "_zone_error", None):
            lines.append(f"<span style='color:#a60'>Zone not drawn: "
                         f"{self._zone_error}</span>")
        for complaint in getattr(self, "_lattice_complaints", ()):
            lines.append(f"<span style='color:#a60'>{complaint}</span>")
        if self.calibrate_hv.isChecked() and self.measured_phi is not None:
            phi = self.measured_phi
            lines.append(
                f"hν calibrated: hν − E<sub>kin</sub>(E<sub>F</sub>) = "
                f"{phi.min():.3f} to {phi.max():.3f} eV over the scan "
                f"(single work function {self.work_function.value():.3f} eV "
                f"not used)")
        if self.inner_potential.value() < 0:
            lines.append("<span style='color:#a60'>V0 is negative.</span>")
        if self._pick_points:
            lines.append(self._pick_summary())
        self.report.setHtml("<br>".join(lines))

    # -- picking two points ------------------------------------------------
    def _toggle_picking(self, on: bool):
        self._picking = bool(on)
        self.pick_button.setText("Click two points..." if on
                                 else "Measure a k_z period...")
        if on:
            self._pick_points = []
            self.pick_item.setData([], [])
            self.plot.scene().sigMouseClicked.connect(self._clicked)
        else:
            try:
                self.plot.scene().sigMouseClicked.disconnect(self._clicked)
            except TypeError:
                pass
        self.refresh()

    def _clicked(self, event):
        if not self._picking:
            return
        point = self.plot.getPlotItem().vb.mapSceneToView(event.scenePos())
        self._pick_points.append((float(point.x()), float(point.y())))
        if len(self._pick_points) > 2:
            self._pick_points = self._pick_points[-2:]
        xs = [p[0] for p in self._pick_points]
        ys = [p[1] for p in self._pick_points]
        self.pick_item.setData(xs, ys)
        if len(self._pick_points) == 2:
            self.pick_button.setChecked(False)      # also stops the picking
        else:
            self.refresh()

    def _pick_summary(self) -> str:
        if len(self._pick_points) < 2:
            return "One point picked; click the same feature one zone along."
        (x0, _y0), (x1, _y1) = self._pick_points
        distance = abs(x1 - x0)
        if distance <= 0:
            return ("<span style='color:#c00'>Those two points are at the "
                    "same k_z.</span>")
        lines = [f"<b>Picked k_z separation {distance:.4f} Å⁻¹</b> "
                 f"(real-space repeat {2 * np.pi / distance:.3f} A)"]
        try:
            found = cleavage.candidates(distance, self.lattice(),
                                        tolerance=0.15)
        except Exception as exc:                            # noqa: BLE001
            return "<br>".join(lines + [f"<span style='color:#c00'>{exc}</span>"])
        if not found:
            lines.append("No lattice plane matches that within 15%. Either "
                         "the lattice constants are wrong, or the two points "
                         "are not one zone apart.")
        else:
            lines.append("Planes that match within 15%:")
            for candidate in found[:6]:
                lines.append("&nbsp;&nbsp;" + candidate.describe())
        return "<br>".join(lines)

    # -- converting --------------------------------------------------------
    def convert(self):
        remembered.remember(self.REMEMBERED, self._shape(),
                            self.remembered_settings())
        cube = np.asarray(self.contour.full_cube(), dtype=float)
        settings = self.settings()
        n_kz, n_kpar = int(self.n_kz.value()), int(self.n_kpar.value())
        hv, angle, energy = self.hv, self.angle, self.energy

        def work(report):
            def tick(done, total):
                report(done / max(1, total),
                       f"Converting energy slice {done + 1} of {total}")
            return kzconv.to_kz_cube(hv, angle, energy, cube, n_kz=n_kz,
                                     n_kpar=n_kpar, progress=tick, **settings)

        started = nxs_jobs.run_job(
            self, "Converting to momentum", work, on_done=self._finish,
            on_error=lambda exc: self.report.setHtml(
                f"<span style='color:#c00'>{exc}</span>"))
        if not started:
            self.report.setHtml("Another operation is running.")

    def _finish(self, converted):
        kz_axis, kpar_axis, energy, out = converted
        data = self.contour.data
        scan = data.scan
        settings = self.settings()
        parameters = dict(settings)
        phi = np.asarray(settings["work_function"], dtype=float)
        parameters["work_function"] = float(np.mean(phi))
        parameters["hv_calibrated"] = bool(phi.ndim)
        if phi.ndim:
            parameters["work_function_per_hv"] = " ".join(f"{v:.4f}" for v in phi)
        parameters["theta_corrected"] = bool(self.theta_correct.isChecked())
        parameters.update({
            "n_kz": int(self.n_kz.value()),
            "n_kpar": int(self.n_kpar.value()),
            "space_group": int(self.space_group.value()),
            "lattice_a": float(self.lat_a.value()),
            "lattice_b": float(self.lat_b.value()),
            "lattice_c": float(self.lat_c.value()),
            "lattice_alpha": float(self.lat_alpha.value()),
            "lattice_beta": float(self.lat_beta.value()),
            "lattice_gamma": float(self.lat_gamma.value()),
            "surface_hkl": " ".join(str(v) for v in self.surface_hkl()),
            "kpar_hkl": " ".join(str(v) for v in self.kpar_hkl()),
            "kpar_rotation_deg": float(self.kpar_rotation.value()),
            "surface_period_invA": float(self.surface_period()),
        })
        info = record_step(dict(scan.info),
                           Step("kz_to_k", parameters,
                                source=self.contour.filename))
        info["kz.inner_potential_eV"] = float(settings["inner_potential"])
        # Hand the crystal on to the Brillouin-zone dialog of the converted
        # map, so the zone drawn there starts as the one drawn here rather
        # than as a 3 A cubic cell along (001).
        h, k, l = self.surface_hkl()
        kh, kk, kl = self.kpar_hkl()
        info.update({
            "bz.mode": "3d", "bz.zone": "conventional",
            "bz.space_group": int(self.space_group.value()),
            "bz.a": float(self.lat_a.value()), "bz.b": float(self.lat_b.value()),
            "bz.c": float(self.lat_c.value()),
            "bz.alpha": float(self.lat_alpha.value()),
            "bz.beta": float(self.lat_beta.value()),
            "bz.gamma": float(self.lat_gamma.value()),
            "bz.h": h, "bz.k": k, "bz.l": l,
            "bz.kpar_h": kh, "bz.kpar_k": kk, "bz.kpar_l": kl,
            "bz.azimuth_deg": float(self.kpar_rotation.value()),
            "bz.offset": 0.0,
        })

        name = _unique(f"{self.contour.filename} [kz]",
                       self.contour.existing_names())
        result = MemoryData(
            "kz_map_k", (kz_axis, kpar_axis, energy), out,
            {"x": "k_z (Å⁻¹)", "k": "k// (Å⁻¹)",
             "z": scan.labels.get("z", "E - E_F (eV)")},
            source_label=name, parameters=parameters, prefix="kz_to_k",
            source_path=getattr(data, "path", ""), source_info=info,
            source_motors=dict(scan.fourd_info))
        self.datasetsCreated.emit([result])
        coverage = 100.0 * float(np.isfinite(out).mean())
        self.report.setHtml(
            f"<b>Converted to (k_z, k//, E) at V0 = "
            f"{settings['inner_potential']:.1f} eV.</b><br>"
            f"k_z {kz_axis[0]:.3f} to {kz_axis[-1]:.3f} Å⁻¹, "
            f"k// {kpar_axis[0]:.3f} to {kpar_axis[-1]:.3f} Å⁻¹, "
            f"{coverage:.0f}% covered.<br>"
            f"Added to the list as “{name}”.")


def _same_direction(first, second) -> bool:
    """Whether two Miller triples name the same set of planes: (002) and
    (001), (-1 0 0) and (100) are one surface."""
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    if not first.any() or not second.any():
        return False
    return bool(np.linalg.norm(np.cross(first, second)) < 1e-9)


def _unique(name: str, taken) -> str:
    taken = set(taken or ())
    if name not in taken:
        return name
    index = 2
    while f"{name} ({index})" in taken:
        index += 1
    return f"{name} ({index})"
