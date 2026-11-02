"""Example 3 -- a Fermi-surface map in momentum, and constant-energy pictures.

    python agentic/examples/03_fermi_surface.py [data folder] [output folder]

  1. open an angle map (deflector x slit x energy);
  2. fit the Fermi edge of the whole map;
  3. convert to (kx, ky) with the energy axis on E - E_F;
  4. save the Fermi surface and two deeper constant-energy contours.
"""
import os
import sys

from _common import folders
from arpes_viewer.agent.workspace import Workspace

# -- ask the user for these ----------------------------------------------
GAMMA_DEFLECTOR_DEG = 0.0   # deflector angle of Gamma
GAMMA_SLIT_DEG = 0.0        # slit angle of Gamma
AZIMUTH_DEG = 0.0           # in-plane rotation of the sample
ENERGIES_EV = (0.0, -0.2, -0.4)   # E - E_F of the pictures
HALF_WIDTH_EV = 0.01        # each picture integrates E +- this


def main(argv=sys.argv):
    data, out = folders(argv, "example_03")
    ws = Workspace()
    found = Workspace.find_files(data, "*", recursive=True)
    mapped = next(((f["path"], d["entry"]) for f in found for d in f["datasets"]
                   if d["kind"] == "Map"), None)
    if mapped is None:
        raise SystemExit("no angle map found")
    ident = ws.open(*mapped)["id"]

    ef = ws.fermi_edge(ident)["values"]["ef"]
    print(f"Fermi edge at {ef:.4f} eV (kinetic)")
    k_map = ws.convert_map(ident, gamma_deflector_deg=GAMMA_DEFLECTOR_DEG,
                           gamma_slit_deg=GAMMA_SLIT_DEG,
                           azimuth_deg=AZIMUTH_DEG, output_fermi_level_eV=ef)
    print("k-map:", k_map["name"], [a["label"] for a in k_map["axes"]])

    pictures = []
    for energy in ENERGIES_EV:
        path = os.path.join(out, f"contour_{energy:+.2f}eV.png")
        ws.image(k_map["id"], x="kx", y="ky", colormap="bluehot",
                 ranges={"energy": [energy - HALF_WIDTH_EV, energy + HALF_WIDTH_EV]},
                 width=560, height=560, path=path)
        pictures.append(path)
        print("Saved", path)
    ws.save([k_map["id"]], os.path.join(out, "k_map.nxs"))
    return {"ef": ef, "pictures": pictures, "k_map": k_map}


if __name__ == "__main__":
    main()
