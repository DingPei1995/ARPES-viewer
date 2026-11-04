"""Live ARPES viewer that an agent can drive from files (no GUI control needed).

Start with launch_viewer.py. Reads agentic/config.json (copy config.example.json):
  data_dir  folder with the measurement files / scan folders
  patterns  glob patterns relative to data_dir (default matches CASSIOPEE .txt cuts
            and <scan folder>/*_roi1_.txt maps)
  screen    1-based monitor number for the window (default: 2)
Every *.py dropped into agentic/viewer_cmd/ is executed inside this running GUI process
(globals: L = the program's documented operations -- see arpes_viewer/agent/API.md or L.help() --,
A = arpes_viewer.app, HERE, DATA, QtCore, QtWidgets, np); its printed output goes to
agentic/out/cmd_<name>.log and the file is moved to agentic/viewer_done/. A modal dialog
opened by a command raises ModalDialogBlocked instead of freezing the poller.
(arpes_viewer.ui.common.agentfolder does the polling; the program's Help -> AI assistant
window starts the same thing without this script.)
Nothing here uses the network.
"""
import os, sys, glob, json, time, io, contextlib, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # the repository
for _folder in ("out", "viewer_cmd", "viewer_done", "shots", "figures"):
    os.makedirs(os.path.join(HERE, _folder), exist_ok=True)
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
DATA = os.path.normpath(os.path.expanduser(CFG["data_dir"])); PATTERNS = CFG.get("patterns", ["*.txt", "*/*_roi1_.txt"])
if not os.path.isdir(DATA):
    sys.exit(f"data_dir in {os.path.join(HERE, 'config.json')} is not a folder: {DATA!r}. "
             "Set it to your data folder.")
sys.path.insert(0, ROOT)
if sys.platform == "win32":
    os.environ["QT_QPA_PLATFORM"] = "windows"
import arpes_viewer.app as A
from arpes_viewer.ui.common.agentfolder import CommandFolder
from PyQt5 import QtCore, QtWidgets

paths = []
for pat in PATTERNS:
    paths += sorted(glob.glob(os.path.join(DATA, pat)))

def label_of(src):                                  # row name = file name, or folder name for scans
    return os.path.splitext(os.path.basename(src))[0] if os.path.dirname(src) == DATA \
        else os.path.basename(os.path.dirname(src))

def setup():
    try:
        w = A.win
        scr = QtWidgets.QApplication.screens()
        want = int(CFG.get("screen", 2)) - 1
        if len(scr) > 1 and 0 <= want < len(scr):
            g = scr[want].geometry(); w.move(g.x() + 40, g.y() + 40)
        A.add_files(paths, background=False)
        for key, rec in A.loaded_items.items():
            rec["name"] = label_of(rec["path"])
            item = A._row_for_key(key)
            if item is not None: item.setText(A._row_label(key))
        w.show(); w.raise_(); QtWidgets.QApplication.processEvents()
        time.sleep(0.5); QtWidgets.QApplication.processEvents()
        w.grab().save(os.path.join(HERE, "shots", "step01_main_panel_loaded.png"))
        print("listed", len(A.loaded_items), "datasets", flush=True)
    except Exception:
        traceback.print_exc(); sys.stdout.flush()

_orig = A.offer_recovery
def patched():
    QtCore.QTimer.singleShot(300, setup)
    # the program's own command folder (also started from Help -> AI assistant):
    # command files see A, L (the documented operations: L.help()), HERE, DATA
    A._command_folder = CommandFolder(A, HERE, DATA).start()
A.offer_recovery = patched
sys.exit(A.main())
