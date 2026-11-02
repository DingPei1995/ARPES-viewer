# To do

Planned work that is not in the program yet. Nothing here is wired into the
code; each item waits for a decision before it is started.

## Plan B — renormalising a calculated Hamiltonian against the measurement

**Status:** proposed, on hold (to be decided).

### What it is for

The tight-binding fit (one band, or two hybridised bands) fits hoppings
freely. For a material with a band-structure calculation, the more useful
experimental constraint for theory is usually not a new set of hoppings
but **how the calculation has to be changed to match the data**: how much
each orbital's bands are narrowed (the renormalisation Z), how far each
orbital's on-site energy moves, and where the chemical potential sits. These
are the numbers DFT+U, DFT+DMFT and similar calculations are compared with,
and there are few of them, so the data can pin them down.

### The model

Start from the Wannier Hamiltonian the program already reads
(`_hr.dat` + `.win`, through Calculated bands, `tools/crystal/bandfiles.py`),
H_ij(k) in an orbital basis. Fit

    H'_ij(k) = sqrt(Z_i Z_j) H_ij(k) + delta_ij * d_i - mu

with orbitals grouped (say t2g / eg, or by atom), one Z and one d per group,
and one mu. The measured bands are eigenvalues of H'(k). Optional later
extensions: a separate Z for in-plane and out-of-plane hoppings, or a
spin-orbit coupling strength.

### Data it takes

* Band points (k, E) from ridge detection, MDC / EDC fits, or clicks, as
  the tight-binding fit takes them -- in-plane from k-maps, k_z from
  photon-energy scans (with the inner potential V0 recorded, since k_z
  depends on it).
* A cut in momentum, a k-map or a kz map in momentum.

### How it would be fitted

* Nonlinear least squares over (Z_g, d_g, mu), with analytic derivatives
  of the eigenvalues (Hellmann-Feynman: dE_n/dp = <n| dH'/dp |n>).
* **Which calculated band each point belongs to** is the hard part. Assign
  each point to the nearest eigenvalue at its k, re-assigned at every round,
  and let the orbital weights already shown in Calculated bands, together
  with the light polarisation, restrict which bands a point may go to.
  Points the user labels with a band index are kept on it.
* Starting values Z = 1, d = 0, mu = 0 (the calculation as it is), then the
  shift and the scale fitted for the whole set before the groups are
  separated.
* Robust reweighting of stray points, as in the tight-binding fit.
* Uncertainties from the Jacobian, and a warning when the points cannot
  tell two groups apart (the condition number, as now).

### Where it would go

A new step in **Calculated bands** ("Fit renormalisation"), after the
comparison step that already fits one Z and one energy shift to a cut.
Results: the parameters with errors, the renormalised bands drawn over the
data, the residual per band, and the parameters to a JSON file.

### Things to settle before starting

1. Which orbital groupings to offer, and whether the user defines them or
   they are read from the `.win` projections.
2. Whether Z should be allowed to depend on energy (a kink), or the fit
   restricted to an energy window below the kink.
3. How k_z uncertainty (V0, final-state broadening) enters: fitted, held,
   or propagated into the errors.
4. What the test data should be: a synthetic Hamiltonian with known
   (Z, d, mu), then one real material with a published comparison.

### Rough cost

Larger than the two-band fit: the band assignment, the k_z handling and the
interface in Calculated bands each take work. The eigenvalue fit itself
reuses the Hamiltonian evaluation that Calculated bands already has.
