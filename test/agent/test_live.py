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
        assert str(data) in text and "API.md" in text and "read only" in text
        assert "sample A" in text and "report" in text
        assert "Make Fig. 1 at E_F" in text
        assert "usage_log" not in text                    # not ticked
        with open(os.path.join(commands, "API.md"), encoding="utf-8") as handle:
            assert "L.kz_to_k(" in handle.read()
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
