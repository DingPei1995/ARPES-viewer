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
