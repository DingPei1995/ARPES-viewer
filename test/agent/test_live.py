"""The documented operations ``L`` on a running program (route 3), the
command folder that runs them, and the generated reference they are read
from."""
import json
import os

import numpy as np
import pytest

pytest.importorskip("PyQt5")

SLIT = np.linspace(-10, 10, 41)
DEFL = np.linspace(-6, 6, 13)
EKIN = np.linspace(16.0, 16.6, 61)
EF = 16.45


def _edge(energy, ef=EF, kt=0.01):
    return 1.0 / (np.exp((energy - ef) / kt) + 1.0) + 0.02


_QT_APP = None


@pytest.fixture
def program(tmp_path, monkeypatch):
    """The program's main window, its list holding a cut, an angle map and a
    photon-energy scan."""
    from PyQt5.QtWidgets import QApplication
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path / "config"))
    import arpes_viewer.app as av
    from arpes_viewer.ui.launcher import main_window as main_window_ui
    from arpes_viewer.ui.viewers.widgets import MemoryData
    from arpes_viewer.tools.runtime import remembered
    monkeypatch.setattr(av, "loaded_items", {})
    monkeypatch.setattr(remembered, "recall", lambda *a, **k: None)
    win = av._MainWindow()
    ui = main_window_ui.Ui_MainWindow()
    ui.setupUi(win)
    monkeypatch.setattr(av, "win", win)
    monkeypatch.setattr(av, "ui", ui)
    monkeypatch.setattr(av, "autosave", lambda data, name: None)
    av.SetConnect()
    cut = np.tile(_edge(EKIN), (SLIT.size, 1)) * 100
    av.add_memory_dataset(MemoryData(
        "cut", (SLIT, EKIN), cut,
        {"x": "Angle, slit (deg)", "y": "Kinetic energy (eV)"},
        source_label="cut1"), "cut1")
    cube = np.tile(cut, (DEFL.size, 1, 1))
    av.add_memory_dataset(MemoryData(
        "map", (DEFL, SLIT, EKIN), cube,
        {"x": "Angle, deflector (deg)", "k": "Angle, slit (deg)",
         "z": "Kinetic energy (eV)"}, source_label="map1"), "map1")
    hv = np.linspace(40, 120, 21)
    energy = np.linspace(-0.5, 0.1, 13)
    rng = np.random.default_rng(1)
    av.add_memory_dataset(MemoryData(
        "kz_map", (hv, np.linspace(-12, 12, 25), energy),
        rng.random((hv.size, 25, energy.size)) + 1,
        {"x": "Photon energy (eV)", "k": "Angle (deg)", "z": "E - E_F (eV)"},
        source_label="hv1"), "hv1")
    yield av
    for window in list(QApplication.topLevelWidgets()):
        if window is not win and window.isVisible():
            window.close()
    win.deleteLater()


def test_the_operations_work_on_named_rows(program, tmp_path):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    names = {r["name"] for r in L.rows()}
    assert names == {"cut1", "map1", "hv1"}
    with pytest.raises(KeyError, match="no row"):
        L.describe("nothing")
    assert L.describe("cut1")["axes"][1]["points"] == EKIN.size

    fit = L.fermi_edge("cut1", energy_window=(16.3, 16.6), temperature=30)
    ef = fit["values"]["ef"]
    assert ef == pytest.approx(EF, abs=0.01)
    shifted = L.shift_energy("cut1", ef=ef)
    assert shifted in {r["name"] for r in L.rows()}
    assert "E - E_F" in L.describe(shifted)["axes"][1]["label"]
    k = L.cut_to_k(shifted, gamma_slit_deg=0.0)
    assert "k" in L.describe(k)["axes"][0]["label"].lower()

    data_shape = (SLIT.size, EKIN.size)
    cropped = L.crop(shifted, [(-5, 5), (None, None)])
    assert L.describe(cropped)["axes"][0]["max"] <= 5.0 + 1e-9
    history = L.metadata(cropped, "proc.step")
    assert any("truncate" in str(v) for v in history.values())
    normalised = L.normalise(shifted, axes=1)
    sums = np.nansum(L.data(normalised).values, axis=1)
    assert L.data(normalised).values.shape == data_shape
    assert np.allclose(sums, sums[0])                  # every line alike
    flat = L.background(shifted, method="percentile", axis=1)
    assert flat in {r["name"] for r in L.rows()}
    smoothed = L.smooth(shifted, [0.5, 0.01])
    second = L.derivative(shifted, axis=1, order=2)
    curved = L.curvature(shifted, mode="y", a0=1.0)
    valleys = L.minimum_gradient(shifted, floor=0.1)
    assert valleys.endswith("[grad]")
    assert L.data(valleys).values.shape == data_shape
    assert any("gradient" in str(v) and "form=ratio" in str(v)
               for v in L.metadata(valleys, "proc.step").values())
    of_a_map = L.minimum_gradient("map1", form="modulus")
    assert L.data(of_a_map).values.shape == (DEFL.size, SLIT.size, EKIN.size)
    binned = L.bin(shifted, [2, 1])
    assert L.describe(binned)["axes"][0]["points"] == SLIT.size // 2
    for row in (smoothed, second, curved):
        assert row in {r["name"] for r in L.rows()}

    kmap = L.map_to_k("map1")
    assert L.describe(kmap)["kind"] == "k_map"
    picture = L.picture("cut1", 0, 1, path=str(tmp_path / "cut.png"))
    assert os.path.exists(str(tmp_path / "cut.png")) and picture["shape"]

    # a computation of one's own, listed with its history
    data = L.data("cut1")
    assert data.values.shape == (SLIT.size, EKIN.size)
    mine = L.add("cut1 squared", "cut", data.axes, data.values ** 2,
                 labels=data.labels, made_from="cut1", step="square")
    assert mine in {r["name"] for r in L.rows()}

    saved = L.save([shifted, k], str(tmp_path / "out.nxs"))
    assert os.path.exists(str(tmp_path / "out.nxs")) and saved
    with pytest.raises(FileExistsError):
        L.save([shifted], str(tmp_path / "out.nxs"))

    assert L.rename(mine, "mine") == "mine"
    assert L.remove("mine") == ["mine"]


def test_the_crystal_and_figure_operations(program, tmp_path):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    kmap = L.map_to_k("map1")
    drawn = L.bz_overlay(kmap, space_group=221, a=3.0)
    assert "zone" in drawn["drawn"]
    stored = program.loaded_items[L._key(kmap)]
    assert json.loads(L._scan(kmap).info["bz.overlay"])["layers"]

    figure = L.slice_series(kmap, values=[16.45, 16.3], half_width=0.02,
                            cols=2, title="slices test")
    assert [p["title"] for p in figure["panels"]][:1] == ["16.45 eV"]
    assert "slices test" in L.figures()
    L.figure_style("slices test", font_pt=8.0, inner_tick_numbers=True)
    L.panel_set("slices test", 0, colormap="bluehot", gamma=0.6)
    described = L.figure_describe("slices test")
    assert described["panels"][0]["colormap"] == "bluehot"
    rendered = L.figure_render("slices test", str(tmp_path / "fig.png"), dpi=100)
    assert os.path.exists(rendered["png"])
    with pytest.raises(FileExistsError):
        L.figure_render("slices test", str(tmp_path / "fig.png"))

    picture = L.bz3d_picture(str(tmp_path / "bz.png"), space_group=221, a=3.0,
                             planes=[(0, 0, 1, 0.0)], paths=["G-X-M-G"],
                             frame="sample", surface_hkl=(0, 0, 1),
                             panel_mm=30, size=(600, 600))
    assert os.path.exists(picture["path"])
    assert picture["axes"] == ["k_x", "k_y", "k_z"]
    assert picture["label_px"] == pytest.approx(8 * 25.4 / 72 * 600 / 30)
    filled = L.panel_picture("slices test", 1, str(tmp_path / "bz.png"),
                             span=(1, 1))
    assert filled["panels"][1]["kind"] == "picture"
    L.figure_arrange("slices test", 1, 2)
    files = L.figure_export("slices test", str(tmp_path / "fig.pdf"))
    assert files and os.path.exists(files[0])
    zone = L.brillouin_zone(221, 3.0)
    assert zone
    plane = L.slice_series(kmap, values=[16.45], cols=1)
    sym = L.symmetrise(kmap, fold=4, centre=(0.0, 0.0))
    assert sym["row"] in {r["name"] for r in L.rows()} and sym["residual"] >= 0


def test_the_kz_operations(program):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    result = L.kz_to_k("hv1", space_group=221, a=3.0, gamma_hv=80.0)
    assert result["row"] in {r["name"] for r in L.rows()}
    assert result["gamma_zone_order"] >= 1
    kz = np.sqrt(0.262466 * (80.0 - 4.5 + result["inner_potential_eV"]))
    assert kz == pytest.approx(result["gamma_zone_order"]
                               * result["surface_period_invA"], rel=1e-4)
    with pytest.raises(ValueError, match="hv_calibration|kz_align_fermi"):
        L.kz_to_k("hv1", space_group=221, a=3.0, inner_potential=12.0,
                  calibrate_hv=True)


def test_tool_windows_open_by_action(program):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    actions = {t["action"] for t in L.tools()}
    assert {"mdcfit", "tbfit", "bands", "kzconv", "bz3d"} <= actions
    title = L.run_tool("edcfit", "cut1")
    assert title and title in L.windows()
    assert L.close(title) == title


def test_the_help_is_the_generated_reference(program, capsys):
    from arpes_viewer.ui.common.live import Live, operations
    L = Live(program)
    text = L.help()
    for _group, name, _method in operations():
        assert f"L.{name}(" in text
    assert "kz_to_k" in L.help("kz_to_k") and "gamma_hv" in L.help("kz_to_k")
    assert "L.slice_series" in L.help("Figures")
    assert "fit_fermi_edge" in L.functions("spectra.fermi")


def test_the_command_folder_runs_files_with_L(program, tmp_path):
    from arpes_viewer.ui.common.agentfolder import CommandFolder
    folder = CommandFolder(program, str(tmp_path / "agent")).start()
    try:
        command = tmp_path / "agent" / "viewer_cmd" / "c01.py"
        command.write_text("print(len(L.rows()), sorted(r['name'] for r in L.rows())[0])\n"
                           "d = QtWidgets.QDialog(); d.exec_()\n", encoding="utf-8")
        folder.poll()
        log = (tmp_path / "agent" / "out" / "cmd_c01.log").read_text(encoding="utf-8")
        assert log.startswith("3 cut1")
        assert "ModalDialogBlocked" in log
        assert (tmp_path / "agent" / "viewer_done" / "c01.py").exists()
        assert (tmp_path / "agent" / "heartbeat.txt").exists()
        assert program._agent_folder == str(tmp_path / "agent")
    finally:
        folder.stop()
    assert not (tmp_path / "agent" / "heartbeat.txt").exists()


def test_the_bridge_calls_the_operations(program):
    from arpes_viewer.ui.common import agentbridge
    bridge = agentbridge.start(program)
    try:
        ask = lambda op, **args: bridge.answer(json.dumps(
            {"token": bridge.token, "op": op, "args": args}))[0]
        reply = ask("api", operation="rows")
        assert reply["ok"] and len(reply["result"]) == 3
        fit = ask("api", operation="fermi_edge",
                  args={"name": "cut1", "energy_window": [16.3, 16.6]})
        assert fit["ok"] and fit["result"]["values"]["ef"] == pytest.approx(EF, abs=0.01)
        assert not ask("api", operation="nothing")["ok"]
        assert "L.kz_to_k" in ask("api_help")["result"]["reference"]
        out = ask("python", code="print(L.rows()[0]['name'])")
        assert out["result"]["output"].strip() == "cut1"
    finally:
        bridge.stop()


def test_a_kz_scan_is_aligned_then_converted_with_its_own_calibration(program):
    """kz_align_fermi records each photon energy's E_F; with the loader's
    member windows, the conversion's hv calibration is then on offer."""
    from arpes_viewer.ui.common.live import Live
    from arpes_viewer.ui.viewers.widgets import MemoryData
    L = Live(program)
    hv = np.linspace(40, 120, 9)
    energy = np.linspace(-0.4, 0.2, 61)
    shifts = 0.02 * np.sin(hv / 20.0)
    cube = np.stack([np.tile(100 * (1 / (np.exp((energy - s) / 0.01) + 1) + 0.02),
                             (15, 1)) for s in shifts])
    info = {"cassiopee.member_photon_energy_eV": hv,
            "cassiopee.member_work_function_eV": np.full(hv.size, 4.2),
            "cassiopee.member_kinetic_start_eV": hv - 4.6 - 0.4}
    program.add_memory_dataset(MemoryData(
        "kz_map", (hv, np.linspace(-7, 7, 15), energy), cube,
        {"x": "Photon energy (eV)", "k": "Angle (deg)", "z": "E - E_F (eV)"},
        source_label="hv2", source_info=info), "hv2")
    aligned = L.kz_align_fermi("hv2", angle_range=(0, 14), energy_range=(20, 60),
                               temperature=30)
    assert aligned["row"] and all(aligned["fitted"])
    assert np.allclose(aligned["fermi_levels_eV"], shifts, atol=0.005)
    result = L.kz_to_k(aligned["row"], space_group=221, a=3.0,
                       inner_potential=12.0, calibrate_hv=True)
    assert result["row"]
    assert L.metadata(result["row"], "hv_calibrated")


def test_the_assistant_starts_the_agent_from_two_folders(program, tmp_path, monkeypatch):
    """Two folders, a few options, one prompt: the command folder started in
    the results folder with API.md in it, the prompt on the clipboard with
    the folders, the rules and the options; then the steps watched, and a
    pause that stops the agent's commands."""
    from PyQt5.QtWidgets import QApplication
    from arpes_viewer.ui.common import assistant
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path / "config"))
    data = tmp_path / "beamtime"
    data.mkdir()
    results = tmp_path / "results"
    dialog = program.open_assistant()
    assert program.open_assistant() is dialog            # one window
    assert dialog.copy_and_start() is None               # no folders yet
    dialog.data_edit.setText(str(data))
    dialog.results_edit.setText(str(data))
    assert dialog.copy_and_start() is None               # results != data
    dialog.results_edit.setText(str(results))
    dialog.option_boxes["hide"].setChecked(True)
    dialog.option_boxes["report"].setChecked(True)
    dialog.extra_edit.setPlainText("Make Fig. 1 at E_F and -0.2 eV.")
    text = dialog.copy_and_start()
    try:
        assert QApplication.clipboard().text() == text
        commands = assistant.command_folder_of(str(results))
        assert os.path.join(commands, "viewer_cmd") in text
        assert str(data) in text and "read only" in text
        from arpes_viewer.agent.catalog import path as reference
        assert reference() in text                       # read in place
        assert not os.path.exists(os.path.join(commands, "API.md"))
        assert "sample A" in text and "report" in text
        assert "Make Fig. 1 at E_F" in text
        assert "usage_log" not in text                    # not ticked
        running = program._command_folder
        assert running.running and running.folder == os.path.abspath(commands)
        assert "Ready" in dialog.status.text()            # before the first step

        # a step, watched
        with open(os.path.join(commands, "viewer_cmd", "01_rows.py"), "w") as f:
            f.write("print(L.rows()[0]['name'])\n")
        running.poll()
        dialog.refresh_status()
        assert dialog.steps.count() == 1 and "01_rows.py" in dialog.steps.item(0).text()
        assert dialog.step_log.toPlainText().strip() == "cut1"

        # paused: the agent's next command waits
        dialog.toggle_pause()
        assert "Paused" in dialog.status.text() and not running.timer.isActive()
        dialog.toggle_pause()
        assert running.timer.isActive()
    finally:
        program._command_folder.stop()
        program._command_folder = None
    dialog.close()
    again = assistant.AssistantDialog(program)          # the choices are kept
    assert again.results_edit.text() == str(results)
    assert again.option_boxes["hide"].isChecked()
    again.close()


def test_the_assistant_for_an_mcp_app_turns_the_bridge_on(program, tmp_path, monkeypatch):
    from arpes_viewer.ui.common import assistant
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(program, "_agent_bridge", None, raising=False)
    dialog = assistant.AssistantDialog(program)
    dialog.mode_mcp.setChecked(True)
    bridge = program._agent_bridge
    try:
        assert bridge is not None                         # on when chosen
        data = tmp_path / "data"
        data.mkdir()
        dialog.data_edit.setText(str(data))
        dialog.results_edit.setText(str(tmp_path / "out"))
        text = dialog.copy_and_start()
        assert "claude mcp add arpes-viewer" in text and "viewer_api_help" in text
        assert '"mcpServers"' in text
        ask = lambda op, **args: bridge.answer(json.dumps(
            {"token": bridge.token, "op": op, "args": args}))[0]
        assert ask("api", operation="rows")["ok"]
        dialog.refresh_status()
        assert any("api" in dialog.steps.item(i).text() for i in range(dialog.steps.count()))
        dialog.toggle_pause()
        refused = ask("api", operation="rows")
        assert not refused["ok"] and "paused" in refused["error"]
        assert ask("status")["ok"]                         # looking is allowed
        dialog.toggle_pause()
        assert ask("api", operation="rows")["ok"]
    finally:
        bridge.stop()
        program._agent_bridge = None
        program._agent_paused = False
    dialog.close()

def test_add_files_takes_a_folder(program, tmp_path):
    from arpes_viewer.ui.common.live import Live
    from arpes_viewer.loader.native import save_dataset
    folder = tmp_path / "beamtime"
    (folder / "sub").mkdir(parents=True)
    cut = np.tile(_edge(EKIN), (SLIT.size, 1))
    for path, name in ((folder / "a.nxs", "cutA"), (folder / "sub" / "b.nxs", "cutB")):
        save_dataset(str(path), [{"name": name, "kind": "cut", "axes": (SLIT, EKIN),
                                  "value": cut, "labels": {"x": "Angle", "y": "E"},
                                  "info": {}}])
    (folder / "notes.txt").write_text("not data", encoding="utf-8")
    L = Live(program)
    added = L.add_files(str(folder))["added"]
    assert sorted(added) == ["cutA", "cutB"]


def test_the_status_light_follows_the_agent_with_the_window_closed(program, tmp_path, monkeypatch):
    """Grey not running, green running, yellow paused, red on a failed or
    stalled step -- on the main window's button, whether or not the AI
    assistant window is open; closing it does not stop the agent."""
    from arpes_viewer.ui.common import assistant
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(program, "_command_folder", None, raising=False)
    monkeypatch.setattr(program, "_agent_bridge", None, raising=False)
    monkeypatch.setattr(program, "_agent_paused", False, raising=False)
    light = program._status_light
    button = program.ui.AssistantButton
    assert light.update() == "idle" and assistant.LIGHTS["idle"][0] in button.styleSheet()

    data = tmp_path / "data"
    data.mkdir()
    dialog = assistant.AssistantDialog(program)
    dialog.data_edit.setText(str(data))
    dialog.results_edit.setText(str(tmp_path / "results"))
    dialog.copy_and_start()
    dialog.close()                                       # the agent goes on
    folder = program._command_folder
    try:
        assert folder.running
        commands = os.path.join(folder.folder, "viewer_cmd")
        with open(os.path.join(commands, "01.py"), "w") as handle:
            handle.write("print(L.rows()[0]['name'])\n")
        folder.poll()
        assert light.update() == "running"
        assert assistant.LIGHTS["running"][0] in button.styleSheet()
        assert "running" in button.toolTip().lower()

        program._agent_paused = True                     # paused by the person
        assert light.update() == "paused"
        program._agent_paused = False

        with open(os.path.join(commands, "02.py"), "w") as handle:
            handle.write("L.describe('no such row')\n")
        folder.poll()
        assert light.update() == "error"                 # a failed step
        assert assistant.LIGHTS["error"][0] in button.styleSheet()
        with open(os.path.join(commands, "03.py"), "w") as handle:
            handle.write("print('ok')\n")
        folder.poll()
        assert light.update() == "running"               # a good step clears it

        # a command left unrun: the commands stopped being run
        with open(os.path.join(commands, "04.py"), "w") as handle:
            handle.write("print('late')\n")
        stale = os.path.getmtime(os.path.join(commands, "04.py")) - 120
        os.utime(os.path.join(commands, "04.py"), (stale, stale))
        assert light.update() == "error"
        folder.poll()
        # quiet for long enough: not running
        state, _words = assistant.agent_state(program, now=folder.last_run + 3600)
        assert state == "idle"
        folder.timer.stop()                              # stopped unexpectedly
        assert light.update() == "error"
    finally:
        folder.stop()
        program._command_folder = None
    assert light.update() == "idle"


def test_the_agent_leaves_the_persons_selection_alone(program):
    """The person looks at map1 while the agent works on cut1."""
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    widget = program.ui.FilePathListWidget
    L.select("map1")                                     # the person's choice
    before = [widget.item(i).text() for i in range(widget.count())
              if widget.item(i).isSelected()]
    shifted = L.shift_energy("cut1", ef=16.45)           # lists a new row
    L.cut_to_k(shifted)
    title = L.run_tool("edcfit", "cut1")
    after = [widget.item(i).text() for i in range(widget.count())
             if widget.item(i).isSelected()]
    assert after == before and "map1" in after[0]
    assert "map1" in widget.currentItem().text()
    L.close(title)


def test_paths_are_written_the_systems_way(monkeypatch):
    """A folder from a Qt dialog (forward slashes) joined with file names
    must not give D:/Data\\_agent on Windows: the prompt, its JSON and the
    dialogs all use the system's separators."""
    import ntpath
    import os as _os
    from arpes_viewer.ui.common import assistant, paths
    monkeypatch.setattr(_os, "path", ntpath)            # as on Windows
    assert paths.native("D:/Data/LHhv/") == "D:\\Data\\LHhv"
    text = assistant.build_prompt("folders", "D:/Data/LHhv", "D:/Data/LHhv_out",
                                  options=["usage", "report", "slides"])
    assert "D:\\Data\\LHhv_out\\_agent\\viewer_cmd" in text
    assert "D:\\Data\\LHhv_out\\_agent\\out\\cmd_<name>.log" in text
    assert "D:\\Data\\LHhv_out\\usage_log.md" in text
    assert "D:\\Data\\LHhv_out\\slides\\summary.pptx" in text
    assert "D:/" not in text
    mcp = assistant.build_prompt("mcp", "D:/Data/LHhv", "D:/Data/out")
    assert '{"paths": "D:\\\\Data\\\\LHhv"}' in mcp     # valid JSON


def test_file_dialogs_return_native_paths(monkeypatch):
    from PyQt5.QtWidgets import QApplication, QFileDialog
    from arpes_viewer.ui.common import paths
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QFileDialog, "_native_paths", False, raising=False)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: "/tmp//data/../results/"))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: (["/tmp//a.nxs"], "*.nxs")))
    paths.install_native_dialogs()
    assert QFileDialog.getExistingDirectory() == paths.native("/tmp/results")
    assert QFileDialog.getOpenFileNames()[0] == [paths.native("/tmp/a.nxs")]
    paths.install_native_dialogs()                          # once only
    assert QFileDialog.getExistingDirectory() == paths.native("/tmp/results")


# ----------------------------------------------------------------------
# From a day of real data processed by an agent (CASSIOPEE, 2026-11-04)
# ----------------------------------------------------------------------
def test_rows_by_number_and_path_and_compact(program):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    rows = L.rows()
    assert L.describe(rows[1]["row"])["kind"] == "map"
    assert L.rename(0, "cut one") == "cut one"
    with pytest.raises(KeyError, match="row number"):
        L.describe(99)
    text = L.rows(compact=True)
    assert text.splitlines()[0].startswith("0 | cut one | ")


def test_profile_summary_and_file(program, tmp_path):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    short = L.profile("cut1", "energy", summary=True)
    assert "x" not in short and short["steepest_fall_at"] == pytest.approx(EF, abs=0.02)
    path = tmp_path / "edc.csv"
    full = L.profile("cut1", "energy", path=str(path), max_points=10)
    assert path.exists() and len(full["x"]) <= 11


def test_fermi_edge_picture_search_and_a_refusal_that_says_where(program, tmp_path):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    fit = L.fermi_edge("cut1", (16.3, 16.6), picture=str(tmp_path / "ef.png"))
    assert os.path.exists(fit["picture"])
    with pytest.raises(ValueError, match="energy axis runs 16.0000..16.6000"):
        L.fermi_edge("cut1", (16.0, 16.1), picture=str(tmp_path / "bad.png"))
    assert os.path.exists(str(tmp_path / "bad.png"))   # the refusal, drawn too
    found = L.fermi_edge_search("cut1")
    best = found["candidates"][0]
    assert best["highest"] and best["energy"] == pytest.approx(EF, abs=0.02)
    assert best["fit"]["ef"] == pytest.approx(EF, abs=0.01)


def test_edge_candidates_put_a_weak_last_edge_first():
    """Pass-energy-20 data: a strong drop under a weak tail; the Fermi edge
    is the tail's end, not the steeper drop."""
    from arpes_viewer.tools.spectra.fermi import edge_candidates, fermi_function
    rng = np.random.default_rng(0)
    e = np.linspace(110.0, 111.9, 400)
    y = rng.poisson(1000 * fermi_function(e, 111.45, 60)
                    + 60 * fermi_function(e, 111.80, 16) + 5).astype(float)
    found = edge_candidates(e, y)
    assert found[0]["energy"] == pytest.approx(111.80, abs=0.02)
    assert found[1]["energy"] == pytest.approx(111.45, abs=0.02)


def test_map_to_k_in_one_call_lists_only_the_k_map(program):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    before = len(L.rows())
    k = L.map_to_k("map1", ef=EF, normalise_axes=(1, 2))
    assert len(L.rows()) == before + 1 and k == "map1 [E-E_F] [norm] [k]"
    axes = L.describe(k)["axes"]
    assert axes[0]["points"] == 2 * DEFL.size          # twice the scan
    assert axes[2]["max"] < 0.2                        # on E - E_F
    history = " ".join(str(v) for v in L.metadata(k, "proc.step").values())
    assert "E - E_F" in history and "normalise" in history
    from arpes_viewer.agent.workspace import default_kx_points
    assert default_kx_points(61) == 100 and default_kx_points(150) == 150
    assert default_kx_points(20) == 40


def test_cut_arithmetic_makes_a_row(program):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    data = L.data("cut1")
    L.add("cut2", "cut", data.axes, data.values * 2.0, labels=data.labels)
    out = L.cut_arithmetic("cut1", "cut2", operation="asymmetry",
                           normalise="total")
    assert out["scale_b"] == pytest.approx(0.5)
    values = L.data(out["row"]).values
    assert np.nanmax(np.abs(values)) < 1e-9            # same after scaling


def test_slice_grid_and_a_saved_figure_keeps_its_title(program, tmp_path):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    k = L.map_to_k("map1", ef=EF)
    L.bz_overlay(k, space_group=221, a=3.0)
    k2 = L.map_to_k("map1", ef=EF, new_name="map2 [k]")
    figure = L.slice_grid([k, k2], [0.0, -0.1], column_titles=["LH", "LV"],
                          percentiles=(3, 99.7), high_factor=1.4,
                          zone_style="dashed", zone_color="#B8D62020",
                          title="grid")
    titles = [p["title"] for p in figure["panels"]]
    assert titles == ["LH, 0 eV", "LV, 0 eV", "LH, −0.1 eV", "LV, −0.1 eV"]
    L.figure_save("grid", str(tmp_path / "grid.afig"))
    assert "grid" in L.figures()                       # still found by title
    L.close("grid")


def test_windows_an_operation_opens_and_closes_never_show(program):
    """A window made and closed inside an agent's step is never mapped on
    a screen; one left open is shown at the end."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QWidget
    from arpes_viewer.ui.common.quietwindows import agent_windows
    with agent_windows():
        flash = QWidget()
        flash.setWindowTitle("flash")
        flash.show()
        assert flash.isVisible() and flash.testAttribute(Qt.WA_DontShowOnScreen)
        flash.close()
        stays = QWidget()
        stays.setWindowTitle("stays")
        stays.show()
        with agent_windows():                      # nested: still hidden
            pass
        assert stays.testAttribute(Qt.WA_DontShowOnScreen)
    assert stays.isVisible() and not stays.testAttribute(Qt.WA_DontShowOnScreen)
    stays.close()


def test_garbled_characters_in_an_agents_code_are_reported():
    from arpes_viewer.ui.common.agentbridge import mojibake_warning
    garbled = "−".encode("utf-8").decode("cp1252")
    assert "encoding" in mojibake_warning(f"title = '{garbled}0.2 eV'")
    assert mojibake_warning("title = '−0.2 eV'") == ""


def test_a_lone_spectrum_in_a_map_folder_is_reported_not_listed(program, tmp_path):
    from arpes_viewer.ui.common.live import Live
    from test.loaders.test_cassiopee import make_series, write_spectrum
    folder = tmp_path / "beamtime" / "Map150eV"
    folder.mkdir(parents=True)
    make_series(str(folder), base="Map150eV", count=3, thetas=[-1.0, 0.0, 1.0])
    write_spectrum(str(folder / "CSS0009.txt"), np.linspace(115.6, 116.0, 4),
                   np.linspace(-15, 15, 5), np.ones((5, 4)))
    (tmp_path / "beamtime" / "notes.docx").write_text("x", encoding="utf-8")
    L = Live(program)
    out = L.add_files(str(tmp_path / "beamtime"))
    assert len(out["added"]) == 1 and out["added"][0].startswith("Map150eV")
    assert [os.path.basename(p) for p in out["left_out"]] == ["CSS0009.txt"]
    assert out["unrecognised"] == ["notes.docx"]
    again = L.add_files(str(folder / "CSS0009.txt"))
    assert len(again["added"]) == 1


def test_naming_gives_the_ordered_tag_table(program):
    from arpes_viewer.ui.common.live import Live
    from arpes_viewer.tools.runtime.naming import TAGS
    rule = Live(program).naming()
    assert "[norm]" in rule and "[E-E_F]" in rule and "[k]" in rule
    assert rule.index("[norm]") < rule.index("[E-E_F]") < rule.index("[k]")
    assert len(TAGS) == rule.count("\n  [")


def test_the_steps_are_saved_as_one_script(program, tmp_path, monkeypatch):
    """Everything the agent ran -- command files and MCP requests -- as one
    Python file: the record of the processing, and a script that runs
    again. A failed step is kept as comments."""
    from arpes_viewer.ui.common import agentsteps, assistant
    from arpes_viewer.ui.common.live import Live
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(program, "_agent_bridge", None, raising=False)
    data = tmp_path / "beamtime"
    data.mkdir()
    results = tmp_path / "results"
    dialog = assistant.AssistantDialog(program)
    assert dialog.save_script(str(tmp_path / "none.py")) is None   # nothing yet
    assert not (tmp_path / "none.py").exists()
    dialog.data_edit.setText(str(data))
    dialog.results_edit.setText(str(results))
    text = dialog.copy_and_start()
    assert "session_script" in text and os.path.join(str(results), "agent_steps.py") in text
    folder = program._command_folder
    dialog.mode_mcp.setChecked(True)                     # and an MCP app too
    bridge = program._agent_bridge
    try:
        queue = os.path.join(folder.folder, "viewer_cmd")
        with open(os.path.join(queue, "01_smooth.py"), "w", encoding="utf-8") as f:
            f.write("made = L.smooth('cut1', [0.5, 0.01])\nprint('made', made)\n")
        folder.poll()
        with open(os.path.join(queue, "02_broken.py"), "w", encoding="utf-8") as f:
            f.write("L.smooth('no such row', [1, 1])\n")
        folder.poll()
        ask = lambda op, **args: bridge.answer(json.dumps(
            {"token": bridge.token, "op": op, "args": args}))[0]
        assert ask("api", operation="minimum_gradient",
                   args={"_args": ["cut1"], "floor": 0.1})["ok"]
        assert ask("python", code="print(len(L.rows()))")["ok"]
        assert ask("status")["ok"]                         # looking: not a step

        steps = agentsteps.steps(program)
        assert [s["name"] for s in steps] == [
            "01_smooth.py", "02_broken.py", "api minimum_gradient", "python"]
        assert [s["ok"] for s in steps] == [True, False, True, True]
        assert steps[2]["code"] == "print(L.minimum_gradient('cut1', floor=0.1))"

        saved = dialog.save_script(str(results / "steps.py"))
        assert saved["steps"] == 4 and saved["failed"] == 1
        assert "Saved" in dialog.message.text()
        with open(saved["path"], encoding="utf-8") as handle:
            script = handle.read()
        compile(script, saved["path"], "exec")             # it is Python
        assert "made = L.smooth('cut1', [0.5, 0.01])" in script
        assert "#     L.smooth('no such row', [1, 1])" in script   # commented
        assert "FAILED" in script and "#   made cut1 [sm]" in script
        assert script.index("01_smooth.py") < script.index("api minimum_gradient")

        # and it runs again, as a command file of its own
        rows = len(Live(program).rows())
        with open(os.path.join(queue, "03_again.py"), "w", encoding="utf-8") as f:
            f.write(script)
        folder.poll()
        with open(os.path.join(folder.folder, "out", "cmd_03_again.log"),
                  encoding="utf-8") as handle:
            log = handle.read()
        assert "Traceback" not in log, log
        assert len(Live(program).rows()) == rows + 2       # smooth, gradient

        # the agent can ask for it itself
        answer = Live(program).session_script(str(results / "by_agent.py"),
                                              with_output=False)
        assert answer["steps"] == 5 and os.path.exists(answer["path"])
        with open(answer["path"], encoding="utf-8") as handle:
            bare = handle.read()
        # (step 5 is the script itself, comments and all, so count them)
        full = agentsteps.script(program)
        assert bare.count("# It printed:") < full.count("# It printed:")
        compile(bare, answer["path"], "exec")
    finally:
        folder.stop()
        program._command_folder = None
        bridge.stop()
        program._agent_bridge = None
    dialog.close()


def test_bridge_requests_as_python():
    from arpes_viewer.ui.common.agentsteps import bridge_code
    assert bridge_code("add_files", {"paths": "D:/Data"}) == \
        "print(L.add_files('D:/Data'))"
    assert bridge_code("select", {"names": ["a", "b"]}) == "L.select('a', 'b')"
    assert bridge_code("run_tool", {"action": "mdcfit"}) == \
        "print(L.run_tool('mdcfit'))"
    assert bridge_code("render_figure", {"path": "f.png", "window": "Fig"}) == \
        "print(L.figure_render(path='f.png', title='Fig'))"
    assert bridge_code("api", {"operation": "rows"}) == "print(L.rows())"
    assert bridge_code("python", {"code": "x = 1\n"}) == "x = 1"
    assert bridge_code("something_else", {"a": 1}).startswith("#")


def test_a_fermi_pocket_through_the_operation(program, tmp_path):
    """L.fermi_pocket: the contour, its area and what it gives for a
    quasi-2D sample, with the notice in the answer; a picture to check it,
    and the contour as rows."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    import test_pocket as synthetic
    from arpes_viewer.ui.common.live import Live
    from arpes_viewer.ui.viewers.widgets import MemoryData
    program.add_memory_dataset(MemoryData(
        "k_map", (synthetic.KX, synthetic.KY, synthetic.ENERGY),
        synthetic.cube(0.01),
        {"x": "kx (Å⁻¹)", "k": "ky (Å⁻¹)", "z": "E - E_F (eV)"},
        source_label="FS [k-map]"), "FS [k-map]")
    L = Live(program)
    assert "QUASI-TWO-DIMENSIONAL" in L.help("fermi_pocket")
    assert "UNDER TEST" in L.help("fermi_pocket")
    rows = len(L.rows())
    found = L.fermi_pocket("FS [k-map]", (0.0, 0.0), 0.1, 0.6, energy=-0.05,
                           half_width=0.006, symmetry=6, cell=(3.3, 3.3, 120),
                           energies=[-0.02, -0.06, -0.1, -0.14, -0.18],
                           picture=str(tmp_path / "pocket.png"), to_list=True)
    assert found["area"] == pytest.approx(synthetic.area_of(-0.05), rel=0.01)
    assert found["centre"] == pytest.approx(list(synthetic.CENTRE), abs=0.008)
    assert found["rays_kept"] == found["rays"] == 72
    assert 0 < found["per_cell"] < 2 and found["frequency"] > 0
    assert found["carrier"] == "electron" and found["mass"] > 0
    assert len(found["series"]["areas"]) == 5
    assert "quasi-two-dimensional" in found["notice"]
    assert os.path.getsize(found["picture"]) > 10_000
    assert found["rows"] == ["FS [k-map] [pocket]", "FS [k-map] [pocket area]"]
    assert len(L.rows()) == rows + 2
    json.dumps(found)                                  # plain types only
    plain = L.fermi_pocket("FS [k-map]", synthetic.CENTRE, 0.1, 0.6,
                           energy=-0.05, recentre=False)
    assert "per_cell" not in plain and "mass" not in plain
    with pytest.raises(ValueError, match="k-map"):
        L.fermi_pocket("map1", (0, 0), 1, 5)
    with pytest.raises(ValueError, match="no contour"):
        L.fermi_pocket("FS [k-map]", (0.0, 0.0), 0.02, 0.08, energy=-0.05)
    assert "pocket" in {tool["action"] for tool in L.tools()}


def test_fs_correction_by_points_and_from_a_reference(program):
    from arpes_viewer.ui.common.live import Live
    L = Live(program)
    before = len(L.rows())
    out = L.fs_correction("cut1", points=[(-8, EF - 0.02), (0, EF), (8, EF - 0.02)])
    assert len(L.rows()) == before + 1 and "FS corr" in out["row"]
    assert out["points"] == 3 and out["coefficients"][0] < 0
    # only a row whose Fermi edge has been fitted is a reference
    with pytest.raises(ValueError, match="fitted"):
        L.fs_correction("map1", reference="cut1", mode="offset")
    L.fermi_edge("cut1", energy_window=(16.3, 16.6), temperature=30)
    with pytest.raises(ValueError, match="channel-by-channel"):
        L.fs_correction("map1", reference="cut1", mode="channels")
    out = L.fs_correction("map1", reference="cut1", mode="offset",
                          new_name="map1 on E-E_F")
    assert out["row"] == "map1 on E-E_F" and out["mode"] == "offset"
    axes = L.describe(out["row"])["axes"]
    assert axes[2]["min"] < 0 < axes[2]["max"]
    with pytest.raises(ValueError, match="either points"):
        L.fs_correction("cut1")
