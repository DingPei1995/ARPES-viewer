"""Diamond I09 (loader/beamlines/i09.py), on files laid out as the
beamline's Igor loader (I09_LoadData.ipf) reads them."""
import h5py
import numpy as np
import pytest

from arpes_viewer.loader import registry
from arpes_viewer.loader.beamlines.i09 import parse_scan_command

NA, NE = 6, 9
NAME = "Diamond I09 (EW4000, I09-2 momentum microscope)"


def _gda(f, root="/entry1", version="GDA 9.32.0", command="", name="i09"):
    entry = f.require_group(root)
    entry["program_name"] = version
    entry["title"] = "a scan"
    entry["start_time"] = "2026-11-14T10:00:00"
    if command:
        if version >= "GDA 9.38":
            entry.require_group("diamond_scan")["scan_command"] = command
        else:
            entry["scan_command"] = command
    instrument = entry.require_group("instrument")
    instrument["name"] = name
    return entry


def _region(entry, name, scan_shape, energies=None):
    entry.require_group("instrument/ew4000")
    entry["instrument/ew4000/region_list"] = np.array([name.encode()])
    group = entry.require_group(name)
    data = np.arange(int(np.prod(scan_shape)) * NA * NE, dtype=np.int32).reshape(
        scan_shape + (NA, NE))
    group["image_data"] = data
    group["spectrum_data"] = data.sum(axis=-2)
    group["angles"] = np.linspace(-15, 15, NA)
    group["energies"] = np.linspace(80, 81, NE) if energies is None else energies
    entry["instrument/ew4000/pass_energy"] = 50.0
    return data


def test_scan_command_is_read_as_the_igor_loader_reads_it():
    scannables, detectors = parse_scan_command(
        "scan smpmx 0 1 0.5 smpmy 0 2 1 ew4000 /dls/i09/seq.xml")
    assert [s[0] for s in scannables] == ["smpmx", "smpmy"]
    assert [d[0] for d in detectors] == ["ew4000"]
    scannables, detectors = parse_scan_command("scan kenergy 20 21 0.1 dld 1.0")
    assert scannables == [("kenergy", [20.0, 21.0, 0.1])]
    assert detectors == [("dld", [1.0])]


def test_a_single_region_is_a_cut(tmp_path):
    path = str(tmp_path / "i09-123456.nxs")
    with h5py.File(path, "w") as f:
        entry = _gda(f, command="scan ew4000 /dls/i09/seq.xml")
        data = _region(entry, "Au_VB", (1,))
        entry["instrument/pgmenergy/value"] = np.array([450.0])
    assert registry.detect(path).name == NAME
    [row] = registry.list_entries(path)
    assert row["kind"] == "Cut" and row["entry"] == "region:Au_VB"
    with registry.load(path, row["entry"]) as scan:
        assert scan.kind == "cut"
        np.testing.assert_array_equal(np.asarray(scan.value), data[0])
        np.testing.assert_allclose(scan.y, np.linspace(80, 81, NE))
        assert scan.labels["y"] == "Kinetic energy (eV)"
        assert scan.info["photon_energy_eV"] == 450.0
        assert scan.info["i09.region"] == "Au_VB"
        assert scan.info["instrument.ew4000.pass_energy"] == 50.0
        assert scan.info["gda_version"] == pytest.approx(9.32)


def test_a_polar_scan_is_a_map_convertible_to_k(tmp_path):
    path = str(tmp_path / "i09-1.nxs")
    with h5py.File(path, "w") as f:
        entry = _gda(f, command="scan smppolar -5 5 2.5 ew4000 /seq.xml")
        data = _region(entry, "VB", (5,))
        entry["instrument/smppolar/value"] = np.linspace(-5, 5, 5)
    with registry.load(path) as scan:
        assert scan.kind == "map" and scan.info["axis0.role"] == "angle"
        np.testing.assert_allclose(scan.x, np.linspace(-5, 5, 5))
        np.testing.assert_array_equal(np.asarray(scan.value), data)


def test_a_photon_energy_scan_is_a_kz_map_on_e_minus_ef(tmp_path):
    path = str(tmp_path / "i09-2.nxs")
    hv = np.array([400.0, 410.0, 420.0])
    energies = np.stack([np.linspace(h - 4.5 - 0.5, h - 4.5 + 0.3, NE) for h in hv])
    with h5py.File(path, "w") as f:
        entry = _gda(f, command="scan pgmenergy 400 420 10 ew4000 /seq.xml")
        _region(entry, "VB", (3,), energies)
        entry["instrument/pgmenergy/value"] = hv
    [row] = registry.list_entries(path)
    assert row["kind"] == "kz map"
    with registry.load(path) as scan:
        assert scan.kind == "kz_map"
        np.testing.assert_allclose(scan.x, hv)
        np.testing.assert_allclose(scan.z, np.linspace(-0.5, 0.3, NE), atol=1e-9)


def test_a_spatial_scan_is_spem_4d(tmp_path):
    path = str(tmp_path / "i09-3.nxs")
    with h5py.File(path, "w") as f:
        entry = _gda(f, command="scan smpmx 0 1 0.5 smpmy 0 3 1 ew4000 /seq.xml")
        data = _region(entry, "VB", (3, 4))
        x, y = np.meshgrid(np.linspace(0, 1, 3), np.linspace(0, 3, 4), indexing="ij")
        entry["VB/smpmx"] = x
        entry["VB/smpmy"] = y
    with registry.load(path) as scan:
        assert scan.kind == "spem_4d"
        np.testing.assert_allclose(scan.y, np.linspace(0, 1, 3))
        np.testing.assert_allclose(scan.x, np.linspace(0, 3, 4))
        np.testing.assert_array_equal(np.asarray(scan.value4d), data)


def test_the_momentum_microscope_stack_and_its_total(tmp_path):
    path = str(tmp_path / "i09-2-9999.nxs")
    ke = np.linspace(20, 21, 11)
    with h5py.File(path, "w") as f:
        entry = _gda(f, root="/entry", version="GDA 9.38.1",
                     command="scan kenergy 20 21 0.1 dld 1.0", name="i09-2")
        stack = np.random.default_rng(0).integers(0, 9, (11, 8, 10)).astype(np.uint16)
        entry["instrument/dld/data"] = stack
        entry["instrument/kenergy/value"] = ke
        entry["instrument/dld_total/mcp_roi_total"] = stack.sum(axis=(1, 2))
        entry["instrument/dld_total/kenergy"] = ke
    assert registry.detect(path).name == NAME
    rows = registry.list_entries(path)
    assert [r["entry"] for r in rows] == ["dld:dld", "total"]
    with registry.load(path, "dld:dld") as scan:
        assert scan.kind == "map" and scan.info["axis0.role"] == "other"
        np.testing.assert_allclose(scan.z, ke)
        assert scan.labels["z"] == "Kinetic energy (eV)"
        cube = np.asarray(scan.value)
        assert cube.shape == (10, 8, 11)
        np.testing.assert_array_equal(cube[3, 2, 5], stack[5, 2, 3])
    with registry.load(path, "total") as scan:
        assert scan.kind == "edc"
        np.testing.assert_allclose(scan.x, ke)
        np.testing.assert_array_equal(scan.value[:, 0], stack.sum(axis=(1, 2)))


def test_xas_and_a_scalar_scan_are_curves(tmp_path):
    path = str(tmp_path / "i09-4.nxs")
    with h5py.File(path, "w") as f:
        entry = _gda(f, command="scan jenergy 2.4 2.5 0.01 sdc jI0")
        energy = np.linspace(2.4, 2.5, 11)
        entry["sdc/data"] = np.linspace(1, 2, 11)
        entry["sdc/energy_demand"] = energy
        entry["jI0/data"] = np.full(11, 2.0)
    rows = registry.list_entries(path)
    assert [r["entry"] for r in rows] == ["xas"]
    with registry.load(path, "xas") as scan:
        assert scan.kind == "edc"
        np.testing.assert_allclose(scan.value[:, 0], np.linspace(1, 2, 11) / 2)
        assert scan.info["curve.channels"] == "sdc / I0|sdc|I0"

    path = str(tmp_path / "i09-5.nxs")
    with h5py.File(path, "w") as f:
        entry = _gda(f, command="scan pgmenergy 500 510 1 sd6iamp31")
        entry["instrument/pgmenergy/value"] = np.arange(500.0, 511.0)
        entry["instrument/sd6iamp31/value"] = np.arange(11.0)
    [row] = registry.list_entries(path)
    with registry.load(path, row["entry"]) as scan:
        assert scan.kind == "edc" and scan.labels["x"] == "Photon energy (eV)"
        np.testing.assert_allclose(scan.value[:, 0], np.arange(11.0))


def test_an_i05_file_is_not_taken_for_i09(tmp_path):
    path = str(tmp_path / "i05-1.nxs")
    with h5py.File(path, "w") as f:
        entry = _gda(f, name="i05")
        entry.require_group("analyser")
    from arpes_viewer.loader.beamlines.i09 import is_i09
    with h5py.File(path, "r") as f:
        assert not is_i09(f, path)
