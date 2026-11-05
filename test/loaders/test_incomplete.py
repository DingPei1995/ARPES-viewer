"""A map whose scan was stopped before its end (loader/incomplete.py): the
steps never measured, and the one stopped part-way, are cut off the end --
for every beamline, through the registry -- and nothing else is.

The ANTARES case is the reported one: a 151-step deflector map stopped at
step 100, whose unmeasured images are zeros and whose deflector readback is
NaN there; the cut viewer stopped with "Cannot set range [nan, nan]"."""
import os

import numpy as np
import pytest

from arpes_viewer.loader import registry
from arpes_viewer.loader.incomplete import incomplete_tail, trim_incomplete
from arpes_viewer.loader.scan import LazyArray, LazyCube, NxsScan

from .antares_maps import write_deflector_map


def _scan(cube, kind="map", x=None):
    scan = NxsScan(kind=kind)
    scan.value = cube
    scan.x = np.arange(cube.shape[0], dtype=float) if x is None else x
    scan.k = np.arange(cube.shape[1], dtype=float)
    scan.z = np.arange(cube.shape[2], dtype=float)
    return scan


def _cube(totals):
    return np.stack([np.full((3, 4), t / 12.0) for t in totals])


# -- the rule ----------------------------------------------------------------
def test_a_complete_map_is_left_alone():
    scan = trim_incomplete(_scan(_cube([10, 11, 9, 10, 12, 10])))
    assert scan.value.shape[0] == 6
    assert not any(key.startswith("incomplete.") for key in scan.info)


def test_empty_frames_at_the_end_are_cut():
    scan = trim_incomplete(_scan(_cube([10, 10, 10, 10, 0, 0, 0])))
    assert scan.value.shape[0] == 4
    assert scan.x.size == 4
    assert scan.info["incomplete.frames_dropped"] == 3
    assert scan.info["incomplete.frames_planned"] == 7
    assert "steps 5-7 (no counts)" in scan.info["incomplete.note"]


def test_a_frame_stopped_part_way_is_cut_after_the_empty_ones():
    scan = trim_incomplete(_scan(_cube([10, 10, 10, 10, 3, 0, 0])))
    assert scan.value.shape[0] == 4
    note = scan.info["incomplete.note"]
    assert "step 5 (30% of the frames before it)" in note
    assert "steps 6-7 (no counts)" in note


def test_nan_frames_and_a_missing_axis_value_are_not_measured():
    cube = _cube([10, 10, 10, 10, 10])
    cube[-1] = np.nan
    x = np.array([0.0, 1.0, 2.0, np.nan, np.nan])
    scan = trim_incomplete(_scan(cube, x=x))
    assert scan.value.shape[0] == 3
    assert np.isfinite(scan.x).all()


def test_weak_frames_in_the_middle_are_the_sample_and_stay():
    scan = trim_incomplete(_scan(_cube([10, 10, 1, 1, 10, 10])))
    assert scan.value.shape[0] == 6


def test_a_slow_decline_is_followed_not_cut():
    """Each step is compared with the few before it, so an intensity that
    falls steadily across the scan (an edge of the deflector range) is not
    an interruption -- even though the end is a tenth of the start."""
    totals = 100 * 0.8 ** np.arange(12)
    scan = trim_incomplete(_scan(_cube(totals)))
    assert scan.value.shape[0] == 12


def test_at_least_two_frames_are_kept():
    scan = trim_incomplete(_scan(_cube([10, 0, 0, 0])))
    assert scan.value.shape[0] == 2


def test_cuts_and_converted_maps_are_not_touched():
    scan = trim_incomplete(_scan(_cube([10, 10, 10, 0]), kind="k_map"))
    assert scan.value.shape[0] == 4


def test_per_step_readbacks_in_info_are_cut_too():
    scan = _scan(_cube([10, 10, 10, 0]))
    scan.info["antares.axis0_measured"] = np.arange(4.0)
    trim_incomplete(scan)
    assert scan.info["antares.axis0_measured"].size == 3


def test_only_the_frames_looked_at_are_read():
    class Counting:
        shape, ndim = (50, 3, 4), 3

        def __init__(self):
            self.read = []

        def __getitem__(self, i):
            self.read.append(i)
            return np.zeros((3, 4)) if i >= 45 else np.ones((3, 4))

    array = Counting()
    dropped, _reasons, _totals = incomplete_tail(array)
    assert dropped == 5
    assert len(set(array.read)) <= 11


# -- lazy arrays cut without being read --------------------------------------
def test_a_lazy_cube_is_cut_on_disk(tmp_path):
    import h5py
    data = np.arange(5 * 3 * 4, dtype=float).reshape(5, 3, 4)
    with h5py.File(tmp_path / "c.h5", "w") as f:
        f["d"] = data
    with h5py.File(tmp_path / "c.h5", "r") as f:
        for lazy in (LazyCube(f["d"], (0, 1, 2)).head(3),
                     LazyArray(f["d"]).head(3)):
            assert lazy.shape == (3, 3, 4)
            assert np.asarray(lazy) == pytest.approx(data[:3])
            assert lazy[-1] == pytest.approx(data[2])
            assert lazy[1:, 0] == pytest.approx(data[1:3, 0])
            assert lazy[..., 0] == pytest.approx(data[:3, ..., 0])
            with pytest.raises(IndexError):
                lazy[3]


# -- the reported ANTARES file --------------------------------------------------
@pytest.mark.parametrize("unmeasured_axis", [np.nan, 0.0])
def test_a_stopped_antares_map_opens_as_far_as_it_went(tmp_path, recwarn,
                                                       unmeasured_axis):
    path = write_deflector_map(str(tmp_path / "DeflX_0002.nxs"), steps=151,
                               measured=100, unmeasured_axis=unmeasured_axis)
    scan = registry.load(path)
    try:
        assert scan.kind == "map"
        assert scan.value.shape == (100, 20, 30)
        assert isinstance(scan.value, LazyCube)          # still on disk
        assert scan.x == pytest.approx(np.linspace(-6, 6, 151)[:100])
        assert scan.info["incomplete.frames_dropped"] == 51
        assert "steps 101-151" in scan.info["incomplete.note"]
        assert np.asarray(scan.value[-1]).sum() > 0
        # the scale triplets' unmeasured zeros are not a "drifting calibration"
        assert not [w for w in recwarn if "calibration" in str(w.message)]
        assert scan.z[0] == pytest.approx(100.0)
    finally:
        scan.close()


def test_a_last_antares_step_stopped_part_way_is_left_out(tmp_path):
    path = write_deflector_map(str(tmp_path / "m.nxs"), steps=24,
                               measured=12, partial=0.2)
    scan = registry.load(path)
    try:
        assert scan.value.shape[0] == 11
        assert "step 12 (20% of the frames before it)" in scan.info["incomplete.note"]
    finally:
        scan.close()


def test_the_trim_can_be_turned_off(tmp_path):
    path = write_deflector_map(str(tmp_path / "m.nxs"), steps=24, measured=12)
    scan = registry.load(path, None, registry.LoadOptions(trim_incomplete=False))
    try:
        assert scan.value.shape[0] == 24
    finally:
        scan.close()


def test_a_complete_antares_map_is_unchanged(tmp_path):
    path = write_deflector_map(str(tmp_path / "m.nxs"), steps=24)
    scan = registry.load(path)
    try:
        assert scan.value.shape[0] == 24
        assert "incomplete.note" not in scan.info
    finally:
        scan.close()


def test_a_saved_dataset_is_never_trimmed(tmp_path):
    from arpes_viewer.loader import registry as reg
    native = reg.get_loader("This program's own format")
    assert native.trims_incomplete is False


def test_the_viewer_opens_the_stopped_map(tmp_path):
    """The reported crash: the map and both of its cuts open."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from arpes_viewer.ui.viewers import windows as W
    from arpes_viewer.ui.viewers.widgets import NxsData
    path = write_deflector_map(str(tmp_path / "m.nxs"), steps=40, measured=25,
                               unmeasured_axis=np.nan)
    data = NxsData(path)
    contour = W.ContourWindow(data, "m", "gray", False)
    for which in ("slit", "deflector"):
        contour.open_cut(which)
    app.processEvents()
    assert data.scan.value.shape[0] == 25
    contour.close()


def test_an_image_with_no_finite_value_is_drawn_blank():
    from arpes_viewer.ui.viewers.widgets import _drawable
    blank = _drawable(np.full((3, 4), np.nan))
    assert blank.shape == (3, 4) and not blank.any()
    image = np.ones((2, 2))
    assert _drawable(image) is image
