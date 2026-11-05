"""Saving back over the file a row was read from: refused before ("the file
is open ... save under another name"), now written beside it, the viewers
on it closed, and the new file put in its place."""
import os

import h5py
import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from arpes_viewer.loader import native
from arpes_viewer.loader.scan import HANDLES
from arpes_viewer.ui.viewers.widgets import MemoryData


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def launcher(app, monkeypatch, tmp_path):
    import arpes_viewer.app as av
    from arpes_viewer.ui.launcher import main_window as main_window_ui
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(av, "loaded_items", {})
    monkeypatch.setattr(av, "info_window", None)
    monkeypatch.setattr(av, "current_data", None)
    monkeypatch.setattr(av, "current_key", None)
    win = av._MainWindow()
    ui = main_window_ui.Ui_MainWindow()
    ui.setupUi(win)
    monkeypatch.setattr(av, "win", win)
    monkeypatch.setattr(av, "ui", ui)
    monkeypatch.setattr(av, "autosave", lambda data, name: None)
    av.SetConnect()
    asked = []

    def answer(*args, **kwargs):
        asked.append(args[2] if len(args) > 2 else "")
        return av._answer
    monkeypatch.setattr(QMessageBox, "question", staticmethod(answer))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(
        lambda parent, title, text, *a, **k: pytest.fail(f"{title}: {text}")))
    av._answer = QMessageBox.Yes
    av._asked = asked
    yield av
    for widget in list(QApplication.topLevelWidgets()):
        if widget is not win and widget.isVisible():
            widget.close()
    win.deleteLater()


def _item(name, offset):
    x = np.linspace(-1, 1, 6)
    k = np.linspace(-2, 2, 7)
    e = np.linspace(0, 1, 8)
    return {"name": name, "kind": "map", "axes": (x, k, e),
            "labels": {"x": "Deflector (deg)", "k": "Slit (deg)",
                       "z": "Energy (eV)"},
            "value": np.full((6, 7, 8), float(offset)), "info": {}}


def _file(tmp_path, names=("A", "B")):
    path = str(tmp_path / "data.nxs")
    native.save_dataset(path, [_item(n, i + 1) for i, n in enumerate(names)])
    return path


def _select(launcher, *names):
    widget = launcher.ui.FilePathListWidget
    widget.clearSelection()
    for row in range(widget.count()):
        item = widget.item(row)
        key = item.data(0x0100)
        if launcher.loaded_items[key]["name"] in names:
            item.setSelected(True)


def _rows(launcher):
    return sorted(r["name"] for r in launcher.loaded_items.values())


def _entries(path):
    with h5py.File(path, "r") as f:
        return sorted(f.keys())


def test_a_row_saved_over_its_own_open_file(launcher, tmp_path):
    program = launcher
    path = _file(tmp_path)
    program.add_files([path], background=False)
    assert len(program.loaded_items) == 2
    _select(program, "A")
    viewer = program.open_selected()
    assert HANDLES.is_open(path)
    assert program.save_selected(path, "nxs") == path
    # asked once, telling what is closed and what is lost
    assert len(program._asked) == 1 and "B" in program._asked[0]
    assert not viewer.isVisible()
    assert _entries(path) == ["A"]
    assert _rows(program) == ["A"]
    key, = program.loaded_items
    data = program.load_dataset(key)
    assert np.asarray(data.scan.value).mean() == pytest.approx(1.0)
    data.close()
    assert not [n for n in os.listdir(tmp_path) if ".saving-" in n]


def test_a_computed_dataset_saved_over_the_open_file(launcher, tmp_path):
    program = launcher
    path = _file(tmp_path)
    program.add_files([path], background=False)
    _select(program, "A", "B")
    program.load_selected()                      # metadata on show: file open
    item = _item("A norm", 9)
    program.add_memory_dataset(MemoryData("map", item["axes"], item["value"],
                                     item["labels"], source_label="A norm"),
                          "A norm")
    _select(program, "A", "B", "A norm")
    program.save_selected(path, "nxs")
    assert _entries(path) == ["A", "A norm", "B"]
    assert _rows(program) == ["A", "A norm", "B"]
    assert program._asked == []                  # nothing closed, nothing lost


def test_saying_no_leaves_the_file_as_it_was(launcher, tmp_path):
    program = launcher
    path = _file(tmp_path)
    program.add_files([path], background=False)
    _select(program, "A")
    program.open_selected()
    program._answer = QMessageBox.No
    assert program.save_selected(path, "nxs") is None
    assert _entries(path) == ["A", "B"]
    assert _rows(program) == ["A", "B"]


def test_save_over_keeps_the_old_file_if_it_cannot_be_replaced(tmp_path):
    path = _file(tmp_path)
    HANDLES.acquire(path)
    try:
        def fail():
            raise RuntimeError("a viewer would not close")
        with pytest.raises(RuntimeError):
            native.save_over(path, [_item("C", 5)], release=fail)
    finally:
        HANDLES.close_file(path)
    assert _entries(path) == ["A", "B"]
    assert os.listdir(tmp_path) == ["data.nxs"]


def test_save_over_replaces_an_open_file(tmp_path):
    path = _file(tmp_path)
    HANDLES.acquire(path)
    released = []
    written = native.save_over(path, [_item("C", 5)],
                               release=lambda: released.append(True))
    assert written == ["C"] and released == [True]
    assert not HANDLES.is_open(path)
    assert _entries(path) == ["C"]
