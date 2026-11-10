"""The SPEM viewer as two windows: the spatial map and its spectrum (the
cut viewer), the selection boxes above them that integrate on Refresh only,
the spectra against position beside and under the map, and the two closing
together.

Needs Qt; run headless with QT_QPA_PLATFORM=offscreen.
"""
import gc
import os
import weakref

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication                          # noqa: E402

from arpes_viewer.ui.viewers.widgets import MemoryData, spatial_profile  # noqa: E402
from arpes_viewer.ui.viewers import windows as W  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _cube():
    x, y = np.linspace(0, 5, 6), np.linspace(10, 14, 5)
    k, e = np.linspace(-1, 1, 7), np.linspace(-0.5, 0.1, 8)
    values = np.random.default_rng(3).random((y.size, x.size, k.size, e.size))
    return (x, y, k, e), values


def _spem(kind="spem_4d"):
    axes, values = _cube()
    if kind == "spem_1d":
        x, _y, k, e = axes
        return MemoryData("spem_1d", (x, k, e), values[0],
                          {"x": "X (mm)", "y": "k", "z": "E"}, source_label="line")
    return MemoryData("spem_4d", axes, values,
                      {"x": "X (mm)", "y": "Y (mm)", "k": "k", "z": "E"},
                      source_label="s")


@pytest.fixture
def window(app):
    window = W.SpatialScanWindow(_spem(), "spem", "gray", False)
    yield window
    window.close()


def test_the_spectrum_is_a_cut_window_of_its_own(window):
    cut = window.cut_window
    assert isinstance(cut, W.CutWindow)
    assert cut is not window
    # the map window keeps only the map
    assert window.image_panels() == (window.spatial_panel,)
    yi, xi = window._pixel
    np.testing.assert_allclose(cut.view.last_frame,
                               window.data.scan.value4d[yi, xi])
    # the cut window's tools read the spectrum on screen
    np.testing.assert_allclose(cut.data.cut_frame, cut.view.last_frame)


def test_moving_the_cursor_moves_the_spectrum(window):
    scan = window.data.scan
    window._on_cursor_moved(1, 4)
    np.testing.assert_allclose(window.cut_window.view.last_frame, scan.value4d[1, 4])
    assert "4" in window.cut_window.slice_label()


def test_no_selection_or_profile_in_the_right_click_menu(window):
    for view in (window.spatial_view, window.cut_window.view):
        texts = [a.text() for a in view.view_box.menu.actions()]
        assert not any("Selection" in t or "Integrate" in t or "profile" in t.lower()
                       or "Stack" in t for t in texts), texts


def test_spatial_box_integrates_only_on_refresh(window):
    scan = window.data.scan
    bar = window.selection_bar
    before = np.array(window.cut_window.view.last_frame)
    bar.set_corners(1, 11, 3, 12, apply=False)
    # placed, not applied: nothing computed yet
    np.testing.assert_allclose(window.cut_window.view.last_frame, before)
    assert bar.note.text()
    bar.refresh()
    expected = scan.value4d[1:3, 1:4].sum(axis=(0, 1))
    np.testing.assert_allclose(window.cut_window.view.last_frame, expected)
    assert not bar.note.text()
    # while the sum is shown, the cursor does not replace it ...
    window._on_cursor_moved(0, 0)
    np.testing.assert_allclose(window.cut_window.view.last_frame, expected)
    # ... not even once the box is unticked: the result is kept
    bar.checkbox.setChecked(False)
    np.testing.assert_allclose(window.cut_window.view.last_frame, expected)
    assert "Reset" in bar.note.text()
    window._on_cursor_moved(0, 1)
    np.testing.assert_allclose(window.cut_window.view.last_frame, expected)
    # Reset: back to the pixel under the cursor, and following it again
    bar.reset_button.click()
    np.testing.assert_allclose(window.cut_window.view.last_frame, scan.value4d[0, 1])
    assert not bar.reset_button.isEnabled()
    window._on_cursor_moved(2, 2)
    np.testing.assert_allclose(window.cut_window.view.last_frame, scan.value4d[2, 2])


def test_spectrum_box_integrates_the_map_on_refresh(window):
    scan = window.data.scan
    overview = np.array(window._spatial_map)
    bar = window.cut_window.selection_bar
    bar.set_corners(-0.4, -0.4, 0.4, -0.2, apply=False)
    np.testing.assert_allclose(window._spatial_map, overview)
    bar.refresh()
    ik = np.nonzero((scan.k >= -0.4) & (scan.k <= 0.4))[0]
    ie = np.nonzero((scan.z >= -0.4) & (scan.z <= -0.2))[0]
    expected = scan.value4d[:, :, ik][:, :, :, ie].sum(axis=(2, 3))
    np.testing.assert_allclose(window._spatial_map, expected)
    # unticking keeps the integrated map; Reset gives the full one back
    bar.checkbox.setChecked(False)
    np.testing.assert_allclose(window._spatial_map, expected)
    bar.reset_button.click()
    np.testing.assert_allclose(window._spatial_map, overview)


@pytest.mark.parametrize("mode", ["E", "k"])
def test_spectra_against_position(window, mode):
    scan = window.data.scan
    window.set_profile_mode(mode)
    cut = window.cut_window
    assert cut.range_region is not None
    assert cut.range_region.orientation == ("vertical" if mode == "E" else "horizontal")
    lo, hi = (-0.5, 0.2) if mode == "E" else (-0.3, 0.0)
    cut.set_range(lo, hi)
    window._on_cursor_moved(2, 3)
    arrays = window.refresh_profiles()
    axis = scan.k if mode == "E" else scan.z
    band = np.nonzero((axis >= lo) & (axis <= hi))[0]
    cube = scan.value4d
    if mode == "E":
        row = cube[2, :, band.min():band.max() + 1, :].sum(axis=1)     # (x, E)
        col = cube[:, 3, band.min():band.max() + 1, :].sum(axis=1)     # (y, E)
    else:
        row = cube[2, :, :, band.min():band.max() + 1].sum(axis=2)     # (x, k)
        col = cube[:, 3, :, band.min():band.max() + 1].sum(axis=2)     # (y, k)
    bottom, bx, by = arrays["bottom"]
    right, rx, ry = arrays["right"]
    np.testing.assert_allclose(bottom, row.T)
    np.testing.assert_allclose(bx, scan.x)
    np.testing.assert_allclose(right, col)
    np.testing.assert_allclose(ry, scan.y)
    assert window.right_profile.isVisibleTo(window)
    assert window.bottom_profile.isVisibleTo(window)


def test_profile_boxes_are_exclusive(window):
    boxes = window.profile_boxes
    boxes["E"].setChecked(True)
    assert window.profile_mode == "E"
    boxes["k"].setChecked(True)
    assert window.profile_mode == "k"
    assert not boxes["E"].isChecked()
    assert window.cut_window.range_region.orientation == "horizontal"
    boxes["k"].setChecked(False)
    assert window.profile_mode is None
    assert window.cut_window.range_region is None
    assert not window.right_profile.isVisibleTo(window)


def test_profiles_follow_a_swapped_map(window):
    scan = window.data.scan
    window.set_swap_xy(True)
    window.set_profile_mode("E")
    arrays = window.profile_arrays()
    np.testing.assert_allclose(arrays["bottom"][1], scan.y)
    np.testing.assert_allclose(arrays["right"][2], scan.x)


def test_spatial_profile_reader():
    (_x, _y, _k, _e), values = _cube()
    out = spatial_profile(values, "y", 2, slice(1, 3), slice(None), "E")
    np.testing.assert_allclose(out, values[:, 2, 1:3, :].sum(axis=1))
    with pytest.raises(ValueError):
        spatial_profile(values, "z", 0, slice(None), slice(None), "E")


@pytest.mark.parametrize("close_first", ["map", "spectrum"])
def test_closing_one_closes_both_and_lets_go(app, close_first):
    window = W.SpatialScanWindow(_spem(), "spem", "gray", False)
    window.show()
    cut = window.cut_window
    assert cut.isVisible()
    closed = []
    window.closed.connect(lambda w: closed.append("map"))
    cut.closed.connect(lambda w: closed.append("spectrum"))
    (window if close_first == "map" else cut).close()
    app.processEvents()
    assert not window.isVisible() and not cut.isVisible()
    assert sorted(closed) == ["map", "spectrum"]
    assert window.cut_window is None
    assert cut.data.scan.value is None
    refs = (weakref.ref(window), weakref.ref(cut))
    del window, cut
    gc.collect()
    app.processEvents()
    gc.collect()
    assert all(ref() is None for ref in refs)


def test_a_line_scan_has_no_boxes(app):
    window = W.SpatialScanWindow(_spem("spem_1d"), "line", "gray", False)
    try:
        assert window.selection_bar is None
        assert window.profile_boxes == {}
        assert window.cut_window.selection_bar is None
        window._on_cursor_moved(0, 2)
        np.testing.assert_allclose(window.cut_window.view.last_frame,
                                   window.data.scan.value[2])
    finally:
        window.close()


def test_snapshot_of_the_spectrum(window):
    popout = window.open_popout()
    try:
        np.testing.assert_allclose(popout.view.last_frame,
                                   window.cut_window.view.last_frame)
    finally:
        popout.close()


def test_the_readout_cursor_picks_the_pixel(window):
    import pyqtgraph as pg
    view = window.spatial_view
    # on from the start, and no second (red target) cursor on the map
    assert view.readout_cursor is not None
    assert view.action_readout.isChecked()
    targets = [item for item in view.plot.items
               if isinstance(item, pg.TargetItem)]
    assert targets == [view.readout_cursor]
    scan = window.data.scan
    assert view.move_readout_to(x=scan.x[4], y=scan.y[1]) is None
    np.testing.assert_allclose(window.cut_window.view.last_frame, scan.value4d[1, 4])
    assert window.spatial_panel.cursor_widget.isVisibleTo(window.spatial_panel)
    # off and on again: back where it was, not in the middle
    view.set_readout_cursor_visible(False)
    view.set_readout_cursor_visible(True)
    np.testing.assert_allclose(view.readout_position(), (scan.x[4], scan.y[1]))


def test_unticking_keeps_the_box(window):
    for bar in (window.selection_bar, window.cut_window.selection_bar):
        x = bar.view._xarray
        y = bar.view._yarray
        corners = (float(x[1]), float(y[1]), float(x[3]), float(y[3]))
        bar.set_corners(*corners, apply=False)
        bar.checkbox.setChecked(False)
        assert bar.view.selection_roi is None
        np.testing.assert_allclose([s.value() for s in bar.corner_spins], corners, atol=1e-3)
        bar.checkbox.setChecked(True)
        np.testing.assert_allclose(bar.corners(), corners, atol=1e-3)


def test_swapping_carries_the_box(window):
    bar = window.selection_bar
    bar.set_corners(1, 11, 3, 12, apply=False)
    window.set_swap_xy(True)
    np.testing.assert_allclose(bar.corners(), (11, 1, 12, 3))


def test_profile_boxes_on_a_row_under_the_selection_box(window):
    window.show()
    QApplication.processEvents()
    try:
        bar = window.selection_bar
        box = window.profile_boxes["E"]
        bar_y = bar.mapTo(window, bar.rect().bottomLeft()).y()
        box_y = box.mapTo(window, box.rect().topLeft()).y()
        assert box_y >= bar_y
    finally:
        window.hide()


@pytest.mark.parametrize("mode", ["E", "k"])
def test_line_cursors_on_the_side_pictures(window, mode):
    scan = window.data.scan
    window.set_profile_mode(mode)
    window._on_cursor_moved(2, 3)
    arrays = window.refresh_profiles()
    spectral = scan.z if mode == "E" else scan.k
    at = float(spectral[2])
    # the menu entries are there
    assert set(window.line_cursor_actions) == {"right", "bottom"}
    window.set_line_cursor("right", True, value=at)
    window.set_line_cursor("bottom", True, value=at)
    assert window.line_cursor_actions["right"].isChecked()
    positions, intensity, where = window.line_curve("right")
    np.testing.assert_allclose(positions, scan.y)
    np.testing.assert_allclose(intensity, arrays["right"][0][:, 2])
    assert where == pytest.approx(at)
    positions, intensity, _ = window.line_curve("bottom")
    np.testing.assert_allclose(positions, scan.x)
    np.testing.assert_allclose(intensity, arrays["bottom"][0][2, :])
    assert window.far_right_curve.isVisibleTo(window)
    assert window.far_bottom_curve.isVisibleTo(window)
    # the curve follows the profiles when the cursor moves on the map
    window._on_cursor_moved(0, 1)
    window.refresh_profiles()
    np.testing.assert_allclose(window.line_curve("right")[1],
                               window.profile_arrays()["right"][0][:, 2])
    # off: the far plot goes, the other stays
    window.line_cursor_actions["right"].setChecked(False)
    assert window.line_cursors["right"] is None
    assert not window.far_right_curve.isVisibleTo(window)
    assert window.far_bottom_curve.isVisibleTo(window)
    # switching the spectral axis keeps the cursor, inside the new axis
    other = "k" if mode == "E" else "E"
    window.set_profile_mode(other)
    axis = scan.k if other == "k" else scan.z
    value = window.line_cursors["bottom"].value()
    assert axis.min() <= value <= axis.max()
    assert window.line_curve("bottom") is not None
    # no profile: nothing beside the map
    window.set_profile_mode(None)
    assert not window.far_bottom_curve.isVisibleTo(window)


def test_the_band_lets_the_box_be_dragged(app, window):
    """A box corner inside the E-vs-position band can still be dragged: only
    the band's two lines take the mouse, not the shaded area between."""
    from PyQt5.QtCore import QEvent, QPoint, QPointF
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtCore import Qt
    cut = window.cut_window
    cut.resize(700, 700)
    cut.show()
    try:
        window.set_profile_mode("E")
        cut.set_range(-0.6, 0.6)
        region = cut.range_region
        assert not region.movable
        assert all(line.movable for line in region.lines)
        bar = cut.selection_bar
        # the box's lower-left corner inside the band, between the lines
        bar.set_corners(-0.2, -0.4, 0.8, -0.1, apply=False)
        for _ in range(10):
            app.processEvents()
        view = cut.view
        roi = view.selection_roi
        # the handle at the box's lower-left corner
        handle = min(roi.getHandles(), key=lambda h: h.pos().x() + h.pos().y())
        scene_point = handle.mapToScene(QPointF(0, 0))
        widget = view.ui.graphicsView
        start = widget.mapFromScene(scene_point)
        end = start + QPoint(-40, 30)
        viewport = widget.viewport()

        def send(kind, point, buttons):
            event = QMouseEvent(kind, QPointF(point), Qt.LeftButton, buttons, Qt.NoModifier)
            QApplication.sendEvent(viewport, event)
            app.processEvents()

        before = view.selection_corners()
        send(QEvent.MouseButtonPress, start, Qt.LeftButton)
        for step in range(1, 6):
            send(QEvent.MouseMove, start + (end - start) * step / 5, Qt.LeftButton)
        send(QEvent.MouseButtonRelease, end, Qt.NoButton)
        after = view.selection_corners()
        assert after[0] < before[0] - 1e-3          # the corner moved left
        # the band did not move with it
        assert cut.range_values() == pytest.approx((-0.6, 0.6))
    finally:
        cut.hide()


def test_a_line_cursor_does_not_squeeze_the_map(app, window):
    from arpes_viewer.ui.common import screen
    screen.LIMIT_TO_SCREEN, saved = False, screen.LIMIT_TO_SCREEN
    try:
        window.resize(900, 900)
        window.show()

        def map_size():
            for _ in range(30):
                app.processEvents()
            box = window.spatial_view.view_box
            return box.width(), box.height()

        start = map_size()
        window.set_profile_mode("E")
        assert map_size() == pytest.approx(start, abs=3)
        window.set_line_cursor("bottom", True)
        assert map_size() == pytest.approx(start, abs=3)
        window.set_line_cursor("right", True)
        assert map_size() == pytest.approx(start, abs=3)
        window.set_line_cursor("bottom", False)
        window.set_line_cursor("right", False)
        window.set_profile_mode(None)
        assert map_size() == pytest.approx(start, abs=3)
        assert (window.width(), window.height()) == (900, 900)
    finally:
        screen.LIMIT_TO_SCREEN = saved
        window.hide()
