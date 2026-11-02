"""Analysis cores: Igor export, summing
repeated scans, ridge detection, the tight-binding fit, the detector
corrections and the crystal structure. All Qt-free."""
import os
import struct

import numpy as np
import pytest

from arpes_viewer.loader import registry  # noqa: F401  -- before the SES reader
from arpes_viewer.tools.crystal import structure as S
from arpes_viewer.tools.crystal import tightbinding as TB
from arpes_viewer.tools.output import igor
from arpes_viewer.tools.processing import detector as DT
from arpes_viewer.tools.processing import repeats as R
from arpes_viewer.tools.processing import ridge as RD

#: Rock salt, written by hand: only the four face-centring translations are
#: listed as symmetry operations, which is enough to build the cell.
NACL_CIF = """# NaCl, rock salt, written by hand for the tests: only the four
# face-centring translations are listed, which is enough to build the cell.
data_NaCl
_chemical_formula_sum 'Cl Na'
_symmetry_space_group_name_H-M 'F m -3 m'
_cell_length_a 5.6402(3)
_cell_length_b 5.6402(3)
_cell_length_c 5.6402(3)
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
loop_
_symmetry_equiv_pos_site_id
_symmetry_equiv_pos_as_xyz
1 'x, y, z'
2 'x, y+1/2, z+1/2'
3 'x+1/2, y, z+1/2'
4 'x+1/2, y+1/2, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
Na1 Na+ 0 0 0 1
Cl1 Cl- 0.5 0.5 0.5 1
"""


@pytest.fixture
def nacl_path(tmp_path):
    path = tmp_path / "nacl.cif"
    path.write_text(NACL_CIF, encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------
# Igor
# --------------------------------------------------------------------------
def _cut_item(name="my cut 1", x=None):
    x = np.linspace(-10, 10, 5) if x is None else x
    e = np.linspace(50, 51, 4)
    return {"name": name, "kind": "cut", "axes": (x, e),
            "labels": {"x": "kx (Å⁻¹)", "y": "Kinetic energy (eV)"},
            "value": np.arange(x.size * 4.0).reshape(x.size, 4),
            "info": {"hv": 60.0, "pol": "LH"}}


def test_ibw_round_trips_through_the_programs_own_reader(tmp_path):
    from arpes_viewer.loader.formats.ses import read_ibw
    item = _cut_item()
    path = igor.write_datasets(str(tmp_path / "a.ibw"), [item], "ibw")[0]
    wave = read_ibw(path)
    assert wave.name == "my_cut_1" and wave.shape == (5, 4)
    assert wave.start == pytest.approx((-10.0, 50.0))
    assert wave.delta == pytest.approx((5.0, 1 / 3))
    assert wave.units == ("Å^-1", "eV")
    assert "hv=60" in wave.note and "pol=LH" in wave.note
    raw = np.fromfile(path, dtype=wave.dtype, offset=wave.offset,
                      count=20).reshape(wave.shape, order="F")
    assert np.array_equal(raw, item["value"])
    head = open(path, "rb").read(384)
    assert sum(struct.unpack("<192h", head)) & 0xFFFF == 0      # checksum


def test_itx_holds_every_wave_with_scaling_and_an_uneven_axis_wave(tmp_path):
    uneven = np.array([0.0, 1.0, 3.0, 6.0, 10.0])
    path = igor.write_datasets(str(tmp_path / "b.itx"),
                               [_cut_item("a"), _cut_item("a", uneven)], "itx")[0]
    text = open(path, encoding="utf-8-sig").read()
    assert text.startswith("IGOR")
    assert "WAVES/D/N=(5,4) 'a'" in text and "WAVES/D/N=(5,4) 'a_2'" in text
    assert "SetScale/P y 50.0,0.3333333333333333" in text
    assert "WAVES/D/N=(5) 'a_2_x'" in text           # the uneven axis
    assert "X Note 'a', \"pol=LH\"" in text


def test_a_cube_is_written_layer_by_layer():
    cube = np.arange(24.0).reshape(2, 3, 4)
    spec = igor.IgorWaveSpec("w", cube, [np.arange(2), np.arange(3), np.arange(4)],
                             ["x", "y", "z"])
    lines = igor.itx_text([spec]).split("\r\n")
    begin = lines.index("BEGIN")
    first = lines[begin + 1].split("\t")
    assert first == ["0", "4", "8"]            # cube[0, :, 0]
    assert lines[begin + 3] == "" or lines[begin + 4] == ""


def test_igor_names_are_legal_and_unique():
    assert igor.igor_name("1 cut (LH)") == "w1_cut_LH"
    assert igor.igor_name("x" * 50) == "x" * 31
    assert igor.igor_name("a", {"a"}) == "a_2"
    assert igor.split_label("Kinetic energy (eV)") == ("Kinetic energy", "eV")


# --------------------------------------------------------------------------
# Repeated scans
# --------------------------------------------------------------------------
K = np.linspace(-1, 1, 60)
E = np.linspace(-0.5, 0.1, 121)


def _spectrum(shift=0.0, width=0.03):
    kk, ee = np.meshgrid(K, E, indexing="ij")
    band = 1 / (1 + ((ee - shift - (0.4 * kk ** 2 - 0.3)) / width) ** 2)
    return 200 * (band + 0.2) / (1 + np.exp((ee - shift) / 0.01)) + 5


def _scans():
    rng = np.random.default_rng(1)
    settings = [(0, .03), (0, .03), (.012, .03), (0, .03), (0, .06)]
    return [rng.poisson(_spectrum(*s)).astype(float) for s in settings]


def test_changed_scans_are_flagged_and_the_shift_measured():
    scans = _scans()
    d = R.diagnose(lambda i: scans[i], 5, [(K, E)] * 5, 1)
    assert d.flags == [False, False, True, False, True]
    assert d.shifts[2] == pytest.approx(0.012, abs=0.0015)
    assert np.all(np.abs(np.delete(d.shifts, 2)) < 0.0015)


def test_noise_only_repeats_flag_nothing():
    rng = np.random.default_rng(3)
    scans = [rng.poisson(_spectrum()).astype(float) for _ in range(4)]
    d = R.diagnose(lambda i: scans[i], 4, [(K, E)] * 4, 1)
    assert not any(d.flags)
    assert np.all(np.abs(d.chi2 - 1) < 0.15)          # counting noise only


def test_sum_keeps_counts_and_undoes_shifts():
    scans = _scans()
    axes, total, _ = R.sum_repeats(lambda i: scans[i], [(K, E)] * 5, [0, 1, 3], 1)
    assert total.sum() == pytest.approx(scans[0].sum() + scans[1].sum()
                                        + scans[3].sum())
    shifts = np.array([0, 0, 0.02, 0, 0])
    axes, total, notes = R.sum_repeats(lambda i: scans[i], [(K, E)] * 5,
                                       [0, 2], 1, shifts=shifts, mode="mean")
    assert axes[1].size < E.size and notes


def test_grids_that_differ_are_put_on_the_first():
    plan = R.grid_plan([(K, E), (K, E + 0.0123)])
    assert not plan["exact"] and plan["target"][1].max() <= E.max()
    with pytest.raises(ValueError):
        R.grid_plan([(K, E), (K, E + 5)])


# --------------------------------------------------------------------------
# Ridge detection
# --------------------------------------------------------------------------
def _band_image():
    k = np.linspace(-0.6, 0.6, 301)
    e = np.linspace(-0.4, 0.05, 226)
    kk, ee = np.meshgrid(k, e, indexing="ij")
    image = (1 / (1 + ((ee - (1.2 * kk ** 2 - 0.3)) / 0.02) ** 2)
             / (1 + np.exp(ee / 0.005)) + 0.1)
    return k, e, np.random.default_rng(0).poisson(image * 300).astype(float)


def test_ridge_points_sit_on_the_band():
    k, e, image = _band_image()
    result = RD.ridges(image, k, e, 0.01, 0.008, threshold=0.1)
    points = result.points[result.points[:, 1] < -0.05]
    error = points[:, 1] - (1.2 * points[:, 0] ** 2 - 0.3)
    assert len(points) > 200
    assert np.median(np.abs(error)) < 0.001                  # 1 meV


def test_ridges_do_not_depend_on_the_axis_units():
    k, e, image = _band_image()
    a = RD.ridges(image, k, e, 0.01, 0.008, threshold=0.1)
    b = RD.ridges(image, k, e * 1000, 0.01, 8.0, threshold=0.1)
    assert len(a.points) == len(b.points)
    assert np.allclose(b.points[:, 1] / 1000, a.points[:, 1])


def test_ridge_cube_goes_plane_by_plane():
    k, e, image = _band_image()
    cube = np.stack([image] * 3)
    out, points = RD.ridge_cube(cube, (np.arange(3.0), k, e), 0, (0.01, 0.008),
                                threshold=0.1)
    assert out.shape == cube.shape and points.shape[1] == 4
    assert set(np.unique(points[:, 0])) == {0.0, 1.0, 2.0}


# --------------------------------------------------------------------------
# Tight binding
# --------------------------------------------------------------------------
def test_shells_count_the_neighbours():
    square = TB.shells(TB.lattice_2d(3.5, 3.5, 90), 3)
    assert [len(v) for _, v in square] == [4, 4, 4]
    hexagonal = TB.shells(TB.lattice_2d(2.46, 2.46, 120), 2)
    assert [len(v) for _, v in hexagonal] == [6, 6]
    fcc = TB.shells(np.array([[0, .5, .5], [.5, 0, .5], [.5, .5, 0]]) * 4, 2)
    assert [len(v) for _, v in fcc] == [12, 6]



def test_shells_are_symmetry_orbits_not_just_distances():
    """In a tetragonal cell with c = a sqrt(2), (1 1 0) and (0 0 1) have the
    same length but are not equivalent: one hopping each."""
    tetragonal = np.diag([3.0, 3.0, 3.0 * np.sqrt(2.0)])
    found = TB.shells(tetragonal, 4)
    assert [len(v) for _, v in found] == [4, 4, 2, 8]
    assert found[1][0] == pytest.approx(found[2][0])
    assert [TB.shell_label(tetragonal, v) for _, v in found[1:3]] == [
        "<1 1 0>", "<0 0 1>"]


def test_a_space_group_splits_what_the_lattice_alone_does_not():
    """A body-centred tetragonal cell with c = a sqrt(2) is metrically fcc:
    its own symmetry puts 12 neighbours in the first shell, the space group
    I4/mmm (139) splits them 8 + 4. P-3 (147) splits a hexagonal lattice's
    12 <1 1 1>-type neighbours into two chiral orbits of 6."""
    from arpes_viewer.tools.crystal.lattice import (
        LatticeParams, point_group_operations, primitive_vectors)
    bct = LatticeParams(3, 3, 3 * np.sqrt(2.0), 90, 90, 90, space_group=139)
    vectors = primitive_vectors(bct)
    assert len(TB.shells(vectors, 1)[0][1]) == 12
    symmetry = TB.lattice_symmetry(vectors, point_group_operations(bct))
    assert [len(v) for _, v in TB.shells(vectors, 2, symmetry=symmetry)] == [8, 4]
    trigonal = LatticeParams(3, 3, 5, 90, 90, 120, space_group=147)
    vectors = primitive_vectors(trigonal)
    symmetry = TB.lattice_symmetry(vectors, point_group_operations(trigonal))
    assert [len(v) for _, v in TB.shells(vectors, 5, symmetry=symmetry)] == [
        6, 2, 6, 6, 6]
    # integer matrices: the same whatever the azimuth
    turned = TB.rotate(vectors, 23.0)
    assert [len(v) for _, v in TB.shells(turned, 5, symmetry=symmetry)] == [
        6, 2, 6, 6, 6]


def test_a_symmetry_that_does_not_fit_the_lattice_is_refused():
    quarter_turn = np.array([[[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]])
    with pytest.raises(ValueError, match="does not map the lattice"):
        TB.lattice_symmetry(np.diag([3.0, 4.0, 5.0]), quarter_turn)


def _two_band_points(energies=(-0.3, -0.15, 0.0, 0.1), noise=0.002, seed=1):
    """Contour points of two hybridised bands on a square lattice: band a
    with one shell, band b with two, a constant coupling."""
    vectors = TB.lattice_2d(3.5, 3.5, 90)
    true = np.array([-0.4, -0.25, 0.3, 0.2, 0.03, 0.06])
    kx = np.linspace(-0.9, 0.9, 181)
    grid = np.array(np.meshgrid(kx, kx, indexing="ij")).reshape(2, -1).T
    lower, upper, *_ = TB.two_band_energies(
        TB.design_matrix(grid, TB.shells(vectors, 2)), true, 1, 2, 0)
    rng = np.random.default_rng(seed)
    k, energy, side = [], [], []
    for e in energies:
        for band, label in ((lower, TB.LOWER), (upper, TB.UPPER)):
            near = np.abs(band - e) < 0.004
            k.append(grid[near])
            energy.append(np.full(near.sum(), e) + rng.normal(0, noise, near.sum()))
            side.append(np.full(near.sum(), label))
    return (vectors, true, grid, np.vstack(k), np.concatenate(energy),
            np.concatenate(side))


def test_two_hybridised_bands_are_recovered_without_labels():
    vectors, true, grid, k, energy, side = _two_band_points()
    fit = TB.fit_two_band(k, energy, vectors, 1, n_shells_b=2, n_hybrid=0)
    assert fit.params == pytest.approx(true, abs=0.003)
    assert np.mean(fit.branch == side) > 0.97
    gap, _where = fit.gap(grid)
    assert gap == pytest.approx(2 * 0.06, abs=0.004)       # 2|V| at the crossing
    assert not fit.warning and fit.rms < 0.005
    names = [row[0] for row in fit.table()]
    assert names[0] == "e_a" and any(n.startswith("t2_b") for n in names)
    assert names[-1].startswith("v0")
    # a few labelled points are honoured, the rest decided by the fit
    labels = np.where(np.arange(len(side)) % 20 == 0, side, TB.AUTO)
    labelled = TB.fit_two_band(k, energy, vectors, 1, n_shells_b=2, branch=labels)
    assert labelled.params == pytest.approx(true, abs=0.003)
    assert np.all(labelled.branch[labels != TB.AUTO] == side[labels != TB.AUTO])


def test_two_bands_need_two_energies_and_enough_points():
    vectors, _true, _grid, k, energy, _side = _two_band_points(energies=(-0.15,), noise=0.0)
    with pytest.raises(ValueError, match="two or more energies"):
        TB.fit_two_band(k, energy, vectors, 1)
    with pytest.raises(ValueError, match="parameters need at least"):
        TB.fit_two_band(k[:3], np.array([0.0, 0.1, 0.2]), vectors, 2)


def test_branch_column_is_read(tmp_path):
    path = tmp_path / "pts.csv"
    path.write_text("kx,ky,E,branch\n0.1,0.2,-0.1,lower\n0.3,0.1,0.0,upper\n"
                    "0.2,0.2,0.1,\n")
    k, energy, branch = TB.read_points(str(path), with_branch=True)
    assert branch.tolist() == [TB.LOWER, TB.UPPER, TB.AUTO]
    assert len(TB.read_points(str(path))) == 2

def _true_model(azimuth=0.0):
    vectors = TB.rotate(TB.lattice_2d(3.5, 3.5, 90), azimuth)
    return TB.TBFit(vectors, TB.shells(vectors, 2), 0.1, [-0.3, 0.05], 0,
                    [0, 0], 0, 0, False)


def test_the_fit_recovers_the_hoppings_with_errors():
    rng = np.random.default_rng(0)
    model = _true_model()
    k = rng.uniform(-0.9, 0.9, (400, 2))
    energies = model.energy(k) + rng.normal(0, 0.005, 400)
    fit = TB.fit(k, energies, model.vectors, 2)
    assert fit.e0 == pytest.approx(0.1, abs=0.002)
    assert fit.t == pytest.approx([-0.3, 0.05], abs=0.002)
    assert np.all(fit.t_err < 0.001) and fit.rms == pytest.approx(0.005, rel=0.2)


def test_one_contour_fixes_the_shape_only_and_says_when_too_many_shells():
    model = _true_model()
    kx = np.linspace(-0.9, 0.9, 301)
    grid = TB.evaluate(model, kx, kx)
    ii, jj = np.nonzero(np.abs(grid) < 0.003)
    k = np.column_stack([kx[ii], kx[jj]])
    fit = TB.fit(k, np.zeros(len(k)), model.vectors, 2)
    assert fit.shape_only and fit.t[0] == -1.0
    assert fit.t[1] / fit.t[0] == pytest.approx(0.05 / -0.3, abs=0.01)
    assert not fit.warning
    assert TB.fit(k, np.zeros(len(k)), model.vectors, 3).warning


def test_stray_points_get_no_weight_and_the_azimuth_is_found():
    rng = np.random.default_rng(2)
    model = _true_model(azimuth=4.0)
    k = rng.uniform(-0.9, 0.9, (300, 2))
    energies = model.energy(k)
    energies[:30] += rng.uniform(0.05, 0.2, 30)               # wrong points
    fit = TB.fit_azimuth(k, energies, TB.lattice_2d(3.5, 3.5, 90), 2,
                         around=0, span=10)
    assert fit.azimuth_deg == pytest.approx(4.0, abs=0.1)
    assert fit.t == pytest.approx([-0.3, 0.05], abs=0.002)
    assert fit.outliers >= 25


def test_points_are_read_from_the_ridge_windows_file(tmp_path):
    path = tmp_path / "ridges.csv"
    path.write_text("E - E_F (eV),kx (Å⁻¹),ky (Å⁻¹),strength\n"
                    "0,0.1,0.2,1\n-0.1,0.3,0.4,1\n", encoding="utf-8")
    k, energies = TB.read_points(str(path))
    assert k.tolist() == [[0.1, 0.2], [0.3, 0.4]]
    assert energies.tolist() == [0.0, -0.1]


# --------------------------------------------------------------------------
# Detector corrections
# --------------------------------------------------------------------------
def test_the_keystone_is_stretched_to_its_first_edge_keeping_counts():
    x = np.linspace(-15, 15, 301)
    y = np.linspace(50, 52, 201)
    xx, yy = np.meshgrid(x, y, indexing="ij")
    true = np.where(np.abs(xx) <= 10, 1 + 0.5 * np.cos(xx / 3), 0.0)
    scale = (6 + (y - 50) * 2) / 10
    source = np.stack([np.interp(x / s, x, true[:, j], left=0, right=0) / s
                       for j, s in enumerate(scale)], axis=1)
    keystone = DT.Keystone.from_corners([(-10, 52), (10, 52), (-6, 50), (6, 50)])
    out = DT.keystone_correct(source, x, y, keystone)
    inside = np.abs(xx) < 9.5
    assert np.nanmax(np.abs(out - true)[inside]) < 0.002
    assert np.nansum(out[:, 0]) == pytest.approx(np.nansum(source[:, 0]), rel=0.01)


@pytest.mark.parametrize("method", DT.METHODS)
def test_a_region_is_patched_from_its_surroundings(method):
    x = np.linspace(-15, 15, 101)
    y = np.linspace(50, 52, 81)
    xx, yy = np.meshgrid(x, y, indexing="ij")
    plane = 1 + 0.1 * xx + 0.05 * (yy - 50)       # linear: every fill is exact
    region = DT.Region(-2, 2, 50.5, 50.8)
    broken = plane.copy()
    broken[region.mask(x, y)] = 100
    fixed = DT.patch_regions(broken, x, y, [region], method)
    assert np.abs(fixed - plane).max() < 1e-9


def test_bad_pixels_are_found_but_noise_is_not():
    x = np.linspace(-15, 15, 101)
    y = np.linspace(50, 52, 81)
    rng = np.random.default_rng(0)
    frame = 100 + rng.normal(0, 3, (101, 81))
    assert DT.find_bad_regions(frame, x, y) == []
    frame[50, 40] = 400
    frame[10:12, 70] = 0
    found = DT.find_bad_regions(frame, x, y)
    assert len(found) == 2
    assert found[0].mask(x, y)[50, 40]


def test_a_map_is_corrected_slice_by_slice_and_k_data_refused():
    x = np.linspace(-15, 15, 51)
    y = np.linspace(50, 52, 41)
    cube = np.ones((3, 51, 41))
    cube[:, 25, 20] = 50
    region = DT.Region(-0.4, 0.4, 50.97, 51.03)
    out = DT.apply_to(cube, (np.arange(3.0), x, y), "map", regions=[region])
    assert np.allclose(out, 1.0)
    assert DT.not_on_detector({"kconv.azimuth": 0})
    assert DT.not_on_detector({"degrid.contrast": 1.0,
                               "proc.step.1": "degrid(x=1)"}) is None


# --------------------------------------------------------------------------
# Crystal structure
# --------------------------------------------------------------------------
def test_a_cif_is_read_and_its_symmetry_applied(nacl_path):
    nacl = S.read_cif(nacl_path)
    assert nacl.a == pytest.approx(5.6402)
    assert len(nacl.atoms) == 8 and nacl.formula() == "NaCl"
    assert {a.element for a in nacl.atoms} == {"Na", "Cl"}


def test_symmetry_operations_and_element_names():
    rotation, translation = S.parse_symop("-y, x-y, z+1/3")
    assert rotation.tolist() == [[0, -1, 0], [1, -1, 0], [0, 0, 1]]
    assert translation == pytest.approx([0, 0, 1 / 3])
    assert S.element_of("Bi1") == "Bi" and S.element_of("O2-") == "O"
    assert S.element_of("SE3") == "Se"


def test_planes_spacings_and_layers():
    nacl = S.parse_cif(NACL_CIF)
    normal, d = S.plane_normal(nacl, (1, 1, 1))
    assert d == pytest.approx(5.6402 / np.sqrt(3))
    layers = S.atomic_layers(nacl, (1, 1, 1))
    # (111) of rock salt: pure Na and pure Cl layers in turn, d/2 apart
    assert [set(c) for _h, c in layers[:4]] == [{"Na"}, {"Cl"}, {"Na"}, {"Cl"}]
    assert layers[1][0] - layers[0][0] == pytest.approx(d / 2)
    outline = S.plane_outline(nacl, (1, 1, 1), 1.5 * d)
    assert len(outline) == 6                          # a hexagon
    assert np.allclose(outline @ normal, 1.5 * d)
    assert len(S.plane_outline(nacl, (1, 1, 1), 100.0)) == 0


def test_lattice_points_of_a_centred_cell():
    assert len(S.lattice_point_atoms("F")) == 4
    assert len(S.lattice_point_atoms("I")) == 2
    s = S.Structure(3, 3, 3, atoms=S.lattice_point_atoms("P"))
    atoms, xyz = S.cartesian_atoms(s, (1, 1, 1))
    assert len(atoms) == 8                             # the eight corners
