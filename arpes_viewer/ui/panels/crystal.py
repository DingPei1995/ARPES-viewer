"""
ui/panels/crystal.py
====================
The crystal structure in real space, in 3-D, step by step.

Opened from the tool panel's Calculation tab (Crystal structure...). Four
steps, the picture beside them all the time:

1. **The structure** -- typed in like the Brillouin-zone tool's cell: the
   space group first, which fixes what the cell parameters may be, then
   the cell and the atoms of the basis; or filled from a CIF file with
   the push of a button.
2. **The look** -- how many cells, and for each element its colour, size,
   transparency and gloss; the cell edges and bonds.
3. **Cleavage plane** -- (hkl), slid along its normal or put on one of the
   atomic layers listed, with the atoms above it faded or hidden to show
   the termination a cleave would leave.
4. **Export** -- a picture at any size, or straight into the figure
   composer.

The crystal's Brillouin zone in 3-D, which was a step here, is a tool of
its own on the Basic tab (*3D BZ*, :mod:`ui.panels.bz3d`); it draws with
this module's :class:`CrystalView`.

Drawn with a plain ``QPainter`` -- shaded spheres, depth-sorted, the same
no-OpenGL approach as the 3-D data views (:mod:`ui.panels.volume`) -- so
the picture can be rendered at any size for a paper. The crystallography
is :mod:`tools.crystal.structure`, which imports no Qt.
"""
from __future__ import annotations

import os

import numpy as np
from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage,
                         QPainter, QPainterPath, QPen, QPolygonF,
                         QRadialGradient, QTransform)
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog,
                             QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                             QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
                             QInputDialog, QLabel, QLineEdit, QListWidget,
                             QPushButton,
                             QRadioButton, QSlider, QSpinBox, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from arpes_viewer.tools.crystal import last_crystal
from arpes_viewer.tools.crystal import structure as S
from arpes_viewer.tools.processing.volume import Camera
from arpes_viewer.ui.common.screen import fits_screen
from arpes_viewer.ui.common.stepper import Step, Stepper, guard_window

__all__ = ["CrystalDialog", "CrystalView", "picture_to_composer"]


def _blend(colour: QColor, other: QColor, f: float) -> QColor:
    f = float(np.clip(f, 0.0, 1.0))
    return QColor(int(colour.red() * (1 - f) + other.red() * f),
                  int(colour.green() * (1 - f) + other.green() * f),
                  int(colour.blue() * (1 - f) + other.blue() * f),
                  colour.alpha())


class CrystalView(QWidget):
    """The structure drawn in 3-D: drag to turn, wheel to zoom."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 420)
        self.structure = None
        self.repeats = (1, 1, 1)
        self.styles = {}
        self.atom_scale = 0.45
        self.show_cell = True
        self.show_bonds = True
        self.bond_factor = 1.15
        self.plane = None          # {"hkl", "offset", "colour", "alpha"}
        self.above = "show"        # "show", "fade" or "hide"
        self.mark_plane_atoms = True
        self.background = QColor("white")
        self.camera = Camera(azimuth=-35.0, elevation=28.0)
        self.zoom = 1.0
        self._drag = None
        #: coordination polyhedra: centre element -> {"colour", "alpha"}
        self.polyhedra = {}
        #: "real" (the crystal) or "zone" (its Brillouin zone)
        self.mode = "real"
        #: planes in the zone: [{"height", "colour", "alpha", "label"}],
        #: height along the plane normal (Å⁻¹) through the zone centre
        self.zone_planes = []
        self.zone_normal = (0.0, 0.0, 1.0)
        #: the labelled path drawn in the zone, e.g. ["Γ", "M", "K", "Γ"]
        self.zone_path = []
        #: more paths, each in its own colour:
        #: [{"labels": ["Γ", "M"], "colour": "#d62728", "width": 2.0}]
        self.zone_paths = []
        self.zone_labels = True
        self.zone_axes = True
        #: labels drawn at their leftmost symmetry-equivalent point (as the
        #: picture is turned), to keep them clear of the path and the axes
        self.zone_left_labels = set()
        self.font_px = 14.0
        #: a key of the elements' colours, and the cell's lengths on its edges
        self.show_legend = False
        self.show_lengths = False
        #: bonds in each atom's colour ("element") or one grey ("grey")
        self.bond_colour = "element"
        self.bond_width = 4.0

    # -- state -------------------------------------------------------------
    def set_structure(self, structure):
        self.structure = structure
        #: the CIF it was read from ("" when typed or from the zone tool)
        self.cif_path = ""
        for element in (structure.elements() if structure else []):
            self.styles.setdefault(element, {
                "colour": S.element_colour(element), "size": 1.0,
                "alpha": 1.0, "gloss": 0.6})
        self.update()

    def view_along(self, direction):
        """Turn the camera to look along ``direction`` (Cartesian)."""
        d = np.asarray(direction, dtype=float)
        d = d / (np.linalg.norm(d) or 1.0)
        self.camera.elevation = float(np.degrees(np.arcsin(np.clip(d[2], -1, 1))))
        self.camera.azimuth = float(np.degrees(np.arctan2(d[1], d[0])))
        self.update()

    # -- the scene ---------------------------------------------------------
    def _items(self):
        """Every primitive, in world coordinates: ("atom", centre, radius,
        style, marked), ("line", p, q, colour, width), ("tri", a, b, c,
        colour, alpha), ("text", point, text, colour) -- the texts drawn
        last, on top. An atom or line may carry a sixth entry, a depth
        bias towards the viewer."""
        items = []
        st = self.structure
        if st is None:
            return items, np.zeros((1, 3))
        if self.mode == "zone":
            return self._zone_items()
        atoms, xyz = S.cartesian_atoms(st, self.repeats)
        corners = np.array([p for edge in S.box_edges(st, self.repeats)
                            for p in edge])
        normal = offset = None
        if self.plane is not None:
            normal, _d = S.plane_normal(st, self.plane["hkl"])
            offset = self.plane["offset"]
        radii = np.array([S.covalent_radius(a.element) for a in atoms])
        shown = np.ones(len(atoms), dtype=bool)
        faded = np.ones(len(atoms))
        for index, (atom, centre, r) in enumerate(zip(atoms, xyz, radii)):
            style = dict(self.styles.get(atom.element, {}))
            marked = False
            if normal is not None:
                height = float(normal @ centre) - offset
                if height > 0.3:
                    if self.above == "hide":
                        shown[index] = False
                        continue
                    if self.above == "fade":
                        faded[index] = 0.15
                        style["alpha"] = style.get("alpha", 1.0) * 0.15
                marked = self.mark_plane_atoms and abs(height) <= 0.3
            items.append(("atom", centre, r * self.atom_scale * style.get("size", 1.0),
                          style, marked))
        if self.show_bonds and len(xyz) > 1:
            from scipy.spatial import cKDTree
            tree = cKDTree(xyz)
            reach = 2 * radii.max() * self.bond_factor
            for i, j in tree.query_pairs(reach):
                if not (shown[i] and shown[j]):
                    continue
                if (np.linalg.norm(xyz[i] - xyz[j])
                        <= (radii[i] + radii[j]) * self.bond_factor):
                    mid = 0.5 * (xyz[i] + xyz[j])
                    for end, k in ((xyz[i], i), (xyz[j], j)):
                        colour = QColor("#9a9a9a" if self.bond_colour == "grey"
                                        else self.styles.get(atoms[k].element, {}).get(
                                            "colour", "#888888"))
                        colour.setAlphaF(min(faded[i], faded[j]))
                        items.append(("line", end, mid, colour, self.bond_width))
        for element, look in self.polyhedra.items():
            for _centre, vertices, triangles in S.coordination_polyhedra(
                    st, element, self.repeats, self.bond_factor):
                edges = set()
                for tri in triangles:
                    a, b, c = vertices[tri]
                    for sub in _subdivide((a, b, c), 1):
                        items.append(("tri", *sub, look["colour"], look["alpha"]))
                    for i, j in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                        edges.add((min(i, j), max(i, j)))
                corners = np.vstack([corners, vertices])
                edge_colour = QColor(look["colour"]).darker(140)
                for i, j in edges:
                    items.append(("line", vertices[i], vertices[j], edge_colour, 1.0))
        if self.show_cell:
            for p, q in S.box_edges(st, self.repeats):
                for t0, t1 in zip(np.linspace(0, 1, 9)[:-1], np.linspace(0, 1, 9)[1:]):
                    items.append(("line", p + t0 * (q - p), p + t1 * (q - p),
                                  "#444444", 1.2))
        if self.plane is not None:
            outline = S.plane_outline(st, self.plane["hkl"], offset, self.repeats)
            if len(outline) >= 3:
                centre = outline.mean(axis=0)
                for k in range(len(outline)):
                    a, b = outline[k], outline[(k + 1) % len(outline)]
                    for tri in _subdivide((centre, a, b), 3):
                        items.append(("tri", *tri, self.plane["colour"],
                                      self.plane["alpha"]))
                    items.append(("line", a, b, self.plane["colour"], 2.0))
        return items, corners

    def zone(self):
        """``(params, b, zone, points)`` of the structure's Brillouin zone:
        the primitive reciprocal vectors, the Wigner-Seitz cell and the
        labelled high-symmetry points."""
        from arpes_viewer.tools.crystal.bz3d import wigner_seitz_cell
        from arpes_viewer.tools.crystal.highsym import high_symmetry_points
        from arpes_viewer.tools.crystal.lattice import primitive_vectors, reciprocal_vectors

        params = self.structure.lattice_params()
        b = reciprocal_vectors(primitive_vectors(params))
        return params, b, wigner_seitz_cell(b), high_symmetry_points(params)

    def _zone_items(self):
        from arpes_viewer.tools.crystal.bz3d import cut_points_3d, plane_cut

        items = []
        _params, b, zone, points = self.zone()
        lift = 0.03 * float(np.linalg.norm(b[0]))
        edges = set()
        for loop in zone.faces:
            for p, q in zip(loop[:-1], loop[1:]):
                key = tuple(sorted((tuple(np.round(p, 6)), tuple(np.round(q, 6)))))
                edges.add(key)
        for p, q in edges:
            p, q = np.array(p), np.array(q)
            for t0, t1 in zip(np.linspace(0, 1, 7)[:-1], np.linspace(0, 1, 7)[1:]):
                items.append(("line", p + t0 * (q - p), p + t1 * (q - p),
                              "#222222", 1.2, lift))
        for plane in self.zone_planes:
            # each plane may lie at its own (hkl); else the shared normal
            normal = np.asarray(plane.get("normal", self.zone_normal), dtype=float)
            normal = normal / (np.linalg.norm(normal) or 1.0)
            u, v = plane_cut(zone.faces, normal, normal * plane["height"])
            if u is None:
                continue
            outline = cut_points_3d(u[:-1], v[:-1], normal, normal * plane["height"])
            centre = outline.mean(axis=0)
            picture = plane.get("picture")
            if picture is not None:
                # a measured constant-energy map on the plane, cut to the zone
                image, x_range, y_range, turn = picture
                c, s_ = np.cos(np.deg2rad(turn)), np.sin(np.deg2rad(turn))
                h = normal * plane["height"]
                rect = [(x_range[0], y_range[0]), (x_range[1], y_range[0]),
                        (x_range[1], y_range[1]), (x_range[0], y_range[1])]
                corners3 = np.array([[c * x - s_ * y, s_ * x + c * y, 0.0]
                                     for x, y in rect]) + h
                items.append(("img", corners3, image, outline,
                              float(plane.get("picture_alpha", 0.92)), -1e6))
            for k in range(len(outline)):
                a, c = outline[k], outline[(k + 1) % len(outline)]
                if picture is None:
                    for tri in _subdivide((centre, a, c), 2):
                        # the planes go down first: lines and points lying in
                        # them would otherwise be cut by their triangles
                        items.append(("tri", *tri, plane["colour"], plane["alpha"],
                                      -1e6))
                items.append(("line", a, c, QColor(plane["colour"]).darker(130), 1.0))
        table = {p.label: np.asarray(p.k, dtype=float) for p in points}
        paths = list(self.zone_paths)
        if self.zone_path:
            paths.insert(0, {"labels": self.zone_path, "colour": "#d62728"})
        for drawn in paths:
            colour = drawn.get("colour", "#d62728")
            width = float(drawn.get("width", 2.0))
            # a "|" breaks the path: the next point starts a new segment
            segments, current = [], []
            for label in drawn.get("labels", ()):
                if label == "|":
                    segments.append(current)
                    current = []
                elif label in table:
                    current.append(table[label])
            segments.append(current)
            for path in segments:
                for p, q in zip(path[:-1], path[1:]):
                    for t0, t1 in zip(np.linspace(0, 1, 7)[:-1],
                                      np.linspace(0, 1, 7)[1:]):
                        items.append(("line", p + t0 * (q - p), p + t1 * (q - p),
                                      colour, width, 2 * lift))
        if self.zone_labels:
            for label, k in table.items():
                if label in self.zone_left_labels:
                    k = self._leftmost_equivalent(k)
                items.append(("atom", k, 0.025 * float(np.linalg.norm(b[0])),
                              {"colour": "#111111", "alpha": 1.0, "gloss": 0.0},
                              False, 3 * lift))
                items.append(("text", k, label, "#111111", 0.7))
        reach = 1.35 * float(np.max(np.abs(zone.vertices)))
        if self.zone_axes:
            for axis, name in ((0, "k_x"), (1, "k_y"), (2, "k_z")):
                end = np.zeros(3)
                end[axis] = reach
                items.append(("arrow", np.zeros(3), end, "#555555", 1.2))
                items.append(("text", end * 1.08, name, "#333333", 0.3))
        frame = np.asarray(zone.vertices, dtype=float)
        if self.zone_axes:
            frame = np.vstack([frame, 1.4 * np.eye(3) * reach])
        return items, frame

    def _leftmost_equivalent(self, k):
        """Of the points the crystal's rotation axis along k_z makes of
        ``k``, the one furthest left on the picture."""
        from arpes_viewer.tools.crystal.compare import in_plane_operations, symmetry_fold

        params = self.structure.lattice_params()
        fold = symmetry_fold(params.space_group or 1)
        right = self.camera.basis()[0]
        options = [np.concatenate([op @ k[:2], k[2:]])
                   for op in in_plane_operations(fold, mirror=False)]
        return min(options, key=lambda p: float(p @ right))

    def paint_into(self, painter: QPainter, width: int, height: int):
        painter.fillRect(0, 0, width, height, self.background)
        items, corners = self._items()
        if not items:
            painter.setPen(QColor("#888"))
            painter.drawText(0, 0, width, height, Qt.AlignCenter,
                             "No structure yet")
            return
        centre = corners.mean(axis=0)
        basis = self.camera.basis()
        projected = (corners - centre) @ basis[:2].T
        extent = float(np.max(np.abs(projected))) or 1.0
        scale = self.zoom * 0.42 * min(width, height) / extent

        def screen(point):
            p = (np.asarray(point) - centre)
            return QPointF(width / 2 + scale * float(p @ basis[0]),
                           height / 2 - scale * float(p @ basis[1]))

        def depth(point):
            return float((np.asarray(point) - centre) @ basis[2])

        texts = [item for item in items if item[0] == "text"]
        items = [item for item in items if item[0] != "text"]
        keyed = []
        for item in items:
            if item[0] == "atom":
                bias = item[5] if len(item) > 5 else 0.0
                keyed.append((depth(item[1]) + bias, item))
            elif item[0] in ("line", "arrow"):
                # an optional sixth entry lifts a line towards the viewer, so
                # one lying in a translucent plane is not cut into dashes
                bias = item[5] if len(item) > 5 else 0.0
                keyed.append((depth(0.5 * (item[1] + item[2])) + bias, item))
            elif item[0] == "img":
                keyed.append((depth(np.mean(item[1], axis=0)) + item[5], item))
            else:
                bias = item[6] if len(item) > 6 else 0.0
                keyed.append((depth((item[1] + item[2] + item[3]) / 3) + bias, item))
        keyed.sort(key=lambda pair: pair[0])
        painter.setRenderHint(QPainter.Antialiasing, True)
        for _d, item in keyed:
            if item[0] == "atom":
                _k, c, r, style, marked = item[:5]
                self._paint_atom(painter, screen(c), r * scale, style, marked)
            elif item[0] == "img":
                self._paint_picture(painter, item, screen)
            elif item[0] == "arrow":
                _k, p, q, colour, w = item[:5]
                self._paint_arrow(painter, screen(p), screen(q), QColor(colour),
                                  w * max(1.0, scale / 60.0))
            elif item[0] == "line":
                _k, p, q, colour, w = item[:5]
                pen = QPen(QColor(colour), w * max(1.0, scale / 60.0))
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(screen(p), screen(q))
            else:
                _k, a, b, c, colour, alpha = item[:6]
                fill = QColor(colour)
                fill.setAlphaF(float(alpha))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(fill))
                painter.drawPolygon(QPolygonF([screen(a), screen(b), screen(c)]))
        font = painter.font()
        font.setPixelSize(max(8, int(round(self.font_px * min(width, height) / 600))))
        font.setItalic(False)
        painter.setFont(font)
        for item in texts:
            _k, point, text, colour = item[:4]
            at = screen(point)
            painter.setPen(QColor(colour))
            self._draw_label(painter, at, text, *(item[4:5]))
        if self.mode == "real" and self.structure is not None:
            if self.show_lengths:
                self._paint_lengths(painter, screen, corners)
            if self.show_legend:
                self._paint_legend(painter, width, height, scale)

    @staticmethod
    def _paint_picture(painter, item, screen):
        """A picture on a plane: an affine map of its pixels onto the
        projected rectangle, clipped to the zone's outline on that plane."""
        _k, corners, image, outline, alpha, _bias = item
        p = [screen(c) for c in corners]
        w, h = image.width(), image.height()
        du = ((p[1].x() - p[0].x()) / w, (p[1].y() - p[0].y()) / w)
        dv = ((p[3].x() - p[0].x()) / h, (p[3].y() - p[0].y()) / h)
        clip = QPainterPath()
        clip.addPolygon(QPolygonF([screen(c) for c in outline]))
        clip.closeSubpath()
        painter.save()
        painter.setClipPath(clip)
        painter.setOpacity(alpha)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setTransform(QTransform(du[0], du[1], dv[0], dv[1],
                                        p[0].x(), p[0].y()), True)
        painter.drawImage(QRectF(0, 0, w, h), image)
        painter.restore()

    def _paint_lengths(self, painter, screen, corners):
        """``a = 3.52 Å`` beside the cell's a edge, ``c = ...`` beside its c
        edge (and b when it differs from a): the cell's size on the
        picture, as a structure figure labels it."""
        st = self.structure
        vectors = st.vectors()
        middle = screen(corners.mean(axis=0))
        names = [("a", st.a), ("b", st.b), ("c", st.c)]
        shown = [0, 2] if abs(st.a - st.b) < 1e-6 else [0, 1, 2]
        metrics = QFontMetricsF(painter.font())
        painter.setPen(QColor("#222222"))
        for index in shown:
            p, q = screen(np.zeros(3)), screen(vectors[index])
            mid = QPointF(0.5 * (p.x() + q.x()), 0.5 * (p.y() + q.y()))
            away = np.array([mid.x() - middle.x(), mid.y() - middle.y()])
            away = away / (np.linalg.norm(away) or 1.0)
            name, value = names[index]
            text = f"{name} = {value:.3g} Å"
            w, h = metrics.horizontalAdvance(text), metrics.height()
            # the text's centre clear of the edge by its own half-size
            reach = 0.9 * h + 0.5 * (abs(away[0]) * w + abs(away[1]) * h)
            cx, cy = mid.x() + away[0] * reach, mid.y() + away[1] * reach
            # _draw_label starts 0.35 em right of and above the point it gets
            self._draw_label(painter, QPointF(cx - 0.5 * w - 0.35 * painter.font().pixelSize(),
                                              cy + 0.35 * h), text)

    def _paint_legend(self, painter, width, height, scale):
        """A ball in each element's colour, and its name."""
        elements = self.structure.elements()
        metrics = QFontMetricsF(painter.font())
        line = 1.7 * metrics.height()
        radius = 0.55 * metrics.height()
        x = 0.04 * width + radius
        y = height - 0.04 * height - line * (len(elements) - 1) - radius
        for element in elements:
            style = dict(self.styles.get(element, {}), alpha=1.0)
            self._paint_atom(painter, QPointF(x, y), radius, style, False)
            painter.setPen(QColor("#222222"))
            painter.drawText(QPointF(x + 1.8 * radius, y + 0.35 * metrics.height()),
                             element)
            y += line

    @staticmethod
    def _paint_arrow(painter, start: QPointF, end: QPointF, colour, width):
        """A line with a filled head at ``end``."""
        dx, dy = end.x() - start.x(), end.y() - start.y()
        length = float(np.hypot(dx, dy))
        if length < 1e-6:
            return
        ux, uy = dx / length, dy / length
        head = max(6.0, 4.5 * width)
        base = QPointF(end.x() - ux * head, end.y() - uy * head)
        pen = QPen(colour, width)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)
        painter.drawLine(start, base)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(colour))
        nx, ny = -uy * head * 0.38, ux * head * 0.38
        painter.drawPolygon(QPolygonF([end, QPointF(base.x() + nx, base.y() + ny),
                                       QPointF(base.x() - nx, base.y() - ny)]))
        painter.setBrush(Qt.NoBrush)

    @staticmethod
    def _draw_label(painter, at: QPointF, text: str, offset_em: float = 0.35):
        """A label beside a point, with "k_x"-style subscripts, ``offset_em``
        (of the font size) right of and above it."""
        from arpes_viewer.tools.output.figure import parse_markup

        x = at.x() + offset_em * painter.font().pixelSize()
        y = at.y() - offset_em * painter.font().pixelSize()
        base = painter.font()
        colour = painter.pen().color()
        outline = QPainterPath()
        for run, kind in parse_markup(text):
            font = QFont(base)
            font.setPixelSize(max(6, int(base.pixelSize() * (0.7 if kind != "base" else 1.0))))
            offset = {"sub": 0.3, "super": -0.45}.get(kind, 0.0) * base.pixelSize()
            outline.addText(QPointF(x, y + offset), font, run)
            x += QFontMetricsF(font).horizontalAdvance(run)
        # a white halo keeps the label legible over lines and planes
        halo = QPen(QColor(255, 255, 255, 220), max(2.0, base.pixelSize() / 6))
        halo.setJoinStyle(Qt.RoundJoin)
        painter.strokePath(outline, halo)
        painter.fillPath(outline, colour)

    @staticmethod
    def _paint_atom(painter, centre: QPointF, radius: float, style, marked):
        """A shaded ball: diffuse light from the upper left falling off to
        a dark rim, a soft ambient floor, and -- with gloss -- a sharp
        specular spot and a faint reflected rim, so a glossy ball reads as
        glossy and a matt one as chalk. Transparency applies to all of it."""
        if radius <= 0.3:
            return
        base = QColor(style.get("colour", "#999999"))
        alpha = float(np.clip(style.get("alpha", 1.0), 0.0, 1.0))
        gloss = float(np.clip(style.get("gloss", 0.6), 0.0, 1.0))
        light = QPointF(centre.x() - 0.35 * radius, centre.y() - 0.4 * radius)
        diffuse = QRadialGradient(light, 1.45 * radius)
        lit = _blend(base, QColor("white"), 0.18 + 0.12 * (1 - gloss))
        dark = base.darker(185)
        for at, colour in ((0.0, lit), (0.45, base), (0.85, base.darker(135)),
                           (1.0, dark)):
            colour = QColor(colour)
            colour.setAlphaF(alpha)
            diffuse.setColorAt(at, colour)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(diffuse))
        painter.drawEllipse(centre, radius, radius)
        if gloss > 0.02:
            # light bounced back off the floor, on the lower right rim
            rim = QRadialGradient(QPointF(centre.x() + 0.45 * radius,
                                          centre.y() + 0.5 * radius), 0.75 * radius)
            bounce = _blend(base, QColor("white"), 0.35)
            bounce.setAlphaF(0.35 * gloss * alpha)
            clear = QColor(bounce)
            clear.setAlphaF(0.0)
            rim.setColorAt(0.0, bounce)
            rim.setColorAt(1.0, clear)
            painter.setBrush(QBrush(rim))
            painter.drawEllipse(centre, radius, radius)
            # the specular spot: small and sharp when glossy
            spot_r = radius * (0.5 - 0.25 * gloss)
            spot = QRadialGradient(QPointF(centre.x() - 0.38 * radius,
                                           centre.y() - 0.42 * radius), spot_r)
            white = QColor(255, 255, 255)
            white.setAlphaF(min(1.0, 0.95 * gloss) * max(alpha, 0.35))
            none = QColor(255, 255, 255, 0)
            spot.setColorAt(0.0, white)
            spot.setColorAt(0.35 + 0.3 * (1 - gloss), QColor(255, 255, 255,
                                                           int(90 * gloss * alpha)))
            spot.setColorAt(1.0, none)
            painter.setBrush(QBrush(spot))
            painter.drawEllipse(spot.center(), spot_r, spot_r)
        painter.setBrush(Qt.NoBrush)
        if marked:
            painter.setPen(QPen(QColor("#e0302a"), max(1.5, radius * 0.12)))
        else:
            painter.setPen(QPen(QColor(0, 0, 0, int(70 * alpha)), max(0.6, radius * 0.03)))
        painter.drawEllipse(centre, radius, radius)

    def render_image(self, width: int, height: int, background=None) -> QImage:
        image = QImage(int(width), int(height), QImage.Format_ARGB32)
        image.fill(background or self.background)
        painter = QPainter(image)
        try:
            self.paint_into(painter, int(width), int(height))
        finally:
            painter.end()
        return image

    # -- Qt ----------------------------------------------------------------
    def paintEvent(self, _event):
        painter = QPainter(self)
        try:
            self.paint_into(painter, self.width(), self.height())
        finally:
            painter.end()

    def mousePressEvent(self, event):
        self._drag = (event.pos(), self.camera.azimuth, self.camera.elevation)

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return
        start, az, el = self._drag
        delta = event.pos() - start
        self.camera.azimuth = az - 0.5 * delta.x()
        self.camera.elevation = float(np.clip(el + 0.5 * delta.y(), -89.0, 89.0))
        self.update()

    def mouseReleaseEvent(self, _event):
        self._drag = None

    def wheelEvent(self, event):
        self.zoom *= 1.1 ** (event.angleDelta().y() / 120.0)
        self.zoom = float(np.clip(self.zoom, 0.2, 8.0))
        self.update()


def _subdivide(triangle, levels: int):
    """A triangle split into 4**levels smaller ones (for depth sorting)."""
    out = [tuple(np.asarray(p, dtype=float) for p in triangle)]
    for _ in range(levels):
        nxt = []
        for a, b, c in out:
            ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
            nxt += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
        out = nxt
    return out


class _ColourButton(QPushButton):
    colourChanged = pyqtSignal(str)

    def __init__(self, colour: str):
        super().__init__("")
        self.colour = colour
        self.setFixedWidth(46)
        self._show()
        self.clicked.connect(self._pick)

    def _show(self):
        self.setStyleSheet(f"background-color: {self.colour}; border: 1px "
                           f"solid #888;")

    def _pick(self):
        chosen = QColorDialog.getColor(QColor(self.colour), self, "Colour")
        if chosen.isValid():
            self.set_colour(chosen.name())

    def set_colour(self, colour: str):
        self.colour = colour
        self._show()
        self.colourChanged.emit(colour)


@fits_screen
class CrystalDialog(QDialog):
    """The crystal structure viewer."""

    def __init__(self, parent=None, datasets=None, colormap="blue", flip=True):
        super().__init__(parent)
        self.setWindowTitle("Crystal structure")
        self.resize(1200, 760)
        self.structure = None
        #: k-maps whose constant-energy pictures can lie on the zone's planes
        self.datasets = [(n, d) for n, d in (datasets or [])
                         if getattr(d, "kind", None) == "k_map"]
        self.colormap, self.flip = colormap, flip
        self.view = CrystalView(self)
        layout = QHBoxLayout(self)
        self.stepper = Stepper([self._step_structure(), self._step_look(),
                                self._step_plane(), self._step_export()], self,
                               finish_text="Close", show_index=False)
        self.stepper.setMinimumWidth(470)
        self.stepper.stepChanged.connect(self._step_shown)
        layout.addWidget(self.stepper, 2)
        right = QVBoxLayout()
        right.addWidget(self.view, 1)
        views = QHBoxLayout()
        views.addWidget(QLabel("<i>drag to turn, wheel to zoom</i>  View along:"))
        for text, which in (("a", 0), ("b", 1), ("c", 2), ("plane normal", None)):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, w=which: self.look_along(w))
            views.addWidget(button)
        views.addStretch(1)
        right.addLayout(views)
        layout.addLayout(right, 3)
        guard_window(self, self.stepper, "crystal_structure", "Crystal structure",
                     close_on_finish=True)
        self.manual_changed()

    # ==================================================================
    # Step 1: the structure
    # ==================================================================
    def _step_structure(self):
        from arpes_viewer.ui.common.cellinput import CellInput

        page = QWidget()
        column = QVBoxLayout(page)

        # Typed in, as the Brillouin-zone tool takes a cell: the space group
        # first, which greys out the parameters it fixes.
        cell = QGroupBox("Cell (space group first)")
        cell_layout = QVBoxLayout(cell)
        self.cell_input = CellInput(cell)
        cell_layout.addWidget(self.cell_input)
        self.cell_boxes = self.cell_input.boxes
        self.space_group = self.cell_input.space_group_box
        self.cell_input.changed.connect(self.manual_changed)
        self.centering_label = self.cell_input.info_label
        column.addWidget(cell)

        atoms = QGroupBox("Atoms of the basis (fractional coordinates; the "
                          "space group's copies are added)")
        atoms_column = QVBoxLayout(atoms)
        self.atom_table = QTableWidget(0, 4)
        self.atom_table.setHorizontalHeaderLabels(["Element", "x", "y", "z"])
        self.atom_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.atom_table.itemChanged.connect(self.manual_changed)
        atoms_column.addWidget(self.atom_table)
        buttons = QHBoxLayout()
        add = QPushButton("Add atom")
        add.clicked.connect(lambda: self.add_atom("X", 0, 0, 0))
        remove = QPushButton("Remove atom")
        remove.clicked.connect(self.remove_atom)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        atoms_column.addLayout(buttons)
        column.addWidget(atoms, 1)

        self.cif_button = QPushButton("Read a CIF file...")
        self.cif_button.setToolTip(
            "Fill the space group, the cell and the atoms above from a CIF "
            "(ICSD, COD, Materials Project, FullProf...), with its own "
            "symmetry operations; the crystal is redrawn at once. Everything "
            "can still be edited afterwards.")
        self.cif_button.clicked.connect(lambda: self.read_cif())
        column.addWidget(self.cif_button)
        self.structure_label = QLabel("")
        self.structure_label.setWordWrap(True)
        column.addWidget(self.structure_label)
        #: a CIF's symmetry operations, for its own space group
        self._cif_operations = None
        self._cif_number = 0
        self._cif_name = ""
        self.cif_path = ""
        self.add_atom("X", 0, 0, 0)
        text = ("The crystal, typed in: the <b>space group</b> first -- it "
                "decides which cell parameters are free, and the others "
                "follow -- then the <b>cell</b> and the <b>atoms</b> of the "
                "basis, to which the space group's centering copies are "
                "added. <b>Read a CIF file</b> fills all of it from a file, "
                "with the file's full symmetry.")
        return Step("The structure", text, page,
                    ready=lambda: "" if self.structure is not None and
                    self.structure.atoms else "No atoms yet.")

    def add_atom(self, element, x, y, z, occupancy: float = 1.0):
        self._put_atom(element, (x, y, z), occupancy)
        self.manual_changed()

    def _put_atom(self, element, frac, occupancy: float = 1.0):
        self.atom_table.blockSignals(True)
        row = self.atom_table.rowCount()
        self.atom_table.insertRow(row)
        for column, value in enumerate((element,) + tuple(frac)):
            item = QTableWidgetItem(str(value) if column == 0
                                    else f"{float(value):.6g}")
            if column == 0:
                item.setData(Qt.UserRole, float(occupancy))
            self.atom_table.setItem(row, column, item)
        self.atom_table.blockSignals(False)

    def remove_atom(self):
        row = self.atom_table.currentRow()
        if row >= 0:
            self.atom_table.removeRow(row)
            self.manual_changed()

    def _table_atoms(self):
        atoms = []
        for row in range(self.atom_table.rowCount()):
            try:
                cell = self.atom_table.item(row, 0)
                element = S.element_of(cell.text())
                frac = tuple(float(self.atom_table.item(row, c).text())
                             for c in (1, 2, 3))
            except (AttributeError, ValueError):
                continue
            occupancy = cell.data(Qt.UserRole)
            atoms.append(S.Atom(f"{element}{row + 1}", element, frac,
                                1.0 if occupancy is None else float(occupancy)))
        return atoms

    def _operations(self):
        """The CIF's own operations while its space group is kept; else the
        centering translations of the space group typed."""
        from arpes_viewer.tools.crystal.spacegroups import spacegroup_info
        number = self.cell_input.space_group()
        if self._cif_operations and number == self._cif_number:
            return self._cif_operations
        centering = spacegroup_info(number).centering
        return [(np.eye(3), np.asarray(t, dtype=float))
                for t in S.CENTERING_TRANSLATIONS.get(centering, [(0, 0, 0)])]

    def manual_changed(self, *_):
        if not hasattr(self, "cell_input"):
            return
        number = self.cell_input.space_group()
        a, b, c, alpha, beta, gamma = self.cell_input.cell()
        own = bool(self._cif_operations) and number == self._cif_number
        structure = S.Structure(
            a, b, c, alpha, beta, gamma,
            atoms=S.expand(self._table_atoms(), self._operations()),
            name=self._cif_name if own else "", space_group=str(number),
            space_group_number=number)
        if not structure.name:
            structure.name = structure.formula()
        self.set_structure(structure)

    def _settings_applied(self):
        self.cell_input.apply_constraints()
        self.manual_changed()

    def read_cif(self, path=None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "CIF file", "",
                                                  "CIF (*.cif);;All files (*)")
            if not path:
                return None
        try:
            structure = S.read_cif(path)
        except (OSError, ValueError, UnicodeError) as exc:
            self.structure_label.setText(f"<b>Could not read it:</b> {exc}")
            return None
        number = structure.space_group_number or 1
        self._cif_operations = list(structure.operations) or None
        self._cif_number = number
        self._cif_name = structure.name
        cell = (structure.a, structure.b, structure.c, structure.alpha,
                structure.beta, structure.gamma)
        # the inputs show what was read, and the crystal is drawn from them
        self.cell_input.set_cell(number, *cell, emit=False)
        if any(abs(v - w) > 1e-6 for v, w in zip(self.cell_input.cell(), cell)):
            # a setting the constraints do not describe (rhombohedral axes,
            # say): keep the file's cell as it is
            for name, value in zip(("a", "b", "c", "alpha", "beta", "gamma"), cell):
                box = self.cell_boxes[name]
                box.blockSignals(True)
                box.setValue(value)
                box.blockSignals(False)
        self.atom_table.blockSignals(True)
        self.atom_table.setRowCount(0)
        self.atom_table.blockSignals(False)
        for site in (structure.sites or structure.atoms):
            self._put_atom(site.element, site.frac, site.occupancy)
        self.manual_changed()
        self.cif_path = os.path.abspath(path)
        built = self.structure
        self.structure_label.setText(
            f"Read {os.path.basename(path)}: {structure.name} "
            f"({built.formula()}), {structure.space_group or '?'} "
            f"(#{number}): a = {structure.a:.4g}, b = {structure.b:.4g}, "
            f"c = {structure.c:.4g} Å, {structure.alpha:.4g}/"
            f"{structure.beta:.4g}/{structure.gamma:.4g}°; "
            f"{len(built.atoms)} atoms in the cell.")
        return built

    def set_structure(self, structure):
        self.structure = structure
        self.view.set_structure(structure)
        if hasattr(self, "style_table"):
            self._fill_styles()
            self._plane_changed()
        if hasattr(self, "stepper"):
            self.stepper.refresh()

    # ==================================================================
    # Step 2: the look
    # ==================================================================
    def _step_look(self):
        page = QWidget()
        column = QVBoxLayout(page)
        form = QFormLayout()
        repeat_row = QHBoxLayout()
        self.repeat_boxes = []
        for name in ("a", "b", "c"):
            box = QSpinBox()
            box.setRange(1, 8)
            box.setValue(1)
            box.valueChanged.connect(self._look_changed)
            repeat_row.addWidget(QLabel(f"× {name}"))
            repeat_row.addWidget(box)
            self.repeat_boxes.append(box)
        form.addRow("Cells", repeat_row)
        self.scale_box = QDoubleSpinBox()
        self.scale_box.setRange(0.05, 2.0)
        self.scale_box.setSingleStep(0.05)
        self.scale_box.setValue(0.45)
        self.scale_box.setToolTip("All atoms' radii, as a fraction of the "
                                  "covalent radius (1 = touching neighbours).")
        self.scale_box.valueChanged.connect(self._look_changed)
        form.addRow("Atom size", self.scale_box)
        self.cell_box = QCheckBox("Cell edges")
        self.cell_box.setChecked(True)
        self.bond_box = QCheckBox("Bonds (atoms closer than 1.15 x the sum of "
                                  "their covalent radii)")
        self.bond_box.setChecked(True)
        self.bond_grey = QCheckBox("Grey, thin bonds (not in the atoms' colours)")
        self.legend_box = QCheckBox("Key of the elements")
        self.lengths_box = QCheckBox("Lattice constants on the cell edges")
        for box in (self.cell_box, self.bond_box, self.bond_grey,
                    self.legend_box, self.lengths_box):
            box.toggled.connect(self._look_changed)
            form.addRow(box)
        self.background_combo = QComboBox()
        self.background_combo.addItems(["White", "Black", "Transparent"])
        self.background_combo.currentIndexChanged.connect(self._look_changed)
        form.addRow("Background", self.background_combo)
        poly = QHBoxLayout()
        self.poly_combo = QComboBox()
        self.poly_combo.setToolTip("Draw the coordination polyhedron around "
                                   "every atom of this element (its bonded "
                                   "neighbours as corners) -- the CuS4 "
                                   "tetrahedra, the TiSe6 octahedra.")
        self.poly_combo.currentIndexChanged.connect(self._look_changed)
        poly.addWidget(self.poly_combo, 1)
        self.poly_colour = _ColourButton("#8fc3e8")
        self.poly_colour.colourChanged.connect(self._look_changed)
        poly.addWidget(self.poly_colour)
        self.poly_alpha = QSpinBox()
        self.poly_alpha.setRange(0, 100)
        self.poly_alpha.setValue(45)
        self.poly_alpha.setSuffix(" % transparent")
        self.poly_alpha.valueChanged.connect(self._look_changed)
        poly.addWidget(self.poly_alpha)
        form.addRow("Polyhedra around", poly)
        column.addLayout(form)
        self.style_table = QTableWidget(0, 5)
        self.style_table.setHorizontalHeaderLabels(
            ["Element", "Colour", "Size ×", "Transparency %", "Gloss %"])
        self.style_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.style_table.setSelectionMode(QAbstractItemView.NoSelection)
        column.addWidget(self.style_table, 1)
        text = ("How it looks. Repeat the cell along a, b and c, set the "
                "atoms' overall size, choose an element to draw "
                "<b>coordination polyhedra</b> around (its bonded neighbours "
                "as corners), and for each element its "
                "<b>colour</b>, <b>size</b>, <b>transparency</b> and "
                "<b>gloss</b> (0 % a matt ball, 100 % a shiny one). Drag the "
                "picture to turn it, scroll to zoom; the buttons under it "
                "look straight along a, b, c or a plane's normal.")
        return Step("The look", text, page, enter=self._fill_styles)

    def _fill_styles(self):
        table = self.style_table
        elements = self.structure.elements() if self.structure else []
        current = self.poly_combo.currentText()
        self.poly_combo.blockSignals(True)
        self.poly_combo.clear()
        self.poly_combo.addItems(["(none)"] + elements)
        if current in elements:
            self.poly_combo.setCurrentText(current)
        self.poly_combo.blockSignals(False)
        table.setRowCount(len(elements))
        for row, element in enumerate(elements):
            style = self.view.styles.setdefault(element, {
                "colour": S.element_colour(element), "size": 1.0,
                "alpha": 1.0, "gloss": 0.6})
            table.setItem(row, 0, QTableWidgetItem(element))
            colour = _ColourButton(style["colour"])
            colour.colourChanged.connect(
                lambda c, e=element: self.set_style(e, colour=c))
            table.setCellWidget(row, 1, colour)
            for column, key, lo, hi, factor in ((2, "size", 0.1, 5.0, 1.0),
                                                (3, "alpha", 0, 100, None),
                                                (4, "gloss", 0, 100, 100.0)):
                box = QDoubleSpinBox()
                box.setRange(lo, hi)
                if key == "alpha":
                    box.setValue(100.0 * (1.0 - style["alpha"]))
                    box.valueChanged.connect(
                        lambda v, e=element: self.set_style(e, alpha=1 - v / 100.0))
                elif key == "gloss":
                    box.setValue(100.0 * style["gloss"])
                    box.valueChanged.connect(
                        lambda v, e=element: self.set_style(e, gloss=v / 100.0))
                else:
                    box.setSingleStep(0.1)
                    box.setValue(style["size"])
                    box.valueChanged.connect(
                        lambda v, e=element: self.set_style(e, size=v))
                table.setCellWidget(row, column, box)

    def set_style(self, element, **values):
        self.view.styles.setdefault(element, {}).update(values)
        self.view.update()

    def _look_changed(self, *_):
        self.view.repeats = tuple(box.value() for box in self.repeat_boxes)
        self.view.atom_scale = self.scale_box.value()
        self.view.show_cell = self.cell_box.isChecked()
        self.view.show_bonds = self.bond_box.isChecked()
        self.view.bond_colour = "grey" if self.bond_grey.isChecked() else "element"
        self.view.bond_width = 2.0 if self.bond_grey.isChecked() else 4.0
        self.view.show_legend = self.legend_box.isChecked()
        self.view.show_lengths = self.lengths_box.isChecked()
        self.view.background = QColor(
            ("white", "black", "transparent")[self.background_combo.currentIndex()])
        if self.background_combo.currentIndex() == 2:
            self.view.background = QColor(0, 0, 0, 0)
        centre = self.poly_combo.currentText()
        self.view.polyhedra = ({} if centre in ("", "(none)") else {
            centre: {"colour": self.poly_colour.colour,
                     "alpha": 1.0 - self.poly_alpha.value() / 100.0}})
        if hasattr(self, "plane_box"):
            self._plane_changed()
        self.view.update()

    # ==================================================================
    # Step 3: the cleavage plane
    # ==================================================================
    def _step_plane(self):
        page = QWidget()
        column = QVBoxLayout(page)
        form = QFormLayout()
        self.plane_box = QCheckBox("Draw a plane")
        self.plane_box.toggled.connect(self._plane_changed)
        form.addRow(self.plane_box)
        hkl = QHBoxLayout()
        self.hkl_boxes = []
        for name, value in (("h", 0), ("k", 0), ("l", 1)):
            box = QSpinBox()
            box.setRange(-9, 9)
            box.setValue(value)
            box.valueChanged.connect(self._plane_changed)
            hkl.addWidget(QLabel(name))
            hkl.addWidget(box)
            self.hkl_boxes.append(box)
        form.addRow("Miller indices", hkl)
        self.offset_slider = QSlider(Qt.Horizontal)
        self.offset_slider.setRange(0, 1000)
        self.offset_slider.setValue(500)
        self.offset_slider.valueChanged.connect(self._offset_moved)
        self.offset_label = QLabel("")
        offset_row = QHBoxLayout()
        offset_row.addWidget(self.offset_slider, 1)
        offset_row.addWidget(self.offset_label)
        form.addRow("Position", offset_row)
        self.above_combo = QComboBox()
        self.above_combo.addItems(["Show the atoms above it", "Fade them",
                                   "Hide them (the cleaved surface)"])
        self.above_combo.currentIndexChanged.connect(self._plane_changed)
        form.addRow("Above the plane", self.above_combo)
        look = QHBoxLayout()
        self.plane_colour = _ColourButton("#3a7bd5")
        self.plane_colour.colourChanged.connect(self._plane_changed)
        look.addWidget(self.plane_colour)
        self.plane_alpha = QSpinBox()
        self.plane_alpha.setRange(0, 100)
        self.plane_alpha.setValue(65)
        self.plane_alpha.setSuffix(" % transparent")
        self.plane_alpha.valueChanged.connect(self._plane_changed)
        look.addWidget(self.plane_alpha)
        form.addRow("Plane colour", look)
        column.addLayout(form)
        column.addWidget(QLabel("Atomic layers parallel to the plane "
                                "(double-click to put the plane on one):"))
        self.layer_list = QListWidget()
        self.layer_list.itemDoubleClicked.connect(
            lambda item: self.set_plane_height(item.data(Qt.UserRole)))
        column.addWidget(self.layer_list, 1)
        self.plane_label = QLabel("")
        self.plane_label.setWordWrap(True)
        column.addWidget(self.plane_label)
        text = ("A <b>cleavage plane</b> (hkl): tick <b>Draw</b> and give its "
                "Miller indices (in the cell above). Slide it along its "
                "normal, or double-click one of the <b>atomic layers</b> to "
                "put it exactly there -- each line says which atoms that "
                "layer holds, so the possible terminations of a cleave read "
                "off the list. <b>Hide the atoms above</b> to see the surface "
                "the cleave would leave; atoms in the plane are ringed red.")
        return Step("Cleavage plane", text, page, enter=self._plane_changed)

    def hkl(self):
        return tuple(box.value() for box in self.hkl_boxes)

    def _plane_range(self):
        return S.offset_range(self.structure, self.hkl(), self.view.repeats)

    def plane_height(self):
        lo, hi = self._plane_range()
        return lo + (hi - lo) * self.offset_slider.value() / 1000.0

    def set_plane_height(self, height):
        lo, hi = self._plane_range()
        self.offset_slider.setValue(int(round(1000 * (height - lo) / ((hi - lo) or 1))))
        self._plane_changed()

    def _offset_moved(self, *_):
        self._plane_changed(rebuild_layers=False)

    def _plane_changed(self, *_, rebuild_layers=True):
        if self.structure is None or not any(self.hkl()):
            self.view.plane = None
            self.view.update()
            return
        on = self.plane_box.isChecked()
        try:
            _normal, d = S.plane_normal(self.structure, self.hkl())
        except ValueError as exc:
            self.plane_label.setText(str(exc))
            return
        height = self.plane_height()
        self.offset_label.setText(f"{height:.3f} Å")
        self.view.plane = ({"hkl": self.hkl(), "offset": height,
                            "colour": self.plane_colour.colour,
                            "alpha": 1.0 - self.plane_alpha.value() / 100.0}
                           if on else None)
        self.view.above = ("show", "fade", "hide")[self.above_combo.currentIndex()]
        if rebuild_layers:
            self.layer_list.clear()
            for h, counts in S.atomic_layers(self.structure, self.hkl(),
                                             self.view.repeats):
                text = ", ".join(f"{e}{'' if n == 1 else f' x{n}'}"
                                 for e, n in counts.items())
                self.layer_list.addItem(f"{h:8.3f} Å   {text}")
                self.layer_list.item(self.layer_list.count() - 1).setData(
                    Qt.UserRole, h)
        self.plane_label.setText(f"d({' '.join(map(str, self.hkl()))}) = {d:.4f} Å")
        self.view.update()

    def look_along(self, which):
        if self.structure is None:
            return
        if which is None:
            if any(self.hkl()):
                normal, _d = S.plane_normal(self.structure, self.hkl())
                self.view.view_along(normal)
            return
        self.view.view_along(self.structure.vectors()[which])

    # ==================================================================
    # Step 4: the Brillouin zone
    # ==================================================================
    def _step_shown(self, index):
        self.view.mode = "real"
        self.view.update()

    # ==================================================================
    # Step 4: export
    # ==================================================================
    def _step_export(self):
        page = QWidget()
        form = QFormLayout(page)
        size = QHBoxLayout()
        self.width_box = QSpinBox()
        self.height_box = QSpinBox()
        for box, value in ((self.width_box, 1600), (self.height_box, 1600)):
            box.setRange(100, 12000)
            box.setValue(value)
            box.setSingleStep(100)
            size.addWidget(box)
        form.addRow("Size (px)", size)
        save = QPushButton("Save picture...")
        save.clicked.connect(lambda: self.save_picture())
        form.addRow(save)
        compose = QPushButton("To figure composer...")
        compose.setToolTip("Add the picture as a panel of a figure composer "
                           "that is open, or of a new one.")
        compose.clicked.connect(lambda: self.to_figure_composer())
        form.addRow(compose)
        self.export_label = QLabel("")
        self.export_label.setWordWrap(True)
        form.addRow(self.export_label)
        text = ("The picture as it is shown, at the size you choose -- it is "
                "drawn again at that size, not enlarged. <b>Save picture</b> "
                "writes a PNG (transparent if the background is). <b>To "
                "figure composer</b> puts it on a figure page beside your "
                "data, where it is labelled and arranged like any panel.")
        return Step("Export", text, page, enter=lambda: self._step_shown(3))

    def picture(self):
        return self.view.render_image(self.width_box.value(),
                                      self.height_box.value())

    def save_picture(self, path=None):
        if path is None:
            name = (self.structure.name if self.structure else "") or "crystal"
            path, _ = QFileDialog.getSaveFileName(
                self, "Save picture", f"{name}.png", "PNG (*.png)")
            if not path:
                return None
        if not path.lower().endswith(".png"):
            path += ".png"
        self.picture().save(path, "PNG")
        self.export_label.setText(f"Wrote {path}.")
        return path

    def to_figure_composer(self, target=None, ask=True):
        name = (self.structure.name if self.structure else "") or "crystal"
        sources = None
        if getattr(self, "cif_path", ""):
            from arpes_viewer.tools.output.figfile import source_record
            sources = [source_record(self.cif_path, kind="structure",
                                     note="the picture is drawn from this CIF")]
        target = picture_to_composer(self, self.picture(), name,
                                     sources=sources, target=target, ask=ask)
        if target is not None:
            self.export_label.setText(f"Added to “{target.windowTitle()}”.")
        return target


def picture_to_composer(parent, image, name, *, sources=None, target=None,
                        ask=True):
    """A picture (QImage) as a panel of a figure composer: of ``target``,
    of an open one the user picks (``ask``), or of a new one. Returns the
    composer window, or None if the user cancelled."""
    from arpes_viewer.tools.output import figure as nf
    from arpes_viewer.ui.panels.figure import (FigureWindow, Panel, _qimage_array,
                                  open_figure_windows)
    from arpes_viewer.ui.viewers.windows import keep_alive

    rgba = _qimage_array(image)
    panel = Panel(data=nf.picture_data(rgba, name))
    if sources:
        panel.data.sources = list(sources)
    panel.x_labels = panel.y_labels = False
    if target is None and ask:
        windows = open_figure_windows()
        if windows:
            names = ["A new figure"] + [w.windowTitle() for w in windows]
            choice, ok = QInputDialog.getItem(
                parent, "To figure composer", "Add the picture to:", names,
                0, False)
            if not ok:
                return None
            index = names.index(choice)
            target = windows[index - 1] if index > 0 else None
    if target is None:
        target = FigureWindow([panel], f"Figure — {name}", parent=None)
        keep_alive(target)
        target.show()
    else:
        target.add_panels([panel])
        target.raise_()
    return target
