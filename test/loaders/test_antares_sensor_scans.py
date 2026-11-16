"""ANTARES scans of sensors (case 7): an alignment curve against one motor,
a focus scan against two; and a file whose entry recorded no scan data."""
import h5py
import numpy as np
import pytest

from arpes_viewer.loader import registry


def _entry(f, name="img1_0001"):
    g = f.create_group(name)
    g.create_group("ANTARES/MBSAcquisition_1")
    g["title"] = b""
    return g


def _sensor(group, key, values, long_name):
    group[key] = values
    group[key].attrs["long_name"] = long_name


def test_an_alignment_curve_is_one_table(tmp_path):
    path = str(tmp_path / "Align_2026-11-14_15-30-46.nxs")
    ma1 = np.linspace(-1.0, 1.0, 21)
    current = np.exp(-ma1 ** 2 / 0.1)
    with h5py.File(path, "w") as f:
        sd = _entry(f).create_group("scan_data")
        sd["actuator_1_1"] = ma1[::-1]
        sd["actuator_1_1"].attrs["long_name"] = "i12-m-c02/op/ma1-mt_tx/position"
        _sensor(sd, "data_01", current[::-1], "i12-m-cx1/dt/photodiode/current")
        _sensor(sd, "data_02", np.ones(21), "i12-m-cx1/dt/femto/gain")
        sd["time_1"] = np.arange(21.0)
    assert registry.detect(path).name == "SOLEIL ANTARES"
    [row] = registry.list_entries(path)
    assert row["entry"] == "img1_0001" and row["kind"] == "MDC"
    scan = registry.load(path, row["entry"])
    assert scan.kind == "mdc" and scan.info["_case"] == 7
    np.testing.assert_allclose(scan.x, ma1)                  # ascending
    np.testing.assert_allclose(scan.value[:, 0], current)
    assert scan.info["curve.channels"] == "photodiode current|gain"
    assert scan.labels["x"].startswith("ma1-mt_tx")


def test_a_focus_scan_is_one_image_per_sensor(tmp_path):
    path = str(tmp_path / "CapillaryFocusScan.nxs")
    pix = np.linspace(10, 14, 5)           # inner, fast
    piy = np.linspace(-2, 1, 4)            # outer, slow
    counts = np.add.outer(piy, pix)        # (outer, inner)
    with h5py.File(path, "w") as f:
        g = _entry(f, "Focus_0001")
        sd = g.create_group("scan_data")
        sd["actuator_1_1"] = np.tile(pix, (4, 1))
        sd["actuator_2_1"] = np.tile(piy[:, None], (1, 5))
        traj = g.create_group("scan_config/trajectory")
        traj["actuator_1_1/name"] = b"i12-m-cx1/ex/pi/x"
        traj["actuator_2_1/name"] = b"i12-m-cx1/ex/pi/y"
        _sensor(sd, "data_01", np.zeros((4, 5)), "i12-m-cx1/dt/femto/current")
        _sensor(sd, "data_02", counts, "cps")
    rows = registry.list_entries(path)
    assert [r["entry"] for r in rows] == ["Focus_0001#data_02", "Focus_0001#data_01"]
    assert rows[0]["kind"] == "Cut"
    scan = registry.load(path, rows[0]["entry"])
    assert scan.kind == "cut"
    np.testing.assert_allclose(scan.x, pix)
    np.testing.assert_allclose(scan.y, piy)
    np.testing.assert_allclose(scan.value, counts.T)
    assert scan.labels["x"].startswith("PIX") and scan.labels["y"].startswith("PIY")
    assert scan.info["scan.sensor"] == "cps"


def test_an_entry_with_no_scan_data_says_so(tmp_path):
    path = str(tmp_path / "Align_empty.nxs")
    with h5py.File(path, "w") as f:
        _entry(f)
    assert registry.detect(path).name == "SOLEIL ANTARES"
    [row] = registry.list_entries(path)
    assert row["kind"] == "No data"
    with pytest.raises(ValueError, match="no scan data"):
        registry.load(path, row["entry"])


def _mesh_file(path, ny=6, nx=5, nk=4, ne=7):
    """A PIX x PIY scan in a deflector map's layout, as in a real focus
    scan: actuators on the grid, the scales per point, data_11 4-D, and
    the counts (CPS) recorded at each point."""
    pix = np.linspace(10, 14, nx)
    piy = np.linspace(-2, 1, ny)
    rng = np.random.default_rng(3)
    cube = rng.random((ny, nx, nk, ne)).astype(np.float32)
    with h5py.File(path, "w") as f:
        g = _entry(f, "Focus_0001")
        sd = g.create_group("scan_data")
        sd["actuator_1_1"] = np.tile(pix, (ny, 1))
        sd["actuator_1_1"].attrs["long_name"] = "i12-m-cx1/ex/pi/x"
        sd["actuator_2_1"] = np.tile(piy[:, None], (1, nx))
        sd["actuator_2_1"].attrs["long_name"] = "i12-m-cx1/ex/pi/y"
        full = lambda v: np.full((ny, nx), float(v))
        for key, value in (("data_04", 16.0), ("data_05", 0.5), ("data_06", 19.0),
                           ("data_07", -3.0), ("data_08", 2.0), ("data_09", 3.0)):
            sd[key] = full(value)
        sd["data_11"] = cube
        _sensor(sd, "data_01", cube.sum(axis=(2, 3)), "cps")
    return pix, piy, cube


def test_a_focus_scan_with_spectra_is_a_spatial_scan_and_its_counts_an_image(tmp_path):
    path = str(tmp_path / "CapillaryFocusScan.nxs")
    pix, piy, cube = _mesh_file(path)
    rows = registry.list_entries(path)
    assert [(r["entry"], r["kind"]) for r in rows] == [
        ("Focus_0001", "SPEM"), ("Focus_0001#data_01", "Cut")]
    with registry.load(path, "Focus_0001") as scan:
        assert scan.kind == "spem_4d"
        np.testing.assert_allclose(scan.x, pix)
        np.testing.assert_allclose(scan.y, piy)
        np.testing.assert_allclose(scan.k, [-3, -1, 1, 3])
        np.testing.assert_allclose(scan.z, np.arange(16.0, 19.01, 0.5))
        np.testing.assert_array_equal(scan.value4d[2, 3], cube[2, 3])
        assert scan.labels["x"].startswith("PIX")
    with registry.load(path, "Focus_0001#data_01") as scan:
        assert scan.kind == "cut" and scan.info["scan.sensor"] == "cps"
        np.testing.assert_allclose(scan.value, cube.sum(axis=(2, 3)).T, rtol=1e-6)


def test_the_focus_scan_opens_in_the_program(tmp_path, qapp):
    from arpes_viewer.ui.viewers.widgets import NxsData
    path = str(tmp_path / "CapillaryFocusScan.nxs")
    _mesh_file(path)
    data = NxsData.acquire(path, "Focus_0001")
    try:
        assert data.kind == "spem_4d"
    finally:
        data.close()


def test_a_focus_scan_stopped_half_way_opens_with_its_whole_grid(tmp_path, qapp):
    """The rows never measured read NaN (or 0): the positions are filled
    from the even steps of the measured ones, and the scan opens."""
    from arpes_viewer.ui.viewers.widgets import NxsData
    from arpes_viewer.ui.viewers import windows
    path = str(tmp_path / "Focus_stopped.nxs")
    pix, piy, cube = _mesh_file(path)
    with h5py.File(path, "r+") as f:
        sd = f["Focus_0001/scan_data"]
        for key, fill in (("actuator_1_1", np.nan), ("actuator_2_1", 0.0)):
            values = sd[key][()]
            values[4:] = fill                        # rows 4, 5 never measured
            sd[key][...] = values
        data = sd["data_11"][()]
        data[4:] = np.nan
        sd["data_11"][...] = data
    with registry.load(path, "Focus_0001") as scan:
        np.testing.assert_allclose(scan.x, pix)
        np.testing.assert_allclose(scan.y, piy)
    data = NxsData.acquire(path, "Focus_0001")
    window = windows.open_viewer(data, "stopped", "gray", False)
    assert window is not None
    window.close()
    for row in registry.list_entries(path)[1:]:
        with registry.load(path, row["entry"]) as image:
            assert np.isfinite(image.x).all() and np.isfinite(image.y).all()
