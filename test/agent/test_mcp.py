"""The MCP server, spoken to as a client would: JSON-RPC lines on the
stdin of ``python -m arpes_viewer.agent``, on a file written in this
program's own format. And the running program's bridge, over its socket."""
import base64
import json
import os
import subprocess
import sys
import threading

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SLIT = np.linspace(-10, 10, 41)
DEFL = np.linspace(-6, 6, 13)
EKIN = np.linspace(16.0, 16.6, 61)
EF = 16.45


def _edge(energy, ef=EF, kt=0.01):
    return 1.0 / (np.exp((energy - ef) / kt) + 1.0) + 0.02


@pytest.fixture(scope="module")
def data_file(tmp_path_factory):
    from arpes_viewer.loader.native import save_dataset
    path = str(tmp_path_factory.mktemp("agent") / "demo.nxs")
    cut = np.tile(_edge(EKIN), (SLIT.size, 1)) * 100
    cube = np.tile(cut, (DEFL.size, 1, 1))
    save_dataset(path, [
        {"name": "cut1", "kind": "cut", "axes": (SLIT, EKIN), "value": cut,
         "labels": {"x": "Angle, slit (deg)", "y": "Kinetic energy (eV)"},
         "info": {"photon_energy": 21.2}},
        {"name": "map1", "kind": "map", "axes": (DEFL, SLIT, EKIN), "value": cube,
         "labels": {"x": "Angle, deflector (deg)", "k": "Angle, slit (deg)",
                    "z": "Kinetic energy (eV)"}, "info": {}}])
    return path


class Client:
    """The server as a subprocess, spoken to line by line."""

    def __init__(self, env):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "arpes_viewer.agent"], cwd=ROOT, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)
        self.n = 0

    def send(self, method, params=None, notify=False):
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            self.n += 1
            message["id"] = self.n
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        if notify:
            return None
        return json.loads(self.proc.stdout.readline())

    def call(self, name, **arguments):
        reply = self.send("tools/call", {"name": name, "arguments": arguments})
        result = reply["result"]
        texts = [b["text"] for b in result["content"] if b["type"] == "text"]
        images = [b for b in result["content"] if b["type"] == "image"]
        return result["isError"], texts, images

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=30)


@pytest.fixture
def client(tmp_path):
    env = dict(os.environ, ARPES_VIEWER_CONFIG_DIR=str(tmp_path),
               QT_QPA_PLATFORM="offscreen", PYTHONPATH=ROOT)
    c = Client(env)
    yield c
    c.close()


def test_the_handshake_and_the_tool_list(client):
    reply = client.send("initialize", {"protocolVersion": "2025-06-18",
                                       "capabilities": {},
                                       "clientInfo": {"name": "t", "version": "0"}})
    assert reply["result"]["serverInfo"]["name"] == "arpes-viewer"
    assert reply["result"]["protocolVersion"] == "2025-06-18"
    assert "instructions" in reply["result"]
    assert client.send("notifications/initialized", notify=True) is None
    assert client.send("ping")["result"] == {}
    tools = {t["name"]: t for t in client.send("tools/list")["result"]["tools"]}
    for name in ("open_dataset", "get_image", "fit_fermi_edge", "convert_cut_to_k",
                 "convert_map_to_k", "save_datasets", "brillouin_zone",
                 "viewer_screenshot", "viewer_python", "viewer_run_tool"):
        assert name in tools
        assert tools[name]["inputSchema"]["type"] == "object"
    assert client.send("no/such")["error"]["code"] == -32601


def test_a_session_from_file_to_k_and_back_to_disk(client, data_file, tmp_path):
    client.send("initialize", {"protocolVersion": "2024-11-05"})
    error, texts, _ = client.call("find_files", folder=os.path.dirname(data_file))
    assert not error and "demo.nxs" in texts[0]
    error, texts, _ = client.call("open_dataset", path=data_file, entry="cut1")
    assert not error, texts
    cut = json.loads(texts[0])
    assert cut["id"] == "d1" and cut["kind"] == "cut"
    assert [a["slot"] for a in cut["axes"]] == ["x", "y"]

    error, texts, _ = client.call("get_profile", id="d1", along="energy",
                                  ranges={"slit": [-2, 2]})
    profile = json.loads(texts[0])
    assert profile["points"] == EKIN.size and profile["y"][0] > profile["y"][-1]

    error, texts, _ = client.call("fit_fermi_edge", id="d1",
                                  energy_window=[16.2, 16.6], temperature=116)
    fit = json.loads(texts[0])
    assert not error and fit["values"]["ef"] == pytest.approx(EF, abs=0.01)

    png = str(tmp_path / "cut.png")
    error, texts, images = client.call("get_image", id="d1", x="slit", y="energy",
                                       width=200, height=150, save_png=png)
    assert not error and images and images[0]["mimeType"] == "image/png"
    assert base64.b64decode(images[0]["data"])[:8] == b"\x89PNG\r\n\x1a\n"
    assert os.path.getsize(png) > 100

    error, texts, _ = client.call("convert_cut_to_k", id="d1", gamma_slit_deg=0.0,
                                  output_fermi_level_eV=EF)
    k = json.loads(texts[0])
    assert not error, texts
    assert k["kind"] == "cut" and "k" in k["axes"][0]["label"]
    assert k["axes"][1]["label"] == "E - E_F (eV)"
    assert k["axes"][1]["max"] == pytest.approx(EKIN.max() - EF, abs=1e-6)

    error, texts, _ = client.call("open_dataset", path=data_file, entry="map1")
    error, texts, _ = client.call("convert_map_to_k", id="d3", n_kx=30, n_ky=30)
    kmap = json.loads(texts[0])
    assert not error and kmap["kind"] == "k_map"

    out = str(tmp_path / "out.nxs")
    error, texts, _ = client.call("save_datasets", ids=[k["id"], kmap["id"]], path=out)
    assert not error and os.path.exists(out)
    from arpes_viewer.loader import registry
    assert {e["kind"] for e in registry.list_entries(out)} == {"Cut", "k-map"}
    error, texts, _ = client.call("save_datasets", ids=["d1"],
                                  path=str(tmp_path / "cut.itx"))
    assert not error and os.path.getsize(tmp_path / "cut.itx") > 100


def test_errors_come_back_as_text_a_model_can_read(client):
    error, texts, _ = client.call("describe", id="d99")
    assert error and "no dataset" in texts[0]
    error, texts, _ = client.call("viewer_status")
    assert error and "--agent-bridge" in texts[0]
    error, texts, _ = client.call("brillouin_zone", space_group=194, a=3.0, c=5.0)
    zone = json.loads(texts[0])
    assert not error and set(zone["points"]) >= {"Γ", "M", "K", "A"}
    assert zone["cell"]["gamma"] == 120.0 and zone["cell"]["b"] == 3.0


# -- the running program's side ---------------------------------------------------
_QT_APP = None

@pytest.fixture
def launcher(tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QApplication
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])   # kept alive
    monkeypatch.setenv("ARPES_VIEWER_CONFIG_DIR", str(tmp_path))
    import arpes_viewer.app as av
    from arpes_viewer.ui.launcher import main_window as main_window_ui
    monkeypatch.setattr(av, "loaded_items", {})
    win = av._MainWindow()
    ui = main_window_ui.Ui_MainWindow()
    ui.setupUi(win)
    monkeypatch.setattr(av, "win", win)
    monkeypatch.setattr(av, "ui", ui)
    monkeypatch.setattr(av, "autosave", lambda data, name: None)
    av.SetConnect()
    yield av
    win.deleteLater()


def test_the_bridge_answers_with_its_token_only(launcher, data_file):
    from arpes_viewer.agent import bridge as bridge_client
    from arpes_viewer.ui.common import agentbridge

    assert agentbridge.wanted(["x", "--agent-bridge"])
    bridge = agentbridge.start(launcher)
    assert bridge is not None
    try:
        reply, _ = bridge.answer(json.dumps({"token": "nope", "op": "status"}))
        assert not reply["ok"] and "token" in reply["error"]
        token = bridge.token
        ask = lambda op, **args: bridge.answer(json.dumps(
            {"token": token, "op": op, "args": args}))[0]
        assert ask("add_files", paths=[data_file])["result"]["rows"] == 2
        rows = ask("rows")["result"]
        assert {r["name"] for r in rows} >= {"cut1", "map1"}
        assert ask("select", names=["cut1"])["result"]["selected"] == ["cut1"]
        shot = ask("screenshot")["result"]
        assert base64.b64decode(shot["png"])[:4] == b"\x89PNG"
        assert ask("python", code="print(len(A.loaded_items))")["result"]["output"].strip() == "2"
        assert not ask("run_tool", action="nonsense")["ok"]

        # and over the socket, as the MCP server reaches it
        from PyQt5.QtWidgets import QApplication
        out = {}
        thread = threading.Thread(target=lambda: out.update(
            status=bridge_client.request("status", timeout=20)))
        thread.start()
        while thread.is_alive():
            QApplication.processEvents()
            thread.join(0.01)
        assert out["status"]["rows"] == 2
    finally:
        bridge.stop()
    assert not os.path.exists(bridge_client.config_path())


def test_a_modal_dialog_asked_for_by_an_agent_raises_instead_of_waiting(launcher, tmp_path):
    from PyQt5.QtWidgets import QDialog, QMessageBox
    from arpes_viewer.ui.common import agentbridge

    original = QDialog.__dict__["exec_"]
    notes = []
    with agentbridge.modal_guard(log=notes.append):
        with pytest.raises(agentbridge.ModalDialogBlocked, match="Slice series"):
            dialog = QDialog()
            dialog.setWindowTitle("Slice series figure")
            dialog.exec_()
        assert QMessageBox.warning(None, "Slice figure", "nothing") == QMessageBox.Ok
        with pytest.raises(agentbridge.ModalDialogBlocked):
            QMessageBox.question(None, "Shift?", "Shift the whole map?")
    assert notes == ["[warning] Slice figure: nothing"]
    assert QDialog.__dict__["exec_"] is original     # put back afterwards
    assert "warning" in QMessageBox.__dict__ and callable(QMessageBox.warning)

    bridge = agentbridge.start(launcher)
    try:
        ask = lambda op, **args: bridge.answer(json.dumps(
            {"token": bridge.token, "op": op, "args": args}))[0]
        out = ask("python", code="d = QtWidgets.QDialog(); d.setWindowTitle('X'); d.exec_()")
        assert "ModalDialogBlocked" in out["result"]["output"]
        assert not ask("figure")["ok"]                 # no figure window yet
        import numpy as np
        from arpes_viewer.tools.output import figure as nf
        from arpes_viewer.ui.panels.figure import FigureWindow
        panel = nf.Panel(data=nf.PanelData(array=np.ones((6, 5)),
                                           x=np.arange(6.0), y=np.arange(5.0)),
                         title="0 eV")
        window = FigureWindow([panel], "Test figure")
        window.show()
        described = ask("figure", window="Test figure")["result"]
        assert described["panels"][0]["title"] == "0 eV"
        assert len(described["panels"][0]["frame_mm"]) == 4
        rendered = ask("render_figure", path=str(tmp_path / "fig.png"), dpi=100)["result"]
        assert base64.b64decode(rendered["png_data"])[:4] == b"\x89PNG"
        assert os.path.exists(rendered["png"]) and rendered["dpi"] == 100
        window.close()
    finally:
        bridge.stop()
