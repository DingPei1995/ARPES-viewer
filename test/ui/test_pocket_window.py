"""The Fermi-pocket window: a tool-panel button for k-maps, the notice it
carries, the contour on screen, several pockets counted together, and the
result kept."""
import os
import sys

import numpy as np
import pytest

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import test_pocket as synthetic  # noqa: E402

from arpes_viewer.ui.viewers.widgets import MemoryData  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def _map(hole=False, info=None):
    return MemoryData(
        "k_map", (synthetic.KX, synthetic.KY, synthetic.ENERGY),
        synthetic.cube(0.01, hole=hole),
        {"x": "kx (Å⁻¹)", "k": "ky (Å⁻¹)", "z": "E - E_F (eV)"},
        source_label="FS", source_info=dict(info or {}))


def _open(**kwargs):
    from arpes_viewer.ui.panels.pocket import PocketDialog
    dialog = PocketDialog(("FS", _map(**kwargs)))
    dialog._timer.blockSignals(True)            # traced when the test asks
    return dialog


def test_the_tool_panel_has_the_button_for_k_maps_only():
    from arpes_viewer.ui.launcher import list_actions, main_window
    text, tip = main_window.TOOLS["pocket"]
    assert "quasi-2D" in text
    assert "Under test" in tip and "quasi-two-dimensional" in tip
    advanced = dict(main_window.TOOL_SECTIONS)["Advanced"]
    maps = [keys for title, keys in advanced if title.startswith("3D only")][0]
    assert "pocket" in maps
    assert list_actions.RULES["pocket"][:2] == ("one", frozenset({"k_map"}))


def test_the_window_says_what_it_is_for(app):
    from arpes_viewer.ui.panels import pocket
    dialog = _open()
    assert "under test" in dialog.windowTitle().lower()
    assert "quasi-2D" in dialog.windowTitle()
    notices = [w.text() for w in dialog.findChildren(type(dialog.result_label))
               if "Quasi-two-dimensional samples only" in w.text()]
    assert len(notices) == 1 and "Under test" in notices[0]
    assert "three-dimensional" in notices[0]
    assert dialog.ef.value() == 0.0 and dialog.energy.value() == 0.0
    dialog.close()
    with pytest.raises(ValueError, match="k-map"):
        pocket.PocketDialog(("m", MemoryData(
            "map", (synthetic.KX, synthetic.KY, synthetic.ENERGY),
            np.ones((synthetic.KX.size, synthetic.KY.size,
                     synthetic.ENERGY.size)),
            {"x": "a", "k": "b", "z": "E"}, source_label="m")))
    # an energy axis that is not E - E_F is pointed out
    kinetic = MemoryData("k_map", (synthetic.KX, synthetic.KY,
                                   synthetic.ENERGY + 16.5),
                         synthetic.cube(),
                         {"x": "kx (Å⁻¹)", "k": "ky (Å⁻¹)",
                          "z": "Kinetic energy (eV)"}, source_label="kin")
    other = pocket.PocketDialog(("kin", kinetic))
    assert any("not E − E_F" in w.text()
               for w in other.findChildren(type(other.result_label)))
    other.close()


def test_a_pocket_is_traced_counted_and_kept(app, tmp_path):
    dialog = _open(info={"bz.a": 3.3, "bz.b": 3.3, "bz.gamma": 120.0})
    assert dialog.cell_a.value() == 3.3 and dialog.cell_gamma.value() == 120.0
    dialog.energy.setValue(-0.05)
    dialog.half_width.setValue(0.006)
    dialog.r_min.setValue(0.1)
    dialog.r_max.setValue(0.6)
    numbers = dialog.update_trace()                     # from (0, 0)
    assert numbers["rays_kept"] == 72
    assert numbers["area"] == pytest.approx(synthetic.area_of(-0.05), rel=0.02)
    # the centre: found from the contour, and the target follows
    x, y = dialog.recentre()
    assert (x, y) == pytest.approx(synthetic.CENTRE, abs=0.008)
    assert dialog.target.pos().x() == pytest.approx(x, abs=1e-4)
    dialog.fold.setValue(6)
    numbers = dialog.update_trace()
    assert numbers["area"] == pytest.approx(synthetic.area_of(-0.05), rel=0.01)
    zone = (2 * np.pi) ** 2 / (3.3 * 3.3 * np.sin(np.radians(120)))
    assert numbers["per_cell"] == pytest.approx(2 * numbers["area"] / zone)
    text = dialog.result_label.text()
    assert "Å⁻²" in text and "carriers per cell" in text and " T." in text
    assert "statistical" in text
    # drawn: the points, the contour, the ring, one ray with its fit
    assert len(dialog.points.getData()[0]) == 72
    assert len(dialog.contour_line.getData()[0]) > 100
    dialog.ray_angle.setValue(90.0)
    assert "k_F =" in dialog.ray_note.text()
    # dragging the target moves the centre
    dialog.target.setPos(0.0, 0.0)
    dialog._target_moved()
    assert dialog.centre() == (0.0, 0.0)
    dialog.set_centre(x, y)

    # spin-split, three of them: the count follows, the area does not
    dialog.spin_choice.setCurrentIndex(1)
    dialog.pockets.setValue(3)
    split = dialog.update_trace()
    assert split["area"] == pytest.approx(numbers["area"])
    assert split["density"] == pytest.approx(1.5 * numbers["density"])
    dialog.spin_choice.setCurrentIndex(0)
    dialog.pockets.setValue(1)
    dialog.update_trace()

    # area against energy: the mass, the kind of pocket, the area at E_F
    series = dialog.run_series(np.linspace(-0.02, -0.2, 8), background=False)
    assert series.carrier() == "electron" and dialog.carrier.currentIndex() == 0
    assert dialog.plots.currentWidget() is dialog.energy_plot
    numbers = dialog.numbers()
    assert numbers["mass"] == pytest.approx(
        synthetic.MASS / np.sqrt(1 - synthetic.WARP ** 2), rel=0.03)
    assert "an electron pocket" in dialog.result_label.text()
    dialog.energy.setValue(-0.06)                 # another plane: series kept
    dialog.update_trace()
    assert dialog.series is not None
    dialog.r_max.setValue(0.55)                   # another ring: it is stale
    dialog.update_trace()
    assert dialog.series is None and "mass" not in dialog.numbers()
    dialog.run_series(np.linspace(-0.02, -0.2, 8), background=False)

    # several pockets counted together: electrons minus holes
    first = dialog.keep()
    dialog.carrier.setCurrentIndex(1)
    second = dialog.keep()
    assert first["name"].startswith("e1") and second["name"].startswith("h2")
    assert dialog.table.rowCount() == 2
    assert dialog.totals()["per_cell"] == pytest.approx(0.0, abs=1e-12)
    dialog.table.selectRow(1)
    dialog.remove_kept()
    assert dialog.table.rowCount() == 1
    assert dialog.totals()["per_cell"] == pytest.approx(first["per_cell"])
    assert "Luttinger" in dialog.total_label.text()

    # kept: curves in the list, and a table
    listed = []
    dialog.datasetsCreated.connect(listed.extend)
    made = dialog.export()
    assert listed == made and [d.kind for d in made] == ["mdc", "edc"]
    assert made[0].source_label == "FS [pocket]"
    info = made[0].scan.info
    assert "k_F" in info["curve.channels"] and "σ k_F" in info["curve.channels"]
    assert "quasi-two-dimensional" in info["proc.pocket.notice"]
    assert info["proc.pocket.area"] == pytest.approx(dialog.numbers()["area"])
    assert made[0].scan.value.shape == (72, 4)
    path = dialog.save_table(str(tmp_path / "pocket.csv"))
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    notes = [line for line in lines if line.startswith("#")]
    assert "quasi-two-dimensional" in notes[0]
    assert any(line.startswith("# area:") for line in notes)
    assert any("kept pocket e1" in line for line in notes)
    assert any(line.startswith("# area at E =") for line in notes)
    table = np.loadtxt(path, delimiter=",", skiprows=len(notes) + 1)
    assert table.shape == (72, 8)
    dialog.close()


def test_a_ring_that_misses_the_band_is_said(app):
    dialog = _open()
    dialog.energy.setValue(-0.05)
    dialog.r_min.setValue(0.02)
    dialog.r_max.setValue(0.08)                   # inside the pocket: nothing
    assert dialog.update_trace() is None
    assert "rays found a band" in dialog.result_label.text()
    assert dialog.numbers() is None and dialog.keep() is None
    assert dialog.export() == [] and dialog.recentre() is None
    dialog.close()


def test_a_hole_pocket_is_recognised(app):
    dialog = _open(hole=True)
    dialog.energy.setValue(-0.03)
    dialog.half_width.setValue(0.006)
    dialog.r_min.setValue(0.05)
    dialog.r_max.setValue(0.6)
    dialog.set_centre(*synthetic.CENTRE)
    dialog.run_series(np.linspace(-0.02, -0.12, 8), background=False)
    assert dialog.carrier.currentIndex() == 1
    assert dialog.numbers()["mass"] < 0 and "a hole pocket" in dialog.result_label.text()
    assert dialog.keep()["carrier"] == "hole"
    assert dialog.totals()["density"] < 0
    dialog.close()
