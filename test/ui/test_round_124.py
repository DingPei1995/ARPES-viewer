"""Version 1.2.4: the k conversions' energy rows (an E - E_F output, the
offset behind a tick box), the 3-D views of a k-map cropped to its filled
planes, the slice series of a map not on screen, a CIF of several data
blocks, the cell typed space group first, and the 3-D Brillouin zone as a
window of its own."""
import os

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QDialog

from arpes_viewer.ui.viewers import windows as W
from arpes_viewer.ui.viewers.widgets import MemoryData

SLIT = np.linspace(-12, 12, 61)
DEFL = np.linspace(-8, 8, 17)
EKIN = np.linspace(54.6, 55.7, 45)
EF = 55.6
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FULLPROF_CIF = """\
data_global
_audit_creation_method  "FullProf Suite"
_journal_coeditor_notes
; ?
;
_publ_contact_author_address            # Address of author
; ?
;
data_#(C)
_chemical_name_systematic
; ?
;
_chemical_formula_sum             ?
_symmetry_space_group_name_H-M       'P 63/m m c'
loop_
    _symmetry_equiv_pos_as_xyz   #<--must include 'x,y,z'
'x,y,z'
'x-y,x,z+1/2'
'-y,x-y,z'
'-x,-y,z+1/2'
'-x+y,-x,z'
'y,-x+y,z+1/2'
'-y,-x,z'
'-x,-x+y,z+1/2'
'-x+y,y,z'
'y,x,z+1/2'
'x,x-y,z'
'x-y,-y,z+1/2'
'-x,-y,-z'
'-x+y,-x,-z+1/2'
'y,-x+y,-z'
'x,y,-z+1/2'
'x-y,x,-z'
'-y,x-y,-z+1/2'
'y,x,-z'
'x,x-y,-z+1/2'
'x-y,-y,-z'
'-y,-x,-z+1/2'
'-x,-x+y,-z'
'-x+y,y,-z+1/2'

_cell_length_a                       6.26066(10)
_cell_length_b                       6.26066(10)
_cell_length_c                       5.82146(9)
_cell_angle_alpha                    90.0000
_cell_angle_beta                     90.0000
_cell_angle_gamma                    120.000
loop_
    _atom_site_label
    _atom_site_fract_x
    _atom_site_fract_y
    _atom_site_fract_z
    _atom_site_U_iso_or_equiv
    _atom_site_occupancy
    _atom_site_adp_type
    _atom_site_type_symbol
 La1  0.33330  0.66670  0.75000  0.0023(10)  1.00000 Uani La
 Cr1  0.00000  0.00000  0.00000 -0.0037(18)  1.00000 Uani Cr
 Ge1  0.19327(17)  0.38656(17)  0.25000  0.0016(8)  1.00004 Uani Ge
"""


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _config(tmp_path, monkeypatch):
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path))


def _cut():
    rng = np.random.default_rng(3)
    return MemoryData("cut", (SLIT, EKIN), rng.random((SLIT.size, EKIN.size)) + 1,
                      {"x": "Angle, slit (deg)", "y": "Kinetic energy (eV)"},
                      source_label="c")


def _map():
    rng = np.random.default_rng(4)
    return MemoryData("map", (DEFL, SLIT, EKIN),
                      rng.random((DEFL.size, SLIT.size, EKIN.size)) + 1,
                      {"x": "Angle, deflector (deg)", "k": "Angle, slit (deg)",
                       "z": "Kinetic energy (eV)"}, source_label="m")


# -- 1. the energy rows of the k conversions ------------------------------------
def test_the_cut_offset_is_off_by_default_and_e_minus_ef_is_an_output(app):
    window = W.CutWindow(_cut(), "c", "gray", False)
    dialog = W.CutKConversionDialog(window)
    assert not dialog.energy_offset_check.isChecked()
    assert not dialog.energy_offset_box.isEnabled()
    dialog.energy_offset_box.setValue(3.0)          # ignored while unticked
    assert dialog.settings()["energy_offset_eV"] == 0.0
    assert not dialog.energy_rows.ef_check.isChecked()
    dialog.energy_rows.ef_check.setChecked(True)
    dialog.energy_rows.ef_box.setValue(EF)
    result = window.run_cut_k_conversion(dialog.settings(), name="k")
    np.testing.assert_allclose(result.scan.y, EKIN - EF, atol=1e-9)
    assert result.scan.labels["y"] == "E - E_F (eV)"
    assert W.subtracted_fermi_level(result) == pytest.approx(EF)
    dialog.close()
    window.close()


def test_the_map_offset_is_off_by_default_and_e_minus_ef_is_an_output(app):
    contour = W.ContourWindow(_map(), "m", "gray", False)
    dialog = W.KConversionDialog(contour)
    assert not dialog.energy_offset_check.isChecked()
    dialog.energy_rows.ef_check.setChecked(True)
    dialog.energy_rows.ef_box.setValue(EF)
    settings = dialog.settings()
    assert settings["energy_offset_eV"] == 0.0
    result = contour.run_k_conversion(settings, name="k", background=False)
    assert result.scan.labels["z"] == "E - E_F (eV)"
    assert float(np.max(result.scan.z)) == pytest.approx(EKIN.max() - EF, abs=0.05)
    dialog.close()
    contour.close()


def test_the_offset_when_ticked_is_added(app):
    window = W.CutWindow(_cut(), "c", "gray", False)
    dialog = W.CutKConversionDialog(window)
    dialog.energy_offset_check.setChecked(True)
    dialog.energy_offset_box.setValue(0.5)
    assert dialog.settings()["energy_offset_eV"] == pytest.approx(0.5)
    result = window.run_cut_k_conversion(dialog.settings(), name="k")
    np.testing.assert_allclose(result.scan.y, EKIN + 0.5, atol=1e-9)
    # with E - E_F as well: E_F is where it is on the cut's own axis
    dialog.energy_rows.ef_check.setChecked(True)
    dialog.energy_rows.ef_box.setValue(EF)
    result = window.run_cut_k_conversion(dialog.settings(), name="k2")
    np.testing.assert_allclose(result.scan.y, EKIN - EF, atol=1e-9)
    dialog.close()
    window.close()


# -- 2. a k-map's 3-D views start at its first filled planes ---------------------
def test_filled_ranges_leave_no_empty_face():
    from arpes_viewer.tools.momentum.kspace import convert_map
    from arpes_viewer.tools.processing.volume import filled_ranges

    th, ph = np.linspace(-12, 12, 41), np.linspace(-15, 15, 51)
    energy = np.linspace(15.5, 16.6, 30)
    kx, ky, e, cube = convert_map(th, ph, energy, np.ones((41, 51, 30)),
                                  n_kx=60, n_ky=60, n_energy=30)
    assert not np.isfinite(cube[0]).all()              # the blank faces
    ranges = filled_ranges(cube, (kx, ky, e))
    keep_x = (kx >= ranges[0][0]) & (kx <= ranges[0][1])
    keep_y = (ky >= ranges[1][0]) & (ky <= ranges[1][1])
    inner = cube[keep_x][:, keep_y]
    for face in (inner[0], inner[-1], inner[:, 0], inner[:, -1]):
        assert np.isfinite(face).all()
    assert ranges[2] == (float(e.min()), float(e.max()))


# -- 3. a slice series of a map whose contour is not on screen --------------------
def test_the_slice_series_figure_survives_its_hidden_contour(app, monkeypatch):
    import arpes_viewer.app as av
    from arpes_viewer.ui.launcher import main_window as main_window_ui
    from arpes_viewer.ui.panels import figure as F

    monkeypatch.setattr(av, "loaded_items", {})
    win = av._MainWindow()
    ui = main_window_ui.Ui_MainWindow()
    ui.setupUi(win)
    monkeypatch.setattr(av, "win", win)
    monkeypatch.setattr(av, "ui", ui)
    monkeypatch.setattr(av, "autosave", lambda data, name: None)
    av.SetConnect()
    kdata = W.KMapData(np.linspace(-1, 1, 21), np.linspace(-1, 1, 25),
                       np.linspace(-0.5, 0.1, 15), np.ones((21, 25, 15)),
                       source_label="km", parameters={})
    av.add_memory_dataset(kdata, "km")
    monkeypatch.setattr(F.SliceSeriesDialog, "exec_", lambda self: QDialog.Accepted)
    figure = av.open_slice_series()
    assert figure is not None and figure.isVisible()
    assert len(figure.figure.panels) == 6
    figure.close()
    win.deleteLater()


# -- 6. CIF, cell input, crystal window, 3-D zone --------------------------------
def test_a_fullprof_cif_with_a_journal_block_first_is_read(tmp_path):
    from arpes_viewer.tools.crystal import structure as S
    structure = S.parse_cif(FULLPROF_CIF)
    assert structure.space_group_number == 194
    assert structure.a == pytest.approx(6.26066)
    assert structure.formula() == "LaCrGe3"
    assert len(structure.atoms) == 10 and len(structure.sites) == 3
    real = os.path.join(os.path.dirname(ROOT), "Test-data",
                        "CJY_113_LaCrGe3powder.cif")
    if os.path.exists(real):
        assert len(S.read_cif(real).atoms) == 10


def test_the_cell_input_follows_the_space_group(app):
    from arpes_viewer.ui.common.cellinput import CellInput
    cell = CellInput()
    cell.space_group_box.setValue(194)                 # hexagonal
    assert not cell.boxes["b"].isEnabled() and cell.boxes["c"].isEnabled()
    assert cell.boxes["gamma"].value() == 120.0 and not cell.boxes["gamma"].isEnabled()
    cell.boxes["a"].setValue(3.3)
    assert cell.boxes["b"].value() == pytest.approx(3.3)
    cell.space_group_box.setValue(225)                 # cubic
    assert cell.boxes["c"].value() == pytest.approx(3.3)
    assert not cell.boxes["c"].isEnabled() and cell.boxes["gamma"].value() == 90.0
    cell.space_group_box.setValue(1)                   # triclinic: all free
    assert all(box.isEnabled() for box in cell.boxes.values())


def test_the_crystal_window_types_in_first_and_reads_a_cif_by_button(app, tmp_path):
    from arpes_viewer.ui.panels.crystal import CrystalDialog
    path = tmp_path / "lacrge3.cif"
    path.write_text(FULLPROF_CIF, encoding="utf-8")
    dialog = CrystalDialog()
    assert not hasattr(dialog, "src_bz")                 # no "from BZ" any more
    assert len(dialog.stepper.steps) == 4                # the zone has gone
    assert dialog.read_cif(str(path)) is not None
    assert dialog.space_group.value() == 194
    assert dialog.cell_boxes["c"].value() == pytest.approx(5.82146)
    assert dialog.atom_table.rowCount() == 3
    assert len(dialog.structure.atoms) == 10
    dialog.close()


def test_the_3d_zone_takes_planes_and_paths_and_goes_to_the_composer(app, tmp_path):
    from arpes_viewer.ui.panels.bz3d import BrillouinZone3DDialog
    path = tmp_path / "lacrge3.cif"
    path.write_text(FULLPROF_CIF, encoding="utf-8")
    dialog = BrillouinZone3DDialog()
    dialog.read_cif(str(path))
    assert dialog.cell_input.space_group() == 194
    dialog.add_plane((0, 0, 1), 0.5)
    dialog.add_plane((1, 0, 0), 0.0, "#ff0000")
    dialog.path_rows[0].edit.setText("G-M-K-G")
    dialog.add_path("A-L-H-A", "#0000ff")
    dialog.refresh()
    assert len(dialog.view.zone_planes) == 3
    assert [p["colour"] for p in dialog.view.zone_paths] == ["#d62728", "#0000ff"]
    lines = [i for i in dialog.view._zone_items()[0] if i[0] == "line"]
    assert any(i[3] == "#0000ff" for i in lines)
    dialog.remove_plane(dialog.plane_rows[-1])
    assert len(dialog.view.zone_planes) == 2
    window = dialog.to_figure_composer(ask=False)
    assert window.figure.panels[0].data.kind == "picture"
    window.close()
    dialog.close()


def test_the_tight_binding_3d_lattice_is_typed_space_group_first(app):
    from arpes_viewer.ui.panels.tightbinding import TightBindingDialog
    dialog = TightBindingDialog(None)
    dialog.mode_3d.setChecked(True)
    dialog.space_group.setValue(139)                   # tetragonal, I
    assert not dialog.b3.isEnabled() and dialog.c3.isEnabled()
    dialog.a3.setValue(4.0)
    assert dialog.b3.value() == pytest.approx(4.0)
    assert not dialog.alpha3.isEnabled()
    dialog.close()


def test_the_tool_panel_places_the_moved_tools(app):
    from arpes_viewer.ui.launcher import main_window as M
    sections = {name: [n for _h, names in groups for n in names]
                for name, groups in M.TOOL_SECTIONS}
    assert "bz3d" in sections["Basic"] and "figure" in sections["Basic"]
    assert "figure" not in sections["Advanced"]
    assert M.TOOLS["bz"][0] == "BZ overlap..."
    assert M.TOOLS["bz3d"][0] == "3D BZ..."
