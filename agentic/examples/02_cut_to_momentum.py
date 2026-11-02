"""Example 2 -- a cut from raw data to momentum, on E - E_F.

    python agentic/examples/02_cut_to_momentum.py [data folder] [output folder]

The steps a person takes in the program, as a script:
  1. open a cut;
  2. fit the Fermi edge of its angle-integrated EDC;
  3. put the energy axis on E - E_F;
  4. convert the slit angle to momentum (k);
  5. save a picture and the result (.nxs, which the program opens).

The parameters an agent cannot know -- where Gamma is on the slit, the
sample temperature -- are at the top, as they should be in any script you
ask an agent for: it must ask you for them, not guess.
"""
import os
import sys

from _common import folders
from arpes_viewer.agent.workspace import Workspace

# -- ask the user for these ----------------------------------------------
GAMMA_SLIT_DEG = 0.0        # slit angle of normal emission / Gamma
TEMPERATURE_K = 30.0        # held in the Fermi-edge fit
CUT_NAME = None             # a dataset name; None takes the first cut


def main(argv=sys.argv):
    data, out = folders(argv, "example_02")
    ws = Workspace()
    found = Workspace.find_files(data, "*", recursive=True)
    cut = next(((f["path"], d["entry"]) for f in found for d in f["datasets"]
                if d["kind"] == "Cut" and CUT_NAME in (None, d["name"])), None)
    if cut is None:
        raise SystemExit("no cut found")
    ident = ws.open(*cut)["id"]

    edge = ws.fermi_edge(ident, temperature=TEMPERATURE_K)
    ef, error = edge["values"]["ef"], edge["errors"]["ef"]
    print(f"Fermi edge at {ef:.4f} ± {error:.4f} eV "
          f"(resolution {edge['values']['resolution'] * 1000:.1f} meV, "
          f"reduced chi2 {edge['reduced_chi2']:.2f})")
    if not edge["success"]:
        raise SystemExit("the Fermi-edge fit did not converge: " + edge["message"])

    shifted = ws.shift_energy(ident, ef)["id"]
    in_k = ws.convert_cut(shifted, gamma_slit_deg=GAMMA_SLIT_DEG)
    print("In momentum:", in_k["name"], [a["label"] for a in in_k["axes"]])

    _png, summary = ws.image(in_k["id"], x=0, y="energy",
                             path=os.path.join(out, "cut_in_k.png"))
    saved = ws.save([in_k["id"]], os.path.join(out, "cut_in_k.nxs"))
    print("Saved", summary["saved_png"], "and", saved.get("path", saved))
    return {"ef": ef, "png": summary["saved_png"], "k": in_k}


if __name__ == "__main__":
    main()
