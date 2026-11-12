"""The Fermi-surface correction as a tool of the tool panel's Basic tab
(ui/viewers/windows.py FSCorrectionDialog, ARPES_viewer.open_fs_correction):
step by step -- by hand, clicking the Fermi edge on the data viewer, or
from a reference cut or map of the main list, whose earlier fit is reused
-- and the dialog and its window closing together."""
import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from arpes_viewer.tools.spectra.fermi import fermi_function
from arpes_viewer.ui.viewers import windows as W
from arpes_viewer.ui.viewers.widgets import MemoryData

SLIT = np.linspace(-10, 10, 41)
DEFL = np.linspace(-4, 4, 5)
EKIN = np.linspace(55.0, 56.0, 201)


def _edge(angle):
    """A Fermi edge bent by the analyser: 30 meV lower at the ends."""
    return 55.60 - 0.0003 * angle ** 2


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_modal_boxes(monkeypatch):
    def fail(parent, title, text, *args, **kwargs):
        raise AssertionError(f"{title}: {text}")
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(fail))
    W._REFERENCE_FITS.clear()


def _frame(seed=1):
    rng = np.random.default_rng(seed)
    frame = np.array([100 * fermi_function(EKIN, _edge(a), 20.0) + 5 for a in SLIT])
    return frame + rng.normal(0, 0.3, frame.shape)


def _cut(name="c", seed=1):
    return MemoryData("cut", (SLIT, EKIN), _frame(seed),
                      {"x": "Angle (deg)", "y": "Kinetic energy (eV)"},
                      source_label=name)


def _map(name="m"):
    cube = np.stack([_frame(seed) for seed in range(DEFL.size)])
    return MemoryData("map", (DEFL, SLIT, EKIN), cube,
                      {"x": "Angle, deflector (deg)", "k": "Angle, slit (deg)",
                       "z": "Kinetic energy (eV)"}, source_label=name)


def _with_list(window, rows):
    """Give a standalone window the main list's hooks: ``rows`` is
    {label: data}."""
    window._dataset_entries = lambda: [(f"{label}   [{d.kind.capitalize()}]", label)
                                       for label, d in rows.items()]
    window._dataset_loader = lambda key: rows[key]
    return window


def test_by_hand_step_by_step(app):
    window = W.CutWindow(_cut(), "c", "gray", False)
    made = []
    window.datasetCreated.connect(made.append)
    dialog = window.open_fs_correction()
    assert dialog.step() == dialog.STEP_METHOD
    assert dialog.manual_radio.isChecked()
    assert not dialog.points_box.isVisibleTo(dialog)
    dialog._on_pick(0.0, 55.6)              # not picking yet: ignored
    assert dialog.points() == []
    dialog.go_next()
    assert dialog.step() == dialog.STEP_POINTS
    assert "click the Fermi edge" in dialog.step_title.text()
    assert "Fermi edge" in window.statusBar().currentMessage()
    assert not dialog.next_button.isEnabled()
    for angle in (-9, -5, 0, 5, 9):
        dialog._on_pick(float(angle), _edge(angle))
    assert len(dialog.points()) == 5 and dialog.next_button.isEnabled()
    dialog.go_next()
    assert dialog.step() == dialog.STEP_REVIEW
    assert dialog.correct_button.isVisibleTo(dialog)
    assert not dialog.next_button.isVisibleTo(dialog)
    np.testing.assert_allclose(dialog.coefficients(), [-0.0003, 0, 55.6], atol=1e-3)
    dialog.correct_button.click()
    app.processEvents()
    assert len(made) == 1 and made[0].kind == "cut"
    window.close()


def test_from_a_reference_and_reused_the_second_time(app, monkeypatch):
    reference = _map("gold")
    window = _with_list(W.CutWindow(_cut(), "c", "gray", False),
                        {"gold": reference, "other": window_data()})
    dialog = window.open_fs_correction()
    assert dialog.reference_combo.count() == 2
    dialog.reference_radio.setChecked(True)
    dialog.go_next()
    assert dialog.step() == dialog.STEP_REFERENCE
    assert "choose the reference" in dialog.step_title.text()
    assert dialog.reference_combo.currentText().startswith("gold")
    assert dialog.next_button.text().startswith("Fit the reference")
    assert not dialog.refit_box.isVisibleTo(dialog)
    dialog.width_box.setValue(0)
    dialog.step_box.setValue(4)
    dialog.go_next()
    assert dialog.step() == dialog.STEP_REVIEW
    points = np.array(dialog.points())
    assert len(points) >= 8
    np.testing.assert_allclose(points[:, 1], _edge(points[:, 0]), atol=4e-3)
    dialog.reject()

    # fitted once: a second correction uses that fit, without fitting
    def no_fit(*args, **kwargs):
        raise AssertionError("the reference was fitted again")
    monkeypatch.setattr(W, "run_channel_fit", no_fit)
    again = window.open_fs_correction()
    again.reference_radio.setChecked(True)
    again.go_next()
    assert "Already fitted" in again.reference_note.text()
    assert again.refit_box.isVisibleTo(again)
    assert again.next_button.text().startswith("Use the earlier fit")
    again.go_next()
    assert again.step() == again.STEP_REVIEW
    np.testing.assert_allclose(again.points(), points)
    again.reject()
    window.close()


def window_data():
    return _cut("other", seed=7)


def test_a_reference_fitted_by_the_fermi_edge_fit_is_reused(app, monkeypatch):
    reference = _cut("gold", seed=3)
    angles, energy, frame, _, _ = W.reference_frame(reference)
    fitted = (angles, _edge(angles), np.ones(angles.size, dtype=bool))
    monkeypatch.setattr(W, "run_channel_fit", lambda *a, **k: fitted)
    viewer = W.CutWindow(reference, "gold", "gray", False)
    viewer.fit_channels_here(temperature=20.0, fixed=("temperature",),
                             window=(None, None), half_width=0)
    viewer.close()
    assert W.recall_reference_fit(angles, energy, frame) is not None

    monkeypatch.setattr(W, "run_channel_fit",
                        lambda *a, **k: pytest.fail("fitted again"))
    window = _with_list(W.CutWindow(_cut(), "c", "gray", False),
                        {"gold": reference})
    dialog = window.open_fs_correction()
    dialog.reference_radio.setChecked(True)
    dialog.go_next()
    dialog.go_next()
    assert dialog.step() == dialog.STEP_REVIEW
    assert len(dialog.points()) == angles.size
    dialog.reject()
    window.close()


def test_a_map_is_corrected_whole_from_its_slit_cut(app):
    contour = W.ContourWindow(_map(), "m", "gray", False)
    cut = contour.open_cut("slit")
    made = []
    contour.datasetCreated.connect(made.append)
    dialog = cut.open_fs_correction(bound=True)
    dialog.go_next()
    for angle in (-9, -4, 0, 4, 9):
        dialog._on_pick(float(angle), _edge(angle))
    dialog.go_next()
    dialog.correct_button.click()
    app.processEvents()
    assert len(made) == 1 and made[0].kind == "map"
    assert made[0].scan.value.shape[:2] == (DEFL.size, SLIT.size)
    assert not cut.isVisible()                      # bound: closed with it
    contour.close()


def test_closing_the_window_closes_the_bound_dialog(app):
    window = W.CutWindow(_cut(), "c", "gray", False)
    window.show()
    dialog = window.open_fs_correction(bound=True)
    assert dialog.isVisible()
    window.close()
    app.processEvents()
    assert not dialog.isVisible()


def test_the_cut_viewer_no_longer_offers_it(app):
    window = W.CutWindow(_cut(), "c", "gray", False)
    window._rebuild_functions_menu()
    texts = [a.text() for a in window.functions_menu.actions()]
    assert not any("FS correction" in t for t in texts)
    window.close()
