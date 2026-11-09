"""The minimum-gradient window (a tool-panel button of its own, for cuts
and maps) and the self-energy window (a stated bare band, the
Kramers-Kronig check, and the result kept)."""
import os
import sys

import numpy as np
import pytest

from PyQt5.QtWidgets import QApplication

from arpes_viewer.ui.viewers.widgets import MemoryData
import arpes_viewer.tools.processing.process as P

K = np.linspace(-0.5, 0.5, 101)
ENERGY = np.linspace(-0.4, 0.05, 80)
KY = np.linspace(-0.3, 0.3, 21)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def _values():
    kk, ee = np.meshgrid(K, ENERGY, indexing="ij")
    return 1 / (1 + ((kk - (ee + 0.1) / 2.0) / 0.02) ** 2) + 0.05


def _cut():
    return MemoryData("cut", (K, ENERGY), _values(),
                      {"x": "k (Å⁻¹)", "y": "E - E_F (eV)"}, source_label="k")


def _map():
    cube = np.repeat(_values()[None], KY.size, axis=0)
    return MemoryData("k_map", (KY, K, ENERGY), cube,
                      {"x": "ky (Å⁻¹)", "k": "kx (Å⁻¹)", "z": "E - E_F (eV)"},
                      source_label="m")


# -- minimum gradient ----------------------------------------------------------
def test_the_tool_panel_has_a_minimum_gradient_button():
    from arpes_viewer.ui.launcher import list_actions, main_window
    assert main_window.TOOLS["gradient"][0] == "Minimum gradient..."
    advanced = dict(main_window.TOOL_SECTIONS)["Advanced"]
    assert "gradient" in advanced[0][1]                 # cuts and maps
    assert list_actions.RULES["gradient"][1] == list_actions.PLANES
    assert "gradient" in list_actions.PROCESSING


def test_the_minimum_gradient_window_on_a_cut(app):
    from arpes_viewer.ui.panels.process import ProcessDialog
    dialog = ProcessDialog([("k", _cut())], start="gradient")
    assert dialog.windowTitle() == "Minimum gradient (2D)"
    assert dialog.tabs.count() == 1
    key, params, _run = dialog.operation()
    assert key == "gradient" and params["form"] == "ratio"
    dialog.grad_smooth_x.setValue(0.0)
    dialog.grad_smooth_y.setValue(0.0)
    made = dialog.apply(background=False)
    assert len(made) == 1
    result = made[0]
    assert result.source_label == "k [grad]"
    np.testing.assert_allclose(result.scan.value,
                               P.minimum_gradient(_values(), [K, ENERGY]))
    history = [str(v) for key, v in result.scan.info.items()
               if key.startswith("proc.step")]
    assert any("gradient" in step and "form=ratio" in step for step in history)
    # the other two pictures; |grad I| has no floor to record
    dialog.grad_form.setCurrentIndex(2)
    key, params, run = dialog.operation()
    assert params["form"] == "modulus" and "floor" not in params
    np.testing.assert_allclose(
        run(_values(), [K, ENERGY])[0],
        P.minimum_gradient(_values(), [K, ENERGY], form="modulus"))
    dialog.close()


def test_the_curvature_window_no_longer_hides_it(app):
    from arpes_viewer.ui.panels.process import ProcessDialog
    dialog = ProcessDialog([("k", _cut())], start="curvature")
    modes = [dialog.curv_mode.itemText(i) for i in range(dialog.curv_mode.count())]
    assert len(modes) == 3 and not any("radient" in mode for mode in modes)
    assert dialog.operation()[0] == "curvature"
    dialog.close()
    whole = ProcessDialog([("k", _cut())])              # every operation
    assert [whole.tabs.tabText(i) for i in range(whole.tabs.count())] == [
        "Smooth", "Derivative", "Curvature", "Minimum gradient",
        "Background subtraction", "Symmetrise"]
    for index in range(whole.tabs.count()):             # each tab has its own
        whole.tabs.setCurrentIndex(index)
        whole.operation()
    whole.close()


def test_the_minimum_gradient_window_on_a_map(app):
    from arpes_viewer.ui.panels.volume import VolumeProcessDialog
    dialog = VolumeProcessDialog([("m", _map())], start="gradient")
    assert "Minimum gradient" in dialog.windowTitle()
    texts = [dialog.plane_operation.itemText(i)
             for i in range(dialog.plane_operation.count())]
    assert texts == ["Minimum gradient I / |∇I|", "Minimum gradient 1 / |∇I|",
                     "Gradient modulus |∇I|"]
    assert not dialog.plane_floor.isHidden() and dialog.plane_a0.isHidden()
    dialog.plane_normal.setCurrentIndex(0)              # kx–E planes, at each ky
    key, params, dim, run = dialog.plane_operation_function()
    assert key == "gradient" and dim == 0 and params["floor"] == 0.05
    np.testing.assert_allclose(run(_values()),
                               P.minimum_gradient(_values(), [K, ENERGY]))
    dialog.plane_operation.setCurrentIndex(2)
    key, params, dim, run = dialog.plane_operation_function()
    assert "floor" not in params
    dialog.close()
    # the general 3-D window keeps its operations where they were
    every = VolumeProcessDialog([("m", _map())])
    assert every.plane_operation.itemText(5) == "Curvature 2D"
    assert every.plane_operation.count() == len(every.PLANE_OPERATIONS)
    every.close()


# -- self-energy -----------------------------------------------------------------
V_BARE, K_F = 3.0, 0.5


def _series():
    import arpes_viewer.tools.spectra.dispersion as D
    import arpes_viewer.tools.spectra.peaks as PK
    energy = np.linspace(-0.30, -0.004, 100)
    imaginary = 0.008 + 0.015 * (1 + np.tanh((np.abs(energy) - 0.07) / 0.008))
    real = D.kramers_kronig(energy, imaginary)
    k = K_F + (energy - real) / V_BARE
    fwhm = 2 * imaginary / V_BARE
    column = lambda values: np.asarray(values, float)[:, None]
    return PK.BandSeries(
        positions=energy, names=["band 1"], centres=column(k),
        centre_errors=column(np.full(energy.size, 5e-4)), widths=column(fwhm),
        width_errors=column(np.full(energy.size, 1.5e-3)),
        heights=column(np.ones(energy.size)), areas=column(np.ones(energy.size)),
        chi2=np.ones(energy.size), direction="mdc", x_label="k (Å⁻¹)",
        y_label="E - E_F (eV)", settings=PK.FitSettings()), real, imaginary


def test_the_self_energy_window_states_its_bare_band(app, tmp_path):
    from arpes_viewer.ui.panels.fit import DispersionWindow, SelfEnergyWindow
    series, real, imaginary = _series()
    parent = DispersionWindow(series, "cut")
    window = parent.open_self_energy()
    assert isinstance(window, SelfEnergyWindow)
    # it opens on the usual statement: a line through E_F and the deepest point
    assert window.bare_kind() == "anchors"
    assert window.anchor_a.value() == 0.0
    assert window.anchor_b.value() == pytest.approx(-0.30)
    assert not window.anchor_a.isHidden() and window.velocity.isHidden()
    assert "straight line through the measured band" in window.note.text()
    by_anchors = window.result.consistency()

    # the velocity the two curves pick between themselves
    assert window.suggest_velocity() == pytest.approx(V_BARE, rel=0.02)
    assert window.bare_kind() == "velocity" and not window.velocity.isHidden()
    assert window.result.consistency() < 0.2 * by_anchors
    assert window.anchor_a.isHidden()
    np.testing.assert_allclose(window.result.real, real, atol=1e-3)
    np.testing.assert_allclose(window.result.imaginary, imaginary, rtol=0.03)
    note = window.note.text()
    assert "(consistent)" in note and "λ" in note and "mean free path" in note

    # typed by hand (from a calculation): the result follows
    window.velocity.setValue(2.0 * V_BARE)
    assert window.result.real.max() > 2 * real.max()
    window.velocity.setValue(V_BARE)

    # the dispersion window's own fit is still there to choose
    window.bare_choice.setCurrentIndex(window.BARE.index("dispersion"))
    assert window.result.bare is parent.fit
    window.bare_choice.setCurrentIndex(window.BARE.index("velocity"))

    # kept: as curves in the list, and as a table
    listed = []
    parent.datasetsCreated.connect(listed.extend)
    data = window.export()
    assert listed == [data] and data.kind == "edc"
    info = data.scan.info
    assert "Re Σ" in info["curve.channels"] and "σ Re Σ" in info["curve.channels"]
    assert data.scan.value.shape == (100, 5)
    assert np.all(np.diff(data.scan.x) > 0)
    assert info["proc.self_energy.bare_band"].startswith("a straight line of dE/dk")
    assert info["proc.self_energy.lambda"] == pytest.approx(
        window.result.coupling()[0])
    path = window.save_table(str(tmp_path / "sigma.csv"))
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    notes = [line for line in lines if line.startswith("#")]
    assert any("bare_band" in line for line in notes)
    header = lines[len(notes)]
    assert header.split(",")[:4] == ["energy", "k", "fwhm", "Re_Sigma"]
    table = np.loadtxt(path, delimiter=",", skiprows=len(notes) + 1)
    assert table.shape == (100, 8)
    window.close()
    parent.close()


def test_the_resolution_and_the_fermi_level_are_controls(app):
    from arpes_viewer.ui.panels.fit import SelfEnergyWindow
    series, _real, imaginary = _series()
    series.positions = series.positions + 16.5          # a kinetic-energy axis
    window = SelfEnergyWindow(series, "cut")
    assert not window.bare_choice.model().item(2).isEnabled()   # no fit given
    window.ef.setValue(16.5)
    window.anchor_a.setValue(16.5)
    window.anchor_b.setValue(16.2)
    window.suggest_velocity()
    assert window.velocity.value() == pytest.approx(V_BARE, rel=0.02)
    before = window.result.imaginary.copy()
    window.resolution.setValue(0.004)
    assert np.all(window.result.imaginary < before)
    window.close()
    short = _series()[0]
    short.centres[3:] = np.nan                          # three lines fitted
    with pytest.raises(ValueError, match="fewer than five"):
        SelfEnergyWindow(short, "cut")
