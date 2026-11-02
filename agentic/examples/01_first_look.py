"""Example 1 -- a first look: what is in a data folder, and a picture of it.

    python agentic/examples/01_first_look.py [data folder] [output folder]

Lists every dataset the program can open in the folder, opens the first
cut, prints its axes and main metadata, and saves a picture and an EDC.
With no data folder, it uses the program's synthetic demo data.

What an AI agent learns from it: the program's headless "workspace" -- the
same functions the MCP server offers -- is a few lines of plain Python.
"""
import json
import os
import sys

from _common import folders
from arpes_viewer.agent.workspace import Workspace


def main(argv=sys.argv):
    data, out = folders(argv, "example_01")
    ws = Workspace()

    # 1. What is in the folder (nothing is read beyond the file headers).
    found = Workspace.find_files(data, "*", recursive=True)
    print(f"{len(found)} file(s) the program can open in {data}:")
    for item in found:
        kinds = ", ".join(f"{d['name']} [{d['kind']}]" for d in item["datasets"])
        print(f"  {os.path.basename(item['path'])}  ({item['loader']}): {kinds}")

    # 2. Open the first cut.
    cut = next(((f["path"], d["entry"]) for f in found for d in f["datasets"]
                if d["kind"] == "Cut"), None)
    if cut is None:
        print("No cut in this folder.")
        return None
    described = ws.open(*cut)
    print("\nOpened", described["name"], "as", described["id"])
    print(json.dumps(described["axes"], indent=1))

    # 3. A picture (angle across, energy up) and the EDC at normal emission.
    ident = described["id"]
    _png, summary = ws.image(ident, x=0, y="energy",
                             path=os.path.join(out, "cut.png"))
    edc = ws.profile(ident, along="energy", ranges={0: [-1.0, 1.0]},
                     path=os.path.join(out, "edc_normal_emission.csv"))
    print("\nSaved", summary["saved_png"], "and", edc["saved"])
    return {"dataset": described, "png": summary["saved_png"],
            "edc": edc["saved"]}


if __name__ == "__main__":
    main()
