"""Shared by the example scripts: find the program, and the data to use.

Not an example itself. It makes ``import arpes_viewer`` work from a
downloaded copy of the repository (a pip install needs nothing), and, when
no data folder is given, writes the program's synthetic demo data once so
that every example runs out of the box.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

try:
    import arpes_viewer  # noqa: F401  (installed with pip)
except ImportError:
    sys.path.insert(0, REPO)          # running from a copy of the repository


def folders(argv, default_out):
    """``(data folder, output folder)`` from the command line.

    ``python example.py [data folder] [output folder]``; with no data folder,
    the demo data (written on first use) in ``agentic/out/demo_data``.
    """
    out = os.path.abspath(argv[2] if len(argv) > 2 else
                          os.path.join(REPO, "agentic", "out", default_out))
    os.makedirs(out, exist_ok=True)
    if len(argv) > 1:
        return os.path.abspath(argv[1]), out
    demo = os.path.join(REPO, "agentic", "out", "demo_data")
    if not os.path.isdir(demo) or not os.listdir(demo):
        print("No data folder given: writing the synthetic demo data to", demo)
        sys.path.insert(0, REPO)
        from devtools import demo_data
        demo_data.write_all(demo)
    return demo, out
