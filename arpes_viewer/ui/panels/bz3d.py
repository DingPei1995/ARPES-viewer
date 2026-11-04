"""
ui/panels/bz3d.py
=================
The crystal's Brillouin zone in 3-D, on its own: the Basic tab's
**3D BZ...**.

It was a step of the crystal-structure window; the zone needs only a cell
and a space group, not atoms, so it is a window of its own:

- **The crystal** -- typed in as everywhere else (the space group first,
  which greys out the cell parameters it fixes; :mod:`ui.common.cellinput`),
  or filled from a CIF file with a button. It starts from the last crystal
  of the *BZ overlap* tool, if it drew a 3-D one.
- **Planes** -- as many as wanted, each with its own (hkl) normal, its
  height along it (0 through Γ, 0.5 the zone top...), colour and opacity;
  any of them can carry a measured constant-energy map of a k-map -- one
  selected when the window was opened, or any k-map in the list, read when
  it is chosen. The map's kx, ky lie along the plane's own in-plane axes
  (k_a, k_b for a plane normal to k_c), turned by the maps' azimuth.
- **Axes** -- the crystal's (k_a, k_b, k_c: Cartesian axes of the cell)
  by default, or the sample's as the data has them (k_x, k_y, k_z: k_z
  along the cleavage plane's normal, k_x along the maps' k_x). One symbol
  never names two directions.
- **Paths** -- as many as wanted, each through the labelled points in its
  own colour (Γ-M-K-Γ, A-L-H-A...).
- **Export** -- a picture at any size, or straight into the figure
  composer.

The drawing is the crystal window's :class:`ui.panels.crystal.CrystalView`
in its zone mode; the geometry is :mod:`tools.crystal.bz3d`.
"""
from __future__ import annotations

import os

import numpy as np
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                             QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QScrollArea,
                             QSpinBox, QVBoxLayout, QWidget)

from arpes_viewer.tools.crystal import structure as S
from arpes_viewer.ui.common.cellinput import CellInput
from arpes_viewer.ui.common.screen import fits_screen
from arpes_viewer.ui.panels.crystal import (CrystalView, _ColourButton,
                                            picture_to_composer)

__all__ = ["BrillouinZone3DDialog", "PlaneRow", "PathRow"]

#: the colours new planes and paths take, in turn
PLANE_COLOURS = ("#9ad29a", "#9bb8e8", "#f2c38b", "#d9a0d9", "#a6d8d8")
PATH_COLOURS = ("#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e")


class PlaneRow(QWidget):
    """One plane in the zone: its normal (hkl), its height along it, its
    colour and opacity -- and, for a plane normal to k_z, a measured map."""

    changed = pyqtSignal()
    removed = pyqtSignal(object)

    def __init__(self, hkl=(0, 0, 1), height=0.0, colour="#9ad29a",
                 alpha=0.45, maps=()):
        super().__init__()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 2, 0, 2)
        row = QHBoxLayout()
        self.hkl_boxes = []
        for name, value in zip("hkl", hkl):
            box = QSpinBox()
            box.setRange(-9, 9)
            box.setValue(int(value))
            box.valueChanged.connect(self.changed)
            row.addWidget(QLabel(name))
            row.addWidget(box)
            self.hkl_boxes.append(box)
        self.height_box = QDoubleSpinBox()
        self.height_box.setRange(-2.0, 2.0)
        self.height_box.setSingleStep(0.05)
        self.height_box.setDecimals(3)
        self.height_box.setValue(float(height))
        self.height_box.setToolTip(
            "Height along the normal, in units of the reciprocal vector "
            "G(hkl): 0 is a plane through Γ, 0.5 the zone boundary (top).")
        self.height_box.valueChanged.connect(self.changed)
        row.addWidget(QLabel("at"))
        row.addWidget(self.height_box)
        self.colour_button = _ColourButton(colour)
        self.colour_button.colourChanged.connect(self.changed)
        row.addWidget(self.colour_button)
        self.alpha_box = QDoubleSpinBox()
        self.alpha_box.setRange(0.05, 1.0)
        self.alpha_box.setSingleStep(0.05)
        self.alpha_box.setValue(float(alpha))
        self.alpha_box.setToolTip("Opacity of the plane.")
        self.alpha_box.valueChanged.connect(self.changed)
        row.addWidget(self.alpha_box)
        remove = QPushButton("✕")
        remove.setToolTip("Remove this plane.")
        remove.setMaximumWidth(28)
        remove.clicked.connect(lambda: self.removed.emit(self))
        row.addWidget(remove)
        column.addLayout(row)

        self.map_combo = QComboBox()
        self.map_combo.addItem("(colour only)")
        self.map_combo.addItems(list(maps))
        self.map_combo.setToolTip(
            "Draw a measured constant-energy map on this plane, cut to the "
            "zone: any k-map of the list (press ↻ beside Add a plane after "
            "adding more). Its kx, ky lie along the plane's in-plane axes.")
        self.map_combo.currentIndexChanged.connect(self.changed)
        self.energy_box = QDoubleSpinBox()
        self.energy_box.setRange(-50.0, 50.0)
        self.energy_box.setDecimals(3)
        self.energy_box.setSingleStep(0.05)
        self.energy_box.setSuffix(" eV")
        self.energy_box.setToolTip("The map's energy (E - E_F).")
        self.energy_box.valueChanged.connect(self.changed)
        map_row = QHBoxLayout()
        map_row.addWidget(QLabel("    map"))
        map_row.addWidget(self.map_combo, 1)
        map_row.addWidget(self.energy_box)
        self._map_row = QWidget()
        self._map_row.setLayout(map_row)
        column.addWidget(self._map_row)

    def set_maps(self, names):
        """Offer ``names``, keeping the current choice if it is still one."""
        current = self.map_combo.currentText()
        self.map_combo.blockSignals(True)
        self.map_combo.clear()
        self.map_combo.addItem("(colour only)")
        self.map_combo.addItems(list(names))
        index = self.map_combo.findText(current)
        self.map_combo.setCurrentIndex(max(index, 0))
        self.map_combo.blockSignals(False)

    def hkl(self):
        return tuple(int(box.value()) for box in self.hkl_boxes)


class PathRow(QWidget):
    """One path through the labelled points, in its own colour."""

    changed = pyqtSignal()
    removed = pyqtSignal(object)

    def __init__(self, text="", colour="#d62728", width=2.0):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        self.edit = QLineEdit(text)
        self.edit.setPlaceholderText("e.g. Γ-X-M-Γ-Z-R-A-Z  (G for Γ, | for a jump)")
        self.edit.setToolTip("A path through the labelled points.")
        self.edit.editingFinished.connect(self.changed)
        row.addWidget(self.edit, 1)
        self.colour_button = _ColourButton(colour)
        self.colour_button.colourChanged.connect(self.changed)
        row.addWidget(self.colour_button)
        self.width_box = QDoubleSpinBox()
        self.width_box.setRange(0.5, 10.0)
        self.width_box.setSingleStep(0.5)
        self.width_box.setValue(float(width))
        self.width_box.setToolTip("Line width (px at the window's size).")
        self.width_box.valueChanged.connect(self.changed)
        row.addWidget(self.width_box)
        remove = QPushButton("✕")
        remove.setToolTip("Remove this path.")
        remove.setMaximumWidth(28)
        remove.clicked.connect(lambda: self.removed.emit(self))
        row.addWidget(remove)

    def labels(self):
        from arpes_viewer.tools.crystal.bands import parse_path
        return list(parse_path(self.edit.text()))


@fits_screen
class BrillouinZone3DDialog(QDialog):
    """The 3-D Brillouin zone of a crystal, with planes and paths in it."""

    def __init__(self, parent=None, datasets=None, colormap="blue", flip=True,
                 map_source=None):
        super().__init__(parent)
        self.setWindowTitle("3D Brillouin zone")
        self.resize(1200, 780)
        #: k-maps whose constant-energy pictures can lie on the planes
        self.datasets = [(n, d) for n, d in (datasets or [])
                         if getattr(d, "kind", None) == "k_map"]
        #: ``map_source()`` -> [(name, read)] of every k-map in the list,
        #: ``read()`` giving the dataset; a map is read when first drawn,
        #: and given back when the window closes
        self.map_source = map_source
        self._readers = {}
        self._read = []
        self.finished.connect(self._release_read)
        self.colormap, self.flip = colormap, flip
        self.cif_path = ""
        self.plane_rows, self.path_rows = [], []

        self.view = CrystalView(self)
        self.view.mode = "zone"
        self.view.show_cell = False

        layout = QHBoxLayout(self)
        side = QScrollArea()
        side.setWidgetResizable(True)
        side.setMinimumWidth(500)
        panel = QWidget()
        side.setWidget(panel)
        column = QVBoxLayout(panel)
        column.addWidget(self._crystal_group())
        column.addWidget(self._planes_group())
        column.addWidget(self._paths_group())
        column.addWidget(self._display_group())
        column.addWidget(self._export_group())
        column.addStretch(1)
        layout.addWidget(side, 2)

        right = QVBoxLayout()
        right.addWidget(self.view, 1)
        views = QHBoxLayout()
        views.addWidget(QLabel("<i>drag to turn, wheel to zoom</i>  View along:"))
        self.view_buttons = []
        for index in range(3):
            button = QPushButton(self.view.zone_axis_names[index])
            button.clicked.connect(lambda _=False, i=index: self.look_along(i))
            views.addWidget(button)
            self.view_buttons.append(button)
        oblique = QPushButton("oblique")
        oblique.clicked.connect(lambda: self.look_along("oblique"))
        views.addWidget(oblique)
        views.addStretch(1)
        right.addLayout(views)
        layout.addLayout(right, 3)

        self._start_from_last_crystal()
        self.add_plane((0, 0, 1), 0.0)
        self.add_path("")
        self.refresh()

    # ==================================================================
    # The crystal
    # ==================================================================
    def _crystal_group(self):
        group = QGroupBox("Crystal (space group first)")
        column = QVBoxLayout(group)
        # the file first, as in the crystal window: it fills what is below
        self.cif_button = QPushButton("Read a CIF file...")
        self.cif_button.setToolTip(
            "Fill the space group and the cell below from a CIF file; the "
            "zone is redrawn at once.")
        self.cif_button.clicked.connect(lambda: self.read_cif())
        column.addWidget(self.cif_button)
        self.cell_input = CellInput(group)
        self.cell_input.changed.connect(self.refresh)
        column.addWidget(self.cell_input)
        self.zone_label = QLabel("")
        self.zone_label.setWordWrap(True)
        column.addWidget(self.zone_label)
        return group

    def _start_from_last_crystal(self):
        """The BZ overlap tool's last 3-D crystal, when there is one."""
        from arpes_viewer.tools.crystal import last_crystal
        try:
            params = last_crystal.lattice_params()
        except Exception:                                  # noqa: BLE001
            params = None
        if params is None:
            return False
        self.cell_input.set_cell(params.space_group or 1, params.a, params.b,
                                 params.c, params.alpha, params.beta,
                                 params.gamma, emit=False)
        return True

    def read_cif(self, path=None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "CIF file", "",
                                                  "CIF (*.cif);;All files (*)")
            if not path:
                return None
        try:
            structure = S.read_cif(path)
        except (OSError, ValueError, UnicodeError) as exc:
            self.zone_label.setText(f"<b>Could not read it:</b> {exc}")
            return None
        self.cell_input.set_cell(structure.space_group_number or 1,
                                 structure.a, structure.b, structure.c,
                                 structure.alpha, structure.beta,
                                 structure.gamma, emit=False)
        self.cif_path = os.path.abspath(path)
        self._name = structure.name
        self.refresh()
        return structure

    def structure(self):
        """The cell as a :class:`tools.crystal.structure.Structure` without
        atoms -- all the zone needs."""
        number = self.cell_input.space_group()
        a, b, c, alpha, beta, gamma = self.cell_input.cell()
        return S.Structure(a, b, c, alpha, beta, gamma, atoms=[],
                           name=getattr(self, "_name", ""),
                           space_group=str(number), space_group_number=number)

    # ==================================================================
    # Planes and paths
    # ==================================================================
    def _planes_group(self):
        group = QGroupBox("Planes in the zone")
        column = QVBoxLayout(group)
        self.planes_column = QVBoxLayout()
        column.addLayout(self.planes_column)
        add = QPushButton("Add a plane in 3D BZ")
        add.setToolTip("Another plane, with its own (hkl) normal, height, "
                       "colour and opacity: through Γ at 0, at the zone top "
                       "at 0.5. Any plane can carry a measured map.")
        add.clicked.connect(lambda: self.add_plane())
        update = QPushButton("↻ Maps from the list")
        update.setToolTip("Offer every k-map now in the main list on the "
                          "planes' map choices.")
        update.clicked.connect(self.update_maps)
        buttons = QHBoxLayout()
        buttons.addWidget(add, 1)
        buttons.addWidget(update)
        column.addLayout(buttons)
        maps = QFormLayout()
        self.map_azimuth = QDoubleSpinBox()
        self.map_azimuth.setRange(-360.0, 360.0)
        self.map_azimuth.setSuffix(" °")
        self.map_azimuth.setToolTip(
            "How the maps' k_x lies against the plane's first in-plane axis "
            "(k_a for a plane normal to k_c): the sample azimuth. It also "
            "turns the sample axes' k_x.")
        self.map_window = QDoubleSpinBox()
        self.map_window.setRange(0.0, 2.0)
        self.map_window.setDecimals(3)
        self.map_window.setValue(0.05)
        self.map_window.setSuffix(" eV")
        self.map_window.setToolTip("The energy window the maps are "
                                   "averaged over.")
        self.map_window.valueChanged.connect(self.refresh)
        self.map_azimuth.valueChanged.connect(self._frame_changed)
        maps.addRow("Maps' azimuth", self.map_azimuth)
        maps.addRow("Integrate", self.map_window)
        column.addLayout(maps)
        return group

    def add_plane(self, hkl=(0, 0, 1), height=None, colour=None, alpha=0.45):
        """A new plane; by default normal to (001), the first through Γ and
        the next ones at the zone top."""
        if height is None:
            height = 0.5 if self.plane_rows else 0.0
        if colour is None:
            colour = PLANE_COLOURS[len(self.plane_rows) % len(PLANE_COLOURS)]
        row = PlaneRow(hkl, height, colour, alpha, maps=self.map_names())
        row.changed.connect(self.refresh)
        row.removed.connect(self.remove_plane)
        self.planes_column.addWidget(row)
        self.plane_rows.append(row)
        self.refresh()
        return row

    # -- the maps a plane can carry -------------------------------------------
    def map_names(self):
        """The k-maps a plane can carry: those handed over, then the
        list's."""
        names = [n for n, _d in self.datasets]
        self._readers = {}
        if callable(self.map_source):
            try:
                offered = list(self.map_source())
            except Exception:                              # noqa: BLE001
                offered = []
            for name, read in offered:
                if name not in names:
                    names.append(name)
                    self._readers[name] = read
        return names

    def update_maps(self):
        names = self.map_names()
        for row in self.plane_rows:
            row.set_maps(names)
        return names

    def map_data(self, name):
        """The k-map called ``name``, read from the list on first use."""
        held = dict(self.datasets)
        if name in held:
            return held[name]
        read = self._readers.get(name)
        if read is None:
            raise KeyError(name)
        data = read()
        if getattr(data, "kind", None) != "k_map":
            try:
                data.close()
            except Exception:                              # noqa: BLE001
                pass
            raise ValueError(f"“{name}” is not a k-map")
        self.datasets.append((name, data))
        self._read.append(data)
        return data

    def _release_read(self, *_):
        for data in self._read:
            try:
                data.close()
            except Exception:                              # noqa: BLE001
                pass
        self._read = []

    def remove_plane(self, row):
        if row in self.plane_rows:
            self.plane_rows.remove(row)
            row.setParent(None)
            row.deleteLater()
            self.refresh()

    def _paths_group(self):
        group = QGroupBox("Paths through the labelled points")
        column = QVBoxLayout(group)
        self.paths_column = QVBoxLayout()
        column.addLayout(self.paths_column)
        add = QPushButton("Add path")
        add.setToolTip("Another path, in a colour of its own.")
        add.clicked.connect(lambda: self.add_path())
        column.addWidget(add)
        return group

    def add_path(self, text="", colour=None, width=2.0):
        if colour is None:
            colour = PATH_COLOURS[len(self.path_rows) % len(PATH_COLOURS)]
        row = PathRow(text, colour, width)
        row.changed.connect(self.refresh)
        row.removed.connect(self.remove_path)
        self.paths_column.addWidget(row)
        self.path_rows.append(row)
        self.refresh()
        return row

    def remove_path(self, row):
        if row in self.path_rows:
            self.path_rows.remove(row)
            row.setParent(None)
            row.deleteLater()
            self.refresh()

    def _display_group(self):
        group = QGroupBox("Display")
        form = QFormLayout(group)
        self.labels_box = QCheckBox("Label the high-symmetry points")
        self.labels_box.setChecked(True)
        self.axes_box = QCheckBox("Draw the axes")
        self.axes_box.setChecked(True)
        for box in (self.labels_box, self.axes_box):
            box.toggled.connect(self.refresh)
            form.addRow(box)
        # Two frames, two sets of names: the crystal's own axes (k_a, k_b,
        # k_c), or the measurement's (k_x, k_y, k_z) -- k_z along the
        # cleavage plane's normal and k_x as the maps' k_x. One symbol never
        # names two directions.
        self.frame_combo = QComboBox()
        self.frame_combo.addItem("Crystal: k_a, k_b, k_c", "crystal")
        self.frame_combo.addItem("Sample, as the data: k_x, k_y, k_z", "sample")
        self.frame_combo.setToolTip(
            "Crystal: Cartesian axes of the cell (k_a along a, k_c normal to "
            "the a-b plane). Sample: k_z along the cleavage plane's normal "
            "(hkl below), k_x along the maps' k_x (turned by the maps' "
            "azimuth) -- the kx, ky of the converted data.")
        self.frame_combo.currentIndexChanged.connect(self._frame_changed)
        form.addRow("Axes", self.frame_combo)
        surface = QHBoxLayout()
        self.surface_boxes = []
        for value in (0, 0, 1):
            box = QSpinBox()
            box.setRange(-9, 9)
            box.setValue(value)
            box.valueChanged.connect(self._frame_changed)
            surface.addWidget(box)
            self.surface_boxes.append(box)
        self.surface_row = QWidget()
        self.surface_row.setLayout(surface)
        self.surface_row.setToolTip("The cleavage plane (hkl): the sample's "
                                    "k_z is along its normal.")
        form.addRow("Cleavage plane (hkl)", self.surface_row)
        self.surface_row.setEnabled(False)
        self.left_edit = QLineEdit("")
        self.left_edit.setPlaceholderText("e.g. L, M")
        self.left_edit.setToolTip(
            "Points labelled at their leftmost equivalent (by the zone's "
            "rotation axis), as the picture is turned -- away from the paths "
            "and the axes where they would crowd.")
        self.left_edit.editingFinished.connect(self.refresh)
        form.addRow("Label on the left", self.left_edit)
        self.only_edit = QLineEdit("")
        self.only_edit.setPlaceholderText("all; or e.g. G, L")
        self.only_edit.setToolTip(
            "Only these high-symmetry points are labelled (empty: all of "
            "them) -- e.g. just Γ and L on a schematic of one path.")
        self.only_edit.editingFinished.connect(self.refresh)
        form.addRow("Label only", self.only_edit)
        return group

    # ==================================================================
    # Drawing
    # ==================================================================
    def plane_picture(self, name, energy):
        """A k-map at ``energy`` as ``(QImage, kx range, ky range,
        azimuth)``, coloured with the window's colour map."""
        from PyQt5.QtGui import QImage
        from arpes_viewer.tools.output import colormaps
        from arpes_viewer.ui.panels.bands import _relative_energy
        import warnings

        data = self.map_data(name)
        scan = data.scan
        axis = _relative_energy(scan.z, scan.info)
        half = max(0.5 * self.map_window.value(),
                   0.5 * abs(float(axis[1] - axis[0])) if axis.size > 1 else 0.0)
        keep = np.abs(axis - energy) <= half
        if not keep.any():
            keep = np.abs(axis - energy) == np.min(np.abs(axis - energy))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            plane = np.nanmean(np.asarray(scan.value, float)[:, :, keep], axis=2)
        finite = plane[np.isfinite(plane)]
        lo, hi = ((float(np.percentile(finite, 1)), float(np.percentile(finite, 99.5)))
                  if finite.size else (0.0, 1.0))
        scaled = np.clip((plane - lo) / ((hi - lo) or 1.0), 0, 1)
        lut = np.asarray(colormaps.get_lut(self.colormap, flip=self.flip))
        index = np.rint(np.nan_to_num(scaled) * (len(lut) - 1)).astype(int)
        rgb = lut[index]
        kx, ky = np.asarray(scan.x, float), np.asarray(scan.k, float)
        if kx[0] > kx[-1]:
            rgb, kx, plane = rgb[::-1], kx[::-1], plane[::-1]
        if ky[0] > ky[-1]:
            rgb, ky, plane = rgb[:, ::-1], ky[::-1], plane[:, ::-1]
        buffer = np.empty((ky.size, kx.size, 4), dtype=np.uint8)
        buffer[..., 0] = rgb[..., 2].T
        buffer[..., 1] = rgb[..., 1].T
        buffer[..., 2] = rgb[..., 0].T
        buffer[..., 3] = np.where(np.isfinite(plane), 255, 0).T
        buffer = np.ascontiguousarray(buffer)
        image = QImage(buffer.data, kx.size, ky.size, 4 * kx.size,
                       QImage.Format_ARGB32).copy()
        return (image, (float(kx[0]), float(kx[-1])),
                (float(ky[0]), float(ky[-1])), self.map_azimuth.value())

    def refresh(self, *_):
        """Hand the view the zone as the controls describe it."""
        if not hasattr(self, "labels_box"):
            return                                  # still being built
        from arpes_viewer.tools.crystal.bands import parse_path
        from arpes_viewer.tools.crystal.lattice import reciprocal_vectors

        structure = self.structure()
        self.view.set_structure(structure)
        self.view.mode = "zone"
        try:
            g_basis = reciprocal_vectors(structure.vectors())
        except (ValueError, FloatingPointError) as exc:
            self.zone_label.setText(f"No zone: {exc}")
            self.view.update()
            return
        planes, problems = [], []
        for row in self.plane_rows:
            g = np.asarray(row.hkl(), dtype=float) @ g_basis
            length = float(np.linalg.norm(g))
            if length == 0:
                continue
            normal = g / length
            plane = {"normal": tuple(normal),
                     "height": row.height_box.value() * length,
                     "colour": row.colour_button.colour,
                     "alpha": row.alpha_box.value()}
            if row.map_combo.currentIndex() > 0:
                try:
                    plane["picture"] = self.plane_picture(
                        row.map_combo.currentText(), row.energy_box.value())
                except Exception as exc:                  # noqa: BLE001
                    problems.append(f"<b>Could not draw "
                                    f"{row.map_combo.currentText()}:</b> {exc}")
            planes.append(plane)
        self.view.zone_planes = planes
        self.view.zone_path = []
        self.view.zone_paths = [{"labels": row.labels(),
                                 "colour": row.colour_button.colour,
                                 "width": row.width_box.value()}
                                for row in self.path_rows if row.labels()]
        self.view.zone_labels = self.labels_box.isChecked()
        self.view.zone_axes = self.axes_box.isChecked()
        self.view.zone_left_labels = {l for l in parse_path(self.left_edit.text())
                                      if l != "|"}
        only = getattr(self, "only_edit", None)
        only = {l for l in parse_path(only.text()) if l != "|"} if only else set()
        self.view.zone_only_labels = only or None
        try:
            _p, _b, _zone, points = self.view.zone()
            params = structure.lattice_params()
            self.zone_label.setText(
                f"Space group {params.space_group or '(none: primitive)'}; "
                f"labelled points: {', '.join(p.label for p in points)}."
                + "".join("<br>" + p for p in problems))
        except Exception as exc:                              # noqa: BLE001
            self.zone_label.setText(f"No zone: {exc}")
        self.view.update()

    # ==================================================================
    # The axes' frame
    # ==================================================================
    def frame(self) -> str:
        return self.frame_combo.currentData()

    def surface_hkl(self):
        return tuple(int(box.value()) for box in self.surface_boxes)

    def set_frame(self, frame: str, surface_hkl=None, azimuth=None):
        """Show the crystal's axes (``"crystal"``) or the sample's
        (``"sample"``: k_z along the normal of ``surface_hkl``, k_x along
        the maps' k_x turned by ``azimuth``)."""
        if surface_hkl is not None:
            for box, value in zip(self.surface_boxes, surface_hkl):
                box.blockSignals(True)
                box.setValue(int(value))
                box.blockSignals(False)
        if azimuth is not None:
            self.map_azimuth.blockSignals(True)
            self.map_azimuth.setValue(float(azimuth))
            self.map_azimuth.blockSignals(False)
        self.frame_combo.setCurrentIndex(0 if frame == "crystal" else 1)
        self._frame_changed()

    def _frame_changed(self, *_):
        from arpes_viewer.ui.panels.crystal import sample_frame
        sample = self.frame() == "sample"
        self.surface_row.setEnabled(sample)
        if sample:
            try:
                from arpes_viewer.tools.crystal.lattice import reciprocal_vectors
                g = np.asarray(self.surface_hkl(), dtype=float) @ \
                    reciprocal_vectors(self.structure().vectors())
                if not np.linalg.norm(g):
                    raise ValueError("(0 0 0) is not a plane")
                self.view.zone_axis_vectors = sample_frame(
                    g, self.map_azimuth.value())
                self.view.zone_axis_names = ("k_x", "k_y", "k_z")
            except Exception:                              # noqa: BLE001
                sample = False
        if not sample:
            self.view.zone_axis_vectors = np.eye(3)
            self.view.zone_axis_names = ("k_a", "k_b", "k_c")
        for button, name in zip(self.view_buttons, self.view.zone_axis_names):
            button.setText(name)
        self.refresh()

    def look_along(self, direction):
        """Turn the view: ``"oblique"`` (or None), an axis index 0-2 or an
        axis name of the frame shown ("k_x", "k_a" ...), or a Cartesian
        vector."""
        if direction is None or (isinstance(direction, str)
                                 and direction.lower() == "oblique"):
            self.view.camera.azimuth, self.view.camera.elevation = -35.0, 28.0
            self.view.update()
            return
        if isinstance(direction, str):
            names = list(self.view.zone_axis_names)
            if direction not in names:
                raise ValueError(f"look_along: {direction!r} is not one of "
                                 f"{names + ['oblique']}")
            direction = names.index(direction)
        if isinstance(direction, (int, np.integer)):
            direction = np.asarray(self.view.zone_axis_vectors)[int(direction)]
        self.view.view_along(direction)

    # ==================================================================
    # Export
    # ==================================================================
    def _export_group(self):
        group = QGroupBox("Export")
        form = QFormLayout(group)
        size = QHBoxLayout()
        self.width_box = QSpinBox()
        self.height_box = QSpinBox()
        for box, value in ((self.width_box, 1600), (self.height_box, 1600)):
            box.setRange(100, 12000)
            box.setValue(value)
            box.setSingleStep(100)
            size.addWidget(box)
        form.addRow("Size (px)", size)
        text = QHBoxLayout()
        self.panel_mm_box = QDoubleSpinBox()
        self.panel_mm_box.setRange(0.0, 500.0)
        self.panel_mm_box.setDecimals(1)
        self.panel_mm_box.setSuffix(" mm")
        self.panel_mm_box.setSpecialValueText("off")
        self.panel_mm_box.setToolTip(
            "The width the picture will have in the figure. With it set, "
            "the labels are sized so that they come out at the text size "
            "beside it there, whatever the picture's size in pixels. Off: "
            "the labels scale with the picture, as on screen.")
        self.text_pt_box = QDoubleSpinBox()
        self.text_pt_box.setRange(3.0, 72.0)
        self.text_pt_box.setDecimals(1)
        self.text_pt_box.setValue(8.0)
        self.text_pt_box.setSuffix(" pt")
        text.addWidget(QLabel("panel width"))
        text.addWidget(self.panel_mm_box)
        text.addWidget(QLabel("text"))
        text.addWidget(self.text_pt_box)
        form.addRow("Labels", text)
        buttons = QHBoxLayout()
        save = QPushButton("Save picture...")
        save.clicked.connect(lambda: self.save_picture())
        compose = QPushButton("To figure composer...")
        compose.setToolTip("Add the zone as a panel of a figure composer "
                           "that is open, or of a new one.")
        compose.clicked.connect(lambda: self.to_figure_composer())
        buttons.addWidget(save)
        buttons.addWidget(compose)
        form.addRow(buttons)
        self.export_label = QLabel("")
        self.export_label.setWordWrap(True)
        form.addRow(self.export_label)
        return group

    def label_px(self, width_px: int = None):
        """The label size in pixels for an export ``width_px`` wide that is
        printed at the panel width: text pt -> mm -> pixels. None when no
        panel width is set."""
        mm = float(self.panel_mm_box.value())
        if mm <= 0:
            return None
        width_px = int(width_px or self.width_box.value())
        return float(self.text_pt_box.value()) * 25.4 / 72.0 * width_px / mm

    def picture(self, width=None, height=None):
        """The zone as a picture of the export size (or ``width`` x
        ``height``), its labels sized for the final panel when a panel width
        is given."""
        width = int(width or self.width_box.value())
        height = int(height or self.height_box.value())
        self.view.font_px_fixed = self.label_px(width)
        try:
            return self.view.render_image(width, height)
        finally:
            self.view.font_px_fixed = None

    def _picture_name(self) -> str:
        name = getattr(self, "_name", "") or f"SG {self.cell_input.space_group()}"
        return f"{name} Brillouin zone"

    def save_picture(self, path=None):
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save picture", "brillouin_zone.png", "PNG (*.png)")
            if not path:
                return None
        if not path.lower().endswith(".png"):
            path += ".png"
        self.picture().save(path, "PNG")
        self.export_label.setText(f"Wrote {path}.")
        return path

    def to_figure_composer(self, target=None, ask=True):
        sources = None
        if self.cif_path:
            from arpes_viewer.tools.output.figfile import source_record
            sources = [source_record(self.cif_path, kind="structure",
                                     note="the zone is drawn from this CIF")]
        target = picture_to_composer(self, self.picture(), self._picture_name(),
                                     sources=sources, target=target, ask=ask)
        if target is not None:
            self.export_label.setText(f"Added to “{target.windowTitle()}”.")
        return target
