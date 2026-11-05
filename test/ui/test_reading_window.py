"""A map in the list that has not been opened yet, worked on from a button
under the list (Self-normalise, Truncate, Compress ...): the window needs
only the axes, and reading the file shows a "Reading ..." progress window
instead of freezing the program with no word of what it is doing."""
import os

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from test.loaders.antares_maps import write_deflector_map
from test.loaders.test_cassiopee import make_series


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def launcher(app, monkeypatch, tmp_path):
    import arpes_viewer.app as av
    from arpes_viewer.ui.launcher import main_window as main_window_ui
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(av, "loaded_items", {})
    win = av._MainWindow()
    ui = main_window_ui.Ui_MainWindow()
    ui.setupUi(win)
    monkeypatch.setattr(av, "win", win)
    monkeypatch.setattr(av, "ui", ui)
    monkeypatch.setattr(av, "autosave", lambda data, name: None)
    av.SetConnect()
    reads = []
    real = av.nxs_jobs.run_blocking

    def counting(parent, title, work, cancellable=True):
        reads.append(title)
        return real(parent, title, work, cancellable=cancellable)
    monkeypatch.setattr(av.nxs_jobs, "run_blocking", counting)
    av._reads = reads
    yield av
    for widget in list(QApplication.topLevelWidgets()):
        if widget is not win and widget.isVisible():
            widget.close()
    win.deleteLater()


def _select_only_row(program):
    widget = program.ui.FilePathListWidget
    widget.clearSelection()
    widget.item(0).setSelected(True)


@pytest.mark.parametrize("operation", ["normalise", "truncate", "compress"])
def test_an_unopened_cassiopee_map_is_read_behind_a_progress_window(
        launcher, tmp_path, operation):
    program = launcher
    paths = make_series(str(tmp_path), count=4, thetas=[0.0, 1.0, 2.0, 3.0])
    program.add_files([paths[0]], background=False)
    _select_only_row(program)
    dialog = program.open_data_operations(operation)
    assert dialog is not None
    assert any(title.startswith("Reading ") for title in program._reads)


def test_an_unopened_hdf5_map_stays_on_disk_until_apply(launcher, tmp_path):
    from arpes_viewer.loader.scan import LazyCube
    program = launcher
    path = write_deflector_map(str(tmp_path / "m.nxs"), steps=24)
    program.add_files([path], background=False)
    _select_only_row(program)
    dialog = program.open_data_operations("normalise")
    assert dialog is not None
    (_name, data), = dialog.datasets
    assert isinstance(data.scan.value, LazyCube)    # only the axes were read


def test_a_dataset_already_open_is_not_read_again(launcher, tmp_path):
    program = launcher
    path = write_deflector_map(str(tmp_path / "m.nxs"), steps=24)
    program.add_files([path], background=False)
    _select_only_row(program)
    key = program.selected_keys()[0]
    first = program.load_dataset(key)
    program._reads.clear()
    program.open_data_operations("normalise")
    assert program._reads == []
    first.close()


def test_an_agent_step_reads_directly(launcher, tmp_path):
    """Inside an agent's command the read stays on the GUI thread: pumping
    events there would let the next command start inside this one."""
    from arpes_viewer.ui.common.agentbridge import modal_guard
    program = launcher
    paths = make_series(str(tmp_path), count=3, thetas=[0.0, 1.0, 2.0])
    program.add_files([paths[0]], background=False)
    _select_only_row(program)
    with modal_guard(log=lambda *_: None):
        data = program.load_dataset(program.selected_keys()[0])
    assert program._reads == []
    assert data.kind == "map"
