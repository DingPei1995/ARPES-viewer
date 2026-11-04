# Requests to copy into the chat

Ready-made requests for an AI app driving ARPES viewer (see
[README.md](README.md)). Written for route 3 — the program open on your
screen, listening for the agent (**AI assistant...** → *Copy the prompt and
start*) — and
they work the same over MCP (route 1, `viewer_api`). Replace the folders,
names and numbers in `<...>` with your own: a request with the physical
parameters given gets a better result than a short one.

---

## 0. The first message

The **AI assistant** window writes it for you from two folders, a few
ticked options and your own words (*Copy the prompt and start*). In short:

> You are helping me analyse ARPES data with ARPES viewer, open on my
> screen. Write one Python file per step into `<command folder>/viewer_cmd`
> and wait for `<command folder>/out/cmd_<name>.log`. In those files `L` is
> the program. First read `<command folder>/API.md`: it lists every
> operation; use those, not the program's source. Today's data are in
> `<data folder>`.
> Rules: (1) everything stays on my computer; (2) ask me before choosing
> any physical parameter -- where Γ is, the temperature, an energy window,
> the inner potential; (3) never delete or overwrite; (4) check pictures and
> figures with `L.picture`, `L.figure_describe`, `L.figure_render`, not by
> reading my screen; (5) after each step give me the numbers and wait;
> (6) say so if you compute something yourself.

---

## 1. Looking around

> Add `<D:/data/beamtime>` to the list and give me a table of the rows:
> name, kind (cut, map, kz map ...), and for each its photon energy,
> temperature and polarisation from the metadata.

> Describe `<row>`: its axes, ranges and steps. Then write a picture of it,
> angle across and energy up, and the EDC at normal emission (slit angle
> between -1° and 1°).

---

## 2. Energy: the Fermi level

> Fit the Fermi edge of `<cut>` with the temperature held at `<30>` K, in
> an energy window of `<±0.15>` eV around the edge. Report E_F, the
> resolution, their errors and the reduced χ², and write a picture of the
> EDC with the window.

> The fit looks right: put the cut on E − E_F with that E_F.

> `<kz map>`: align the Fermi level of every photon energy. Use analyser
> channels `<40-600>` and energy channels `<100-400>`. Show me E_F against
> photon energy before going on.

---

## 3. Momentum

**A cut**

> Convert the E − E_F cut to momentum. Normal emission is at slit angle
> `<0.8>`°.

**A Fermi-surface map**

> Fit the Fermi edge of `<map>`, put it on E − E_F, then convert it to
> (kx, ky): Γ at deflector `<-1.5>`°, slit `<0.6>`°. Write the
> constant-energy pictures at E_F, −0.2 and −0.4 eV (each ±10 meV).

**A photon-energy scan**

> Convert `<kz map [E-Ef]>` to (k_z, k//): space group `<194>`,
> a = `<6.26>` Å, c = `<5.82>` Å, surface (0 0 1). Γ is at normal emission
> at hν = `<80>` eV. Tell me the V0 this gives and which high-symmetry
> points the measured plane holds.

---

## 4. Crystal and Brillouin zone

> List the high-symmetry points of space group `<194>`, a = `<6.26>` Å,
> c = `<5.82>` Å, in Å⁻¹.

> Draw the Brillouin zone on `<k-map>`: the same crystal, the (0 0 1)
> plane through Γ, turned by `<15>`°.

> Make a picture of the 3-D zone for a 30 mm panel with 8 pt labels: the
> (0 0 1) plane through Γ, the path Γ-M-K-Γ, the sample's axes.

---

## 5. A figure

> Make a slice series of `<k-map>` at E − E_F = 0, −0.1, −0.2, −0.3 eV
> (±10 meV), 2 columns, colour map `<bluehot>`, levels at the 2nd and
> 99.5th percentile, with the zone. Show me the figure in numbers (page,
> panel frames, text sizes) before anything else.

> Put the 3-D zone picture in the first panel, two grid cells tall; text
> 8 pt; tick numbers on every panel. Render it as a PNG and save it as
> PDF -- new file names.

---

## 6. Several datasets the same way

> Do the same as for `<first cut>` -- Fermi edge at `<30>` K, E − E_F,
> momentum with Γ at slit `<0.8>`° -- for every row whose name contains
> `<LH>`. Do the first two, show me the numbers and wait; then the rest,
> and give me a table of E_F per cut. Save all results in one `.nxs` file.

---

## 7. A script to keep (route 2, coding agents)

> Read `agentic/README.md`, `agentic/API.md` and the scripts in
> `agentic/examples/`. Write `<my_analysis.py>` that `<describe the
> steps>`, with every physical parameter as a named constant at the top.
> Ask me for their values. Run it on one dataset, show me the pictures,
> then on the rest.

---

## Checking what you got

> Which parameters did you use in each step, and where did each come from:
> from me, from the file's metadata, or chosen by you?

> Show me the history of `<row>` (its `proc.step` metadata).

> Did you compute anything yourself rather than with an operation?
