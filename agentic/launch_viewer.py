# Starts viewer_live.py detached (survives this launcher). Run: python launch_viewer.py
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
for folder in ("out", "viewer_cmd", "viewer_done", "shots", "figures"):
    os.makedirs(os.path.join(HERE, folder), exist_ok=True)
if not os.path.exists(os.path.join(HERE, "config.json")):
    sys.exit("First copy config.example.json to config.json in " + HERE +
             " and set data_dir to your data folder.")
py = sys.executable.replace("pythonw.exe", "python.exe")
env = dict(os.environ, PYTHONIOENCODING="utf-8")
lf = open(os.path.join(HERE, "out", "viewer_live.log"), "w", encoding="utf-8")
if sys.platform == "win32":
    # detached, new process group, no console window
    options = dict(creationflags=0x00000008 | 0x00000200 | 0x08000000)
else:
    options = dict(start_new_session=True)
subprocess.Popen([py, os.path.join(HERE, "viewer_live.py")], stdout=lf,
                 stderr=subprocess.STDOUT, env=env, cwd=HERE, **options)
print("launched; its output goes to", os.path.join(HERE, "out", "viewer_live.log"))
