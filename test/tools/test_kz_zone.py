"""The Brillouin zone as a k_z map sees it, for any surface normal.

A k_z map is the plane holding the surface normal and the slit direction.
The zone drawn on it used to be vertical lines at multiples of the period
along the normal -- Gamma points, not boundaries, and the same picture
whatever the surface. These pin the real cut, the dialogs that draw it, and
the lattice they build it from.
"""
import os

import numpy as np
import pytest

from arpes_viewer.tools.crystal.bz3d import kz_frame, kz_zone_cuts, wigner_seitz_cell
from arpes_viewer.tools.crystal.lattice import (LatticeParams, primitive_vectors,
                                   reciprocal_vectors)


def _zone(params):
    b = reciprocal_vectors(primitive_vectors(params))
    return wigner_seitz_cell(b), b


def _centres_on_axis(polygons):
    return sorted(round(float(xs[:-1].mean()), 4) for xs, ys in polygons
                  if abs(ys[:-1].mean()) < 1e-6)


def test_hexagonal_001_is_rectangles_with_period_2pi_over_c():
    params = LatticeParams(3.2, 3.2, 6.0, 90, 90, 120, space_group=194)
    zone, b = _zone(params)
    polygons = kz_zone_cuts(zone, b, kz_frame(params, (0, 0, 1)),
                            (0.0, 3.0), (-1.0, 1.0))
    centres = _centres_on_axis(polygons)
    assert np.allclose(np.diff(centres), 2 * np.pi / 6.0, atol=1e-4)
    assert all(len(xs) - 1 == 4 for xs, _ys in polygons)
    # half-width along k_par is Gamma-M, |a*| / 2
    xs, ys = polygons[0]
    assert np.isclose(np.max(np.abs(ys)), 2 * np.pi / 3.2 / np.sqrt(3), atol=1e-6)


def test_bcc_001_repeats_every_4pi_over_a_not_2pi():
    a = np.pi
    params = LatticeParams(a, a, a, space_group=229)
    zone, b = _zone(params)
    polygons = kz_zone_cuts(zone, b, kz_frame(params, (0, 0, 1)),
                            (-0.5, 9.0), (-0.5, 0.5))
    assert np.allclose(np.diff(_centres_on_axis(polygons)), 4 * np.pi / a)


def test_fcc_111_cuts_are_hexagons_along_the_111_period():
    a = np.pi
    params = LatticeParams(a, a, a, space_group=225)
    zone, b = _zone(params)
    polygons = kz_zone_cuts(zone, b, kz_frame(params, (1, 1, 1)),
                            (0.0, 8.0), (-1.0, 1.0))
    assert np.allclose(np.diff(_centres_on_axis(polygons)),
                       2 * np.pi * np.sqrt(3) / a, atol=1e-4)
    assert {len(xs) - 1 for xs, _ys in polygons} == {6}


def test_the_frame_follows_the_normal_and_the_kpar_choice():
    params = LatticeParams(4.0, 4.0, 4.0, space_group=221)
    normal, along, across = kz_frame(params, (1, 1, 0), (0, 0, 1))
    assert np.allclose(normal, [1 / np.sqrt(2), 1 / np.sqrt(2), 0])
    assert np.allclose(along, [0, 0, 1])
    assert np.allclose(np.cross(normal, along), across)
    _n, turned, _x = kz_frame(params, (1, 1, 0), (0, 0, 1), 90.0)
    assert np.allclose(turned, across)
    with pytest.raises(ValueError):
        kz_frame(params, (1, 1, 0), (2, 2, 0))
    with pytest.raises(ValueError):
        kz_frame(params, (0, 0, 0))


def test_untiled_keeps_the_copy_in_the_window():
    params = LatticeParams(3.0, 3.0, 3.0, space_group=221)
    zone, b = _zone(params)
    one = kz_zone_cuts(zone, b, kz_frame(params, (0, 0, 1)), (5.5, 7.0),
                       (-0.5, 0.5), tile=False)
    assert len(one) == 1
    assert np.isclose(one[0][0][:-1].mean(), 3 * 2 * np.pi / 3.0)


# -- the dialogs ------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _kz_map(kind):
    from arpes_viewer.ui.viewers.widgets import MemoryData
    first = (np.linspace(40, 120, 21) if kind == "kz_map"
             else np.linspace(2.0, 6.0, 41))
    second = (np.linspace(-12, 12, 25) if kind == "kz_map"
              else np.linspace(-1.0, 1.0, 21))
    energy = np.linspace(-0.5, 0.1, 13)
    rng = np.random.default_rng(1)
    labels = {"x": "x", "k": "k", "z": "E - E_F (eV)"}
    return MemoryData(kind, (first, second, energy),
                      rng.random((first.size, second.size, energy.size)) + 1,
                      labels, source_label="kz")


def test_kz_conversion_window_draws_the_cut_for_any_normal(app):
    from arpes_viewer.ui.viewers import windows as W
    from arpes_viewer.ui.panels.kzconv import KzConversionDialog
    contour = W.ContourWindow(_kz_map("kz_map"), "kz", "gray", False)
    dialog = KzConversionDialog(contour)
    # the default hexagonal group gets its gamma = 120, not 90
    assert dialog.lattice().gamma == 120.0
    assert not dialog.lat_gamma.isEnabled() and not dialog.lat_b.isEnabled()
    assert dialog.surface_hkl() == (0, 0, 1)
    # a lattice edit keeps the chosen normal
    target = next(i for i in range(dialog.normal_index.count())
                  if tuple(dialog.normal_index.itemData(i)[0]) == (1, 0, 0))
    dialog.normal_index.setCurrentIndex(target)
    dialog.lat_c.setValue(6.5)
    assert dialog.surface_hkl() == (1, 0, 0)
    xs, ys = dialog.zone_item.getData()
    assert xs is not None and np.isfinite(xs).any()
    # cubic: b and c follow a
    dialog.space_group.setValue(225)
    dialog.lat_a.setValue(4.1)
    assert dialog.lat_b.value() == dialog.lat_c.value() == 4.1
    dialog.close()
    contour.close()


def test_brillouin_zone_dialog_is_offered_and_draws_on_a_kz_map(app):
    from arpes_viewer.ui.viewers import windows as W
    contour = W.ContourWindow(_kz_map("kz_map_k"), "kz", "gray", False)
    info = contour.data.scan.info
    info.update({"bz.space_group": 225, "bz.a": np.pi, "bz.h": 1,
                 "bz.k": 1, "bz.l": 1})
    dialog = contour.open_brillouin_zone()
    assert dialog._kz_map and not dialog.mode_2d.isVisible()
    message = dialog.plot()
    assert message and "polygon" in message, dialog.note.text()
    item = contour.view._bz_layers["bz_main"]
    xs, _ys = item.getData()
    finite = xs[np.isfinite(xs)]
    # drawn in k_z, inside (or at the edge of) the map's k_z range
    assert finite.max() > 2.0 and finite.min() < 6.0
    assert info["bz.kpar_h"] == 0
    dialog.close()
    contour.close()


def test_kz_conversion_window_theta_grid_gamma_and_calibration(app, monkeypatch):
    from arpes_viewer.ui.viewers import windows as W
    from arpes_viewer.ui.panels import kzconv as K
    from arpes_viewer.tools.runtime import remembered
    monkeypatch.setattr(remembered, "recall", lambda *a, **k: None)
    data = _kz_map("kz_map")
    data.scan.info["cassiopee.sample_theta_deg"] = 37.5
    contour = W.ContourWindow(data, "kz", "gray", False)
    dialog = K.KzConversionDialog(contour)
    # the motor's absolute theta is not used unless asked for, as an offset
    assert not dialog.theta_correct.isChecked()
    assert dialog.settings()["theta_position"] == 0.0
    dialog.theta_correct.setChecked(True)
    dialog.theta_position.setValue(1.5)
    assert dialog.settings()["theta_position"] == 1.5
    # the grid follows the angle channels
    assert dialog.n_kpar.value() == max(16, dialog.angle.size)
    # V0 from Γ: k_z at normal emission is then a whole number of periods
    v0, order = dialog.set_v0_from_gamma()
    hv = dialog.gamma_hv.value()
    kz = np.sqrt(K.kzconv.A_CONST * (hv - dialog.work_function.value() + v0))
    assert kz == pytest.approx(order * dialog.surface_period(), rel=1e-6)
    # no per-hv Fermi levels: the calibration cannot be switched on
    assert not dialog.calibrate_hv.isEnabled()
    assert np.ndim(dialog.settings()["work_function"]) == 0
    # the slider and the energy box move together
    dialog.energy_slider.setValue(0)
    assert dialog.preview_energy.value() == pytest.approx(dialog.energy[0], abs=1e-3)
    dialog.close()
    contour.close()


def test_kz_conversion_calibration_is_offered_after_per_hv_fermi_levels(app, monkeypatch):
    from arpes_viewer.ui.viewers import windows as W
    from arpes_viewer.ui.panels import kzconv as K
    from arpes_viewer.tools.runtime import remembered
    monkeypatch.setattr(remembered, "recall", lambda *a, **k: None)
    data = _kz_map("kz_map")
    hv = np.asarray(data.angle_cube[0], dtype=float)
    data.scan.info.update({
        "kz.fermi_level_eV": np.zeros(hv.size),
        "cassiopee.member_photon_energy_eV": hv,
        "cassiopee.member_work_function_eV": np.full(hv.size, 4.2),
        "cassiopee.member_kinetic_start_eV": hv - 4.6 - 0.5})
    contour = W.ContourWindow(data, "kz", "gray", False)
    dialog = K.KzConversionDialog(contour)
    assert dialog.calibrate_hv.isEnabled() and not dialog.calibrate_hv.isChecked()
    dialog.calibrate_hv.setChecked(True)
    phi = dialog.settings()["work_function"]
    assert np.shape(phi) == hv.shape
    dialog.close()
    contour.close()


def test_the_kz_plane_is_shown_in_the_3d_zone(app, monkeypatch):
    """The BZ overlap tool's cut-plane view, fed by the kz window: the plane
    holds the surface normal and the k_par direction, through Γ."""
    from arpes_viewer.ui.viewers import windows as W
    from arpes_viewer.ui.panels import kzconv as K
    from arpes_viewer.tools.runtime import remembered
    monkeypatch.setattr(remembered, "recall", lambda *a, **k: None)
    contour = W.ContourWindow(_kz_map("kz_map"), "kz", "gray", False)
    dialog = K.KzConversionDialog(contour)
    dialog.space_group.setValue(221)
    dialog.lat_a.setValue(3.0)
    preview = dialog.open_plane_preview()
    assert isinstance(preview, W.CutPlanePreviewDialog) and preview.isVisible()
    zone, _b, _bc, normal, point, u, v = dialog.cut_geometry()
    along_kz, along_kpar, _across = dialog._kz_axes()
    assert abs(normal @ along_kz) < 1e-9 and abs(normal @ along_kpar) < 1e-9
    assert np.allclose(point, 0.0) and u is not None
    assert "Γ" in {label for label, _k in dialog.points_in_plane()}
    assert "measured plane" in preview.note.text()
    dialog.inner_potential.setValue(15.0)          # the view follows
    assert "V0 = 15.0" in preview.note.text()
    assert dialog.open_plane_preview() is preview  # one window, raised
    preview.close()
    assert dialog._plane_preview is None
    dialog.close()
    contour.close()


def test_the_kz_window_has_the_viewer_colour_controls_and_no_v0_scan(app, monkeypatch):
    """Colour map + Flip and the level bar (levels, gamma) as in the data
    viewers; no V0-scan tab; k// set by a rotation only."""
    from PyQt5.QtWidgets import QTabWidget
    from arpes_viewer.ui.viewers import windows as W
    from arpes_viewer.ui.panels import kzconv as K
    from arpes_viewer.tools.runtime import remembered
    monkeypatch.setattr(remembered, "recall", lambda *a, **k: None)
    contour = W.ContourWindow(_kz_map("kz_map"), "kz", "gray", False)
    dialog = K.KzConversionDialog(contour)
    assert not dialog.findChildren(QTabWidget)
    assert not hasattr(dialog, "scan_v0")
    dialog.flip_cb.setChecked(True)
    dialog.level_bar.gamma_box.setValue(0.5)
    image = dialog.image.image.T                      # drawn row-major
    assert np.nanmin(image) >= 0.0 and np.nanmax(image) <= 1.0
    lo, hi = dialog.level_bar.levels()
    plane = dialog._preview[2]
    inside = np.isfinite(plane) & (plane > lo) & (plane < hi)
    expected = ((plane[inside] - lo) / (hi - lo)) ** 0.5
    assert np.allclose(image[inside], expected)
    assert dialog.kpar_hkl() == (0, 0, 0) and not dialog.kpar_h.isVisible()
    dialog.kpar_rotation.setValue(30.0)
    along = dialog._kz_axes()[1]
    dialog.kpar_rotation.setValue(0.0)
    assert abs(float(along @ dialog._kz_axes()[1]) - np.cos(np.radians(30))) < 1e-9
    dialog.close()
    contour.close()


def test_the_kz_preview_puts_k_z_across_and_k_par_up(app, monkeypatch):
    """A feature at one k_z shows as a vertical stripe at that k_z: the
    picture agrees with its axes (the image is drawn row-major)."""
    from arpes_viewer.ui.viewers import windows as W
    from arpes_viewer.ui.panels import kzconv as K
    from arpes_viewer.tools.runtime import remembered
    monkeypatch.setattr(remembered, "recall", lambda *a, **k: None)
    contour = W.ContourWindow(_kz_map("kz_map"), "kz", "gray", False)
    dialog = K.KzConversionDialog(contour)
    dialog.n_kz.setValue(40)
    dialog.n_kpar.setValue(25)
    kz_axis, kpar_axis, plane = dialog._preview
    image = dialog.image.image
    assert image.shape == (kpar_axis.size, kz_axis.size)   # rows: k//, up
    rect = dialog.image.mapRectToParent(dialog.image.boundingRect())
    assert rect.left() == pytest.approx(kz_axis[0])
    assert rect.width() == pytest.approx(kz_axis[-1] - kz_axis[0])
    assert rect.top() == pytest.approx(kpar_axis[0])
    dialog.close()
    contour.close()
