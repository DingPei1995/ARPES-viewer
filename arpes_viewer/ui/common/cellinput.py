"""
ui/common/cellinput.py
======================
A crystal's cell typed in the way the Brillouin-zone tool asks for it: the
space group first, then the six cell parameters -- with the ones the space
group fixes greyed out and following the ones it leaves free (b = a for a
tetragonal group, gamma = 120 for a hexagonal one...).

Used by every window that asks for a 3-D lattice: the crystal structure,
the 3-D Brillouin zone and the tight-binding fit, so a cell is entered the
same way everywhere and never contradicts its own space group. The
constraints are :func:`tools.crystal.lattice.free_parameters`.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                             QSpinBox, QWidget)

__all__ = ["CellInput", "LENGTHS", "ANGLES"]

LENGTHS = ("a", "b", "c")
ANGLES = ("alpha", "beta", "gamma")


class CellInput(QWidget):
    """Space group, then a, b, c and alpha, beta, gamma.

    ``changed`` is emitted whenever the cell changes (once per edit, after
    the constrained boxes have followed). ``boxes`` holds the six
    parameter boxes by name, ``space_group_box`` the space group.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None, *, space_group: int = 1,
                 lengths=(4.0, 4.0, 4.0), angles=(90.0, 90.0, 90.0)):
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self.space_group_box = QSpinBox()
        self.space_group_box.setRange(1, 230)
        self.space_group_box.setValue(int(space_group))
        self.space_group_box.setKeyboardTracking(False)
        self.space_group_box.setToolTip(
            "The space group's number (1-230), entered first: it decides "
            "which of the cell parameters below are yours to set -- the "
            "others are greyed out and follow them.")
        form.addRow("Space group", self.space_group_box)
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        form.addRow("", self.info_label)

        self.boxes = {}
        row = QHBoxLayout()
        for name, value in zip(LENGTHS, lengths):
            box = QDoubleSpinBox()
            box.setDecimals(5)
            box.setRange(0.1, 200.0)
            box.setValue(float(value))
            box.setSuffix(" Å")
            box.setKeyboardTracking(False)
            row.addWidget(QLabel(name))
            row.addWidget(box)
            self.boxes[name] = box
        form.addRow("Lengths", row)
        row = QHBoxLayout()
        for name, value in zip(ANGLES, angles):
            box = QDoubleSpinBox()
            box.setDecimals(3)
            box.setRange(1.0, 179.0)
            box.setValue(float(value))
            box.setSuffix(" °")
            box.setKeyboardTracking(False)
            row.addWidget(QLabel(name))
            row.addWidget(box)
            self.boxes[name] = box
        form.addRow("Angles", row)

        self._mirrors = {}
        self.space_group_box.valueChanged.connect(self._space_group_changed)
        for name, box in self.boxes.items():
            box.valueChanged.connect(lambda *_: self._edited())
        self.apply_constraints()

    # -- the cell ------------------------------------------------------------
    def space_group(self) -> int:
        return int(self.space_group_box.value())

    def values(self) -> dict:
        """``{"a", "b", "c", "alpha", "beta", "gamma"}``, constraints met."""
        return {name: float(box.value()) for name, box in self.boxes.items()}

    def cell(self):
        """``(a, b, c, alpha, beta, gamma)``."""
        v = self.values()
        return tuple(v[n] for n in LENGTHS + ANGLES)

    def set_cell(self, space_group=None, a=None, b=None, c=None, alpha=None,
                 beta=None, gamma=None, *, emit: bool = True):
        """Fill the boxes (any left None keep theirs), then let the space
        group's constraints decide the dependent ones."""
        widgets = [self.space_group_box] + list(self.boxes.values())
        for widget in widgets:
            widget.blockSignals(True)
        try:
            if space_group:
                self.space_group_box.setValue(int(space_group))
            for name, value in zip(LENGTHS + ANGLES, (a, b, c, alpha, beta, gamma)):
                if value is not None:
                    self.boxes[name].setValue(float(value))
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self.apply_constraints(emit=emit)

    def setEnabled(self, enabled: bool):           # noqa: N802 (Qt's name)
        super().setEnabled(enabled)
        if enabled:
            self.apply_constraints(emit=False)

    # -- the constraints -----------------------------------------------------
    def apply_constraints(self, emit: bool = False):
        """Grey out and drive the parameters the space group fixes."""
        from arpes_viewer.tools.crystal.lattice import free_parameters
        from arpes_viewer.tools.crystal.spacegroups import spacegroup_info

        number = self.space_group()
        try:
            constraints = free_parameters(number)
            info = spacegroup_info(number)
            self.info_label.setText(
                f"{info.symbol} (#{info.number}), {info.crystal_system}, "
                f"centering {info.centering}: {constraints.note}")
        except Exception as exc:                          # noqa: BLE001
            self.info_label.setText(str(exc))
            return
        self._mirrors = dict(constraints.mirrors)
        for name in LENGTHS:
            self.boxes[name].setEnabled(name not in constraints.mirrors)
        for name in ANGLES:
            box = self.boxes[name]
            fixed = constraints.fixed_angles.get(name)
            box.setEnabled(fixed is None)
            if fixed is not None:
                box.blockSignals(True)
                box.setValue(float(fixed))
                box.blockSignals(False)
        self._follow()
        if emit:
            self.changed.emit()

    def _follow(self):
        for target, source in self._mirrors.items():
            box = self.boxes[target]
            box.blockSignals(True)
            box.setValue(self.boxes[source].value())
            box.blockSignals(False)

    def _space_group_changed(self, *_):
        self.apply_constraints(emit=True)

    def _edited(self):
        self._follow()
        self.changed.emit()
