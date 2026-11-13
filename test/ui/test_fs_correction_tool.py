"""The Fermi-surface correction as a tool of the tool panel's Basic tab
(ui/viewers/windows.py FSCorrectionDialog, ARPES_viewer.open_fs_correction):
step by step -- by hand, clicking the Fermi edge on the data viewer, or
from a reference whose Fermi edge has been fitted (one offset, or channel
by channel) -- and the Fermi edge fit beside it: its two columns, the box
drawn on the data, and the channel-by-channel fit and offset that leave
the blank borders out."""
import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from arpes_viewer.tools.spectra.fermi import fermi_function, measured_channels
from arpes_viewer.ui.viewers import windows as W
from arpes_viewer.ui.viewers.widgets import MemoryData

SLIT = np.linspace(-10, 10, 41)
DEFL = np.linspace(-4, 4, 5)
EKIN = np.linspace(55.0, 56.0, 201)
BLANK = 3                   # blank channels on each side of a "detector" cut


def _edge(angle):
    """A Fermi edge bent by the analyser: 30 meV lower at the ends."""
    return 55.60 - 0.0003 * np.asarray(angle) ** 2


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_modal_boxes(monkeypatch):
    def fail(parent, title, text, *args, **kwargs):
        raise AssertionError(f"{title}: {text}")
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(fail))


def _frame(seed=1, blank=0):
    rng = np.random.default_rng(seed)
    frame = np.array([100 * fermi_function(EKIN, _edge(a), 20.0) + 5 for a in SLIT])
    frame += rng.normal(0, 0.3, frame.shape)
    if blank:
        frame[:blank] = 0.0
        frame[-blank:] = np.nan
    return frame


def _cut(name="c", seed=1, blank=0):
    return MemoryData("cut", (SLIT, EKIN), _frame(seed, blank),
                      {"x": "Angle (deg)", "y": "Kinetic energy (eV)"},
                      source_label=name)


def _map(name="m"):
    cube = np.stack([_frame(seed) for seed in range(DEFL.size)])
    return MemoryData("map", (DEFL, SLIT, EKIN), cube,
                      {"x": "Angle, deflector (deg)", "k": "Angle, slit (deg)",
                       "z": "Kinetic energy (eV)"}, source_label=name)


def _with_list(window, own, rows):
    """A standalone window given the main list's hooks: ``rows`` is
    {name: data}; ``own`` is the name of the window's own row."""
    window._row_key = own
    window._fermi_references = lambda: [
        (f"{name}   [{d.kind.capitalize()}]", name, W.fermi_fit_of(d.scan.info))
        for name, d in rows.items()
        if W.fermi_fit_of(d.scan.info)]
    return window


def _fitted_reference(app, blank=BLANK):
    """A gold cut with its Fermi edge fitted -- whole and channel by
    channel -- through the Fermi edge fit."""
    gold = _cut("gold", seed=3, blank=blank)
    window = W.CutWindow(gold, "gold", "gray", False)
    dialog = window.open_fermi_fit()
    dialog.energy_from.setValue(55.3)
    dialog.energy_to.setValue(55.9)
    assert dialog.run_fit() is not None
    assert dialog.fit_by_channel(confirm=False) is not None
    return gold, window, dialog


# -- the Fermi edge fit --------------------------------------------------------
def test_the_fit_panel_is_two_columns_with_a_fixed_plot(app):
    window = W.CutWindow(_cut(), "c", "gray", False)
    dialog = window.open_fermi_fit()
    left = dialog.table.parentWidget()
    right = dialog.plot.parentWidget()
    assert left is not right
    assert left.isAncestorOf(dialog.fit_button) and right.isAncestorOf(dialog.summary)
    assert not left.isAncestorOf(dialog.plot)
    # side by side: the parameters on the left, the fit on the right
    assert left.parentWidget() is right.parentWidget()
    assert left.geometry().x() < right.geometry().x() or not dialog.isVisible()
    box = dialog.plot.getPlotItem().getViewBox()
    assert box.state["mouseEnabled"] == [False, False]
    # channel by channel sits under Fit, its offset beside it; no fixed
    # defaults for it on the panel, and no drawing button
    assert dialog.channels_button.parentWidget() is left
    assert not dialog.offset_channels_button.isEnabled()
    assert not hasattr(dialog, "channel_width") and not hasattr(dialog, "draw_button")
    assert left.minimumWidth() >= 540
    dialog.close()
    window.close()


def test_channels_fitted_and_offset_without_the_blank_borders(app):
    gold, window, dialog = _fitted_reference(app)
    angles, ef, ok = dialog.channel_fit
    # the blank borders were cut off before fitting
    assert angles.min() == pytest.approx(SLIT[BLANK])
    assert angles.max() == pytest.approx(SLIT[-BLANK - 1])
    np.testing.assert_allclose(ef[ok], _edge(angles[ok]), atol=4e-3)
    fits = W.fermi_fit_of(gold.scan.info)        # kept with the dataset
    assert fits["edge"]["ef"] == pytest.approx(55.6, abs=0.02)
    assert len(fits["channels"]["angle"]) == int(ok.sum())
    made = []
    window.datasetCreated.connect(made.append)
    assert dialog.offset_channels_button.isEnabled()
    result = dialog.offset_channels()
    assert made == [result]
    assert result.scan.x[0] >= SLIT[BLANK] - 1e-9
    assert result.scan.x[-1] <= SLIT[-BLANK - 1] + 1e-9
    assert result.scan.labels["y"].startswith("E - E_F")
    assert W.FERMI_FIT_KEY not in result.scan.info
    energy = result.scan.y
    for column in result.scan.value[::5]:
        half = column.min() + 0.5 * (column.max() - column.min())
        assert abs(energy[np.argmin(np.abs(column - half))]) < 6e-3
    dialog.close()
    window.close()


WIDE = np.linspace(-15, 15, 400)


def _many_noisy_channels(noise=80.0):
    """400 channels, each too noisy for its own edge, the sum fine -- like
    a soft X-ray detector's single channels."""
    from arpes_viewer.tools.spectra.fermi import fermi_edge_model
    clean = np.array([fermi_edge_model(EKIN, float(_edge(a)), 20.0, 0.1, 100.0,
                                       0.0, 5.0, 0.0) for a in WIDE])
    return clean + np.random.default_rng(5).normal(0, noise, clean.shape)


def test_the_channel_fit_is_planned_from_the_data(app):
    from arpes_viewer.tools.spectra.fermi import fit_fermi_edge, plan_channel_fit
    frame = _frame(seed=4)
    seed = fit_fermi_edge(EKIN, frame.sum(0), window=(55.3, 55.9)).values
    plan = plan_channel_fit(SLIT, EKIN, frame, seed, window=(55.3, 55.9))
    assert plan["suitable"] and plan["needed"] <= 3 and plan["fits"] >= 10
    # far too many channels needed per fit, against those measured
    noisy = _many_noisy_channels()
    seed = fit_fermi_edge(EKIN, noisy.sum(0), window=(55.2, 56.0)).values
    plan = plan_channel_fit(WIDE, EKIN, noisy, seed, window=(55.2, 56.0))
    assert not plan["suitable"]
    assert plan["needed"] > plan["total"] // plan["min_fits"]


def test_noisy_data_are_declared_unsuited_to_a_channel_fit(app):
    noisy = MemoryData("cut", (WIDE, EKIN), _many_noisy_channels(),
                       {"x": "Angle (deg)", "y": "Kinetic energy (eV)"},
                       source_label="noisy")
    window = W.CutWindow(noisy, "noisy", "gray", False)
    dialog = window.open_fermi_fit()
    dialog.energy_from.setValue(55.2)
    dialog.energy_to.setValue(56.0)
    assert dialog.fit_by_channel(confirm=False) is None
    assert "not suited to a channel-by-channel fit" in dialog.summary.text()
    assert "channels" in dialog.summary.text()
    assert dialog.channel_fit is None and not dialog.offset_channels_button.isEnabled()
    dialog.close()
    window.close()


def test_a_box_too_small_for_a_line_shape_is_refused(app, monkeypatch):
    window = W.CutWindow(_cut(), "c", "gray", False)
    dialog = window.open_fermi_fit()
    shown = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: shown.append(a[2])))
    real = dialog.run_fit

    def sharp():
        fit = real()
        fit.errors["resolution"] = 3 * fit.values["resolution"]   # undetermined
        return fit
    dialog.run_fit = sharp
    assert dialog.fit_by_channel() is None
    assert shown and "Enlarge the box" in shown[0]
    dialog.close()
    window.close()


def test_the_proposal_window_shows_and_changes_the_plan(app):
    from arpes_viewer.tools.spectra.fermi import fit_fermi_edge
    window = W.CutWindow(_cut(), "c", "gray", False)
    dialog = window.open_fermi_fit()
    dialog.energy_from.setValue(55.3)
    dialog.energy_to.setValue(55.9)
    seed, plan, _ = dialog.plan_channels()
    proposal = W.ChannelFitPlanDialog(dialog, seed, plan)
    assert proposal.width_box.value() == 2 * plan["half_width"] + 1
    proposal.width_box.setValue(4)                 # made odd
    assert proposal.width_box.value() == 5 and proposal.step_box.value() >= 5
    assert proposal.settings()["half_width"] == 2
    assert "fits; E_F to about" in proposal.estimate.text()
    proposal.reject()
    dialog.close()
    window.close()


def test_a_cancelled_channel_fit_keeps_what_was_fitted():
    from arpes_viewer.tools.spectra.fermi import fit_channels
    calls = []
    ef, _err, ok = fit_channels(SLIT, EKIN, _frame(), window=(55.3, 55.9),
                                progress=lambda done, total: calls.append(done) or done < 5)
    assert len(calls) == 5 and np.isfinite(ef).sum() == 5


def test_measured_channels_trims_only_the_ends():
    frame = _frame(blank=2)
    frame[20] = 0.0                                  # a dead channel inside
    assert measured_channels(frame) == slice(2, SLIT.size - 2)


# -- the correction, by hand -------------------------------------------------------
def test_by_hand_step_by_step(app):
    window = W.CutWindow(_cut(), "c", "gray", False)
    made = []
    window.datasetCreated.connect(made.append)
    dialog = window.open_fs_correction()
    assert dialog.step() == dialog.STEP_METHOD
    assert dialog.manual_radio.isChecked()
    assert not dialog.reference_radio.isEnabled()    # nothing fitted listed
    dialog._on_pick(0.0, 55.6)              # not picking yet: ignored
    assert dialog.points() == []
    dialog.go_next()
    assert dialog.step() == dialog.STEP_POINTS
    assert "click the Fermi edge" in dialog.step_title.text()
    assert not dialog.next_button.isEnabled()
    for angle in (-9, -5, 0, 5, 9):
        dialog._on_pick(float(angle), float(_edge(angle)))
    assert len(dialog.points()) == 5 and dialog.next_button.isEnabled()
    dialog.go_next()
    assert dialog.step() == dialog.STEP_REVIEW
    assert dialog.correct_button.isVisibleTo(dialog)
    np.testing.assert_allclose(dialog.coefficients(), [-0.0003, 0, 55.6], atol=1e-3)
    dialog.correct_button.click()
    app.processEvents()
    assert len(made) == 1 and made[0].kind == "cut"
    window.close()


def test_going_back_erases_the_points_picked(app):
    window = W.CutWindow(_cut(), "c", "gray", False)
    dialog = window.open_fs_correction()
    dialog.go_next()
    for angle in (-6, 0, 6):
        dialog._on_pick(float(angle), float(_edge(angle)))
    assert window.view._pick_markers is not None
    dialog.go_back()
    assert dialog.step() == dialog.STEP_METHOD
    assert dialog.points() == []
    assert window.view._pick_markers is None          # gone from the picture
    assert window.view._overlay_curve is None or not window.view._overlay_curve.isVisible() \
        or len(window.view._overlay_curve.getData()[0] or []) == 0
    dialog.reject()
    window.close()


# -- the correction, from a reference --------------------------------------------
def test_the_reference_list_holds_only_other_fitted_rows(app):
    gold, gold_window, gold_dialog = _fitted_reference(app)
    data = _cut("c")
    unfitted = _cut("plain", seed=9)
    window = _with_list(W.CutWindow(data, "c", "gray", False), "c",
                        {"c": data, "gold": gold, "plain": unfitted})
    # this row fitted too: still not its own reference
    data.scan.info[W.FERMI_FIT_KEY] = gold.scan.info[W.FERMI_FIT_KEY]
    dialog = window.open_fs_correction()
    assert [key for _l, key, _f in dialog.references()] == ["gold"]
    dialog.reference_radio.setChecked(True)
    dialog.go_next()
    assert dialog.step() == dialog.STEP_REFERENCE
    assert "Step 2 of 2" in dialog.step_title.text()
    assert dialog.correct_button.isVisibleTo(dialog)
    assert not dialog.next_button.isVisibleTo(dialog)
    assert not hasattr(dialog, "refit_box")
    assert dialog.offset_radio.isEnabled() and dialog.channels_radio.isEnabled()
    assert "Whole edge" in dialog.reference_note.text()
    assert "Channel by channel" in dialog.reference_note.text()
    dialog.reject()
    window.close()
    gold_dialog.close()
    gold_window.close()


def test_one_offset_from_the_reference(app):
    gold, gold_window, gold_dialog = _fitted_reference(app)
    data = _cut("c")
    window = _with_list(W.CutWindow(data, "c", "gray", False), "c",
                        {"c": data, "gold": gold})
    made = []
    window.datasetCreated.connect(made.append)
    dialog = window.open_fs_correction()
    dialog.reference_radio.setChecked(True)
    dialog.go_next()
    dialog.offset_radio.setChecked(True)
    assert dialog.reference_choice()["mode"] == "offset"
    dialog.correct_button.click()
    app.processEvents()
    assert len(made) == 1
    ef = W.fermi_fit_of(gold.scan.info)["edge"]["ef"]
    np.testing.assert_allclose(made[0].scan.y, EKIN - ef)
    assert made[0].scan.x.size == SLIT.size            # nothing cropped
    window.close()
    gold_dialog.close()
    gold_window.close()


def test_channel_by_channel_from_the_reference_crops_its_borders(app):
    gold, gold_window, gold_dialog = _fitted_reference(app)
    data = _cut("c")
    window = _with_list(W.CutWindow(data, "c", "gray", False), "c",
                        {"c": data, "gold": gold})
    made = []
    window.datasetCreated.connect(made.append)
    dialog = window.open_fs_correction()
    dialog.reference_radio.setChecked(True)
    dialog.go_next()
    assert dialog.channels_radio.isChecked()           # preferred when fitted
    dialog.correct_button.click()
    app.processEvents()
    result = made[0]
    fitted = np.asarray(W.fermi_fit_of(gold.scan.info)["channels"]["angle"])
    assert result.scan.x[0] >= fitted.min() - 1e-9
    assert result.scan.x[-1] <= fitted.max() + 1e-9
    energy = result.scan.y
    for column in result.scan.value[::4]:
        half = column.min() + 0.5 * (column.max() - column.min())
        assert abs(energy[np.argmin(np.abs(column - half))]) < 8e-3
    window.close()
    gold_dialog.close()
    gold_window.close()


def test_a_map_is_corrected_whole_from_its_slit_cut(app):
    contour = W.ContourWindow(_map(), "m", "gray", False)
    cut = contour.open_cut("slit")
    made = []
    contour.datasetCreated.connect(made.append)
    dialog = cut.open_fs_correction(bound=True)
    dialog.go_next()
    for angle in (-9, -4, 0, 4, 9):
        dialog._on_pick(float(angle), float(_edge(angle)))
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
