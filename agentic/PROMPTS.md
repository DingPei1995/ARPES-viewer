# Requests to copy into the chat

Ready-made requests for an agent connected to ARPES viewer (see
[README.md](README.md) to connect it). Replace the folder, file and the
numbers in `<...>` with your own. They work with any model; a clear request
with the physical parameters given gets a better result than a short one.

---

## 0. Start every session with the rules

> You are helping me analyse ARPES data with the ARPES viewer tools.
> Rules: (1) everything stays on my computer; (2) use the program's own
> tools, and tell me if you write any computation of your own; (3) before
> choosing any physical parameter -- where Γ is, the temperature, an energy
> window, a threshold -- ask me; (4) never delete or overwrite a file;
> (5) after each step, show me a picture and the numbers, and wait for me
> to say go on.

---

## 1. Looking around

> What datasets can the program open in `<D:/data/beamtime>`? Give me a
> table: file, dataset name, kind (cut, map, kz map...).

> Open `<dataset name>` and tell me its axes, ranges and steps, the photon
> energy, the temperature and the polarisation from its metadata.

> Show me a picture of it, angle across and energy up. Then show me the EDC
> at normal emission (slit angle between -1° and 1°).

---

## 2. Energy: the Fermi level

> Fit the Fermi edge of `<cut>`, with the temperature held at `<30>` K.
> Report E_F, the resolution, their errors and the reduced χ². Use an
> energy window of `<±0.15>` eV around the edge, and show me the EDC with
> the window marked.

> The fit looks right: make a copy of the cut on E − E_F using that E_F.

---

## 3. Momentum

**A cut**

> Convert the E − E_F cut to momentum. Normal emission (Γ) is at slit
> angle `<0.8>`°. Show me the result and save it as `<cut_k.nxs>` in
> `<D:/results>`.

**A Fermi-surface map**

> Open the map `<name>`. Fit the Fermi edge of the whole map. Then convert
> it to (kx, ky) with E − E_F as the energy axis: Γ is at deflector
> `<-1.5>`°, slit `<0.6>`°, sample rotation `<0>`°. Show me the contours at
> E_F, −0.2 and −0.4 eV (each ±10 meV) and save the k-map.

> Before you convert: show me the constant-energy contour at E_F in angles,
> so I can check where Γ is.

---

## 4. Crystal and Brillouin zone

> The crystal is space group `<194>`, a = `<6.26>` Å, c = `<5.82>` Å. List
> the high-symmetry points and their coordinates in Å⁻¹.

> Read the CIF file `<D:/data/sample.cif>` and tell me its space group,
> cell and atoms.

---

## 5. Several datasets the same way

> Do the same as for `<first cut>` -- Fermi edge at `<30>` K, E − E_F, momentum
> with Γ at slit `<0.8>`° -- for every cut in the folder whose name contains
> `<LH>`. Do the first two, show me the pictures and wait; then the rest,
> and give me a table of E_F per cut. Save all results in one `.nxs` file.

---

## 6. With the program open on screen

(Start the program with `arpes-viewer --agent-bridge` first.)

> Add the files of `<D:/data/beamtime>` to the program's list, select
> `<name>`, and open the k conversion (map) tool. Take a screenshot of the
> tool and show it to me; do not press anything yet.

> Take a screenshot of the main window and tell me what is in the list.

---

## 7. A script to keep (coding agents, route 2)

> Read `agentic/README.md` and the three scripts in `agentic/examples/`.
> Write `<my_analysis.py>` that `<describe the steps>`, with every physical
> parameter as a named constant at the top. Ask me for their values. Run it
> on one dataset, show me the pictures, then on the rest.

> Make a figure like example figure 1 of the README from my data: use
> `devtools/figure_tests.py` as the model. Show me the PNG after each
> change.

---

## Checking what you got

> Which parameters did you use in each step, and where did each come from:
> from me, from the file's metadata, or chosen by you?

> Show me the residual of the Fermi fit, and the fit window on the EDC.
