"""Processed datasets are named with one bracketed tag per step, from one
ordered table (tools/runtime/naming.py), and "Sort by data type" groups the
list by the last tag in that order."""
import os

import pytest

from arpes_viewer.tools.runtime.naming import (TAGS, last_tag, tag_for, tagged,
                                               tags_in, type_sort_key)


def test_a_step_adds_its_tag_in_brackets():
    assert tagged("Map1", "normalise") == "Map1 [norm]"
    assert tagged("Map1 [norm]", "shift_energy") == "Map1 [norm] [E-E_F]"
    assert tagged("c", "EDC", "@ 0.1") == "c [EDC @ 0.1]"
    assert tag_for("k") == "k" and tag_for("truncate") == "crop"
    assert tag_for("something new") == "something new"


@pytest.mark.parametrize("name, tags", [
    ("Map80", []),
    ("Map [norm] [E-E_F] [k]", ["norm", "E-E_F", "k"]),
    ("FineMap_s_nor [k] [E-Ef]", ["norm", "k", "E-E_F"]),     # older names
    ("FineMap [E-Ef]_s_nor [k]", ["E-E_F", "norm", "k"]),
    ("x_sm_d2", ["sm", "d2"]),
    ("c [EDC @ 0.1 ±0.02] E=0", ["EDC"]),
    ("a [bin 2]", ["bin"]),
    ("a [core-level EDC]", ["EDC"]),
    ("m [slice Contour] E=0.1", ["slice"]),
])
def test_the_tags_of_a_name_are_read_old_and_new(name, tags):
    assert tags_in(name) == tags


def test_sorting_groups_by_the_last_step_in_processing_order():
    names = ["B [k]", "A [E-E_F]", "A", "C [norm]", "A [norm] [k]",
             "B [E-E_F]", "B", "D [whatever]"]
    ordered = sorted(names, key=type_sort_key)
    assert ordered == ["A", "B", "C [norm]", "A [E-E_F]", "B [E-E_F]",
                       "A [norm] [k]", "B [k]", "D [whatever]"]


def test_the_kind_comes_after_the_type():
    rows = [("m [norm]", "map"), ("c [norm]", "cut"), ("c2", "cut")]
    ordered = sorted(rows, key=lambda r: type_sort_key(*r))
    assert ordered == [("c2", "cut"), ("c [norm]", "cut"), ("m [norm]", "map")]


def test_the_tools_name_their_results_from_the_table():
    """No tool appends an underscore suffix any more: every suffix a
    processing panel gives is a bracketed tag of the table."""
    from arpes_viewer.ui.panels.process import ProcessDialog
    from arpes_viewer.ui.panels.volume import VolumeProcessDialog
    known = {tag for tag, _ in TAGS}
    for table in (ProcessDialog.SUFFIXES, VolumeProcessDialog.SUFFIXES):
        for suffix in table.values():
            assert suffix.startswith(" [") and suffix.endswith("]")
            assert last_tag("x" + suffix) in known


def test_the_list_sorts_by_processing_type(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import numpy as np
    from PyQt5.QtWidgets import QApplication
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    import arpes_viewer.app as program
    from arpes_viewer.ui.launcher import main_window as main_window_ui
    from arpes_viewer.ui.viewers.widgets import MemoryData
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(program, "loaded_items", {})
    win = program._MainWindow()
    ui = main_window_ui.Ui_MainWindow()
    ui.setupUi(win)
    monkeypatch.setattr(program, "win", win)
    monkeypatch.setattr(program, "ui", ui)
    monkeypatch.setattr(program, "autosave", lambda data, name: None)
    x = np.linspace(0, 1, 4)
    for name, kind in (("m [k]", "map"), ("c [E-E_F]", "cut"), ("m", "map"),
                       ("c", "cut"), ("m [E-E_F]", "map")):
        axes = (x, x) if kind == "cut" else (x, x, x)
        program.add_memory_dataset(
            MemoryData(kind, axes, np.ones([4] * len(axes)), {},
                       source_label=name), name)
    program.sort_list("kind")
    widget = ui.FilePathListWidget
    names = [program.loaded_items[widget.item(i).data(0x0100)]["name"]
             for i in range(widget.count())]
    assert names == ["c", "m", "c [E-E_F]", "m [E-E_F]", "m [k]"]
    win.deleteLater()


_QT_APP = None
