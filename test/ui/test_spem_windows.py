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
    # while the box is on, the cursor does not replace the sum
    window._on_cursor_moved(0, 0)
    np.testing.assert_allclose(window.cut_window.view.last_frame, expected)
    # untick: back to the pixel under the cursor
    bar.checkbox.setChecked(False)
    np.testing.assert_allclose(window.cut_window.view.last_frame, scan.value4d[0, 0])


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
    bar.checkbox.setChecked(False)
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
