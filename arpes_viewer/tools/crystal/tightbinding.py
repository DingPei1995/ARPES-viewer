"""
tools/crystal/tightbinding.py
=============================
A one-band tight-binding model fitted to measured band points.

    E(k) = e0 + sum_n t_n S_n(k),      S_n(k) = sum_{R in shell n} cos(k . R)

**One band.** The model describes a single band on a Bravais lattice: one
orbital per site, one band, no hybridisation with any other. Points traced
on two bands, or across an anticrossing, cannot be described by it; fit
each band on its own, and read the hoppings as that band's effective
parameters rather than microscopic orbital-to-orbital ones.

**Shells are symmetry orbits.** Shell ``n`` is one orbit of lattice vectors
under the crystal's point group (with inversion, since t(R) = t(-R)): all
vectors that symmetry makes equivalent, and only those. Two inequivalent
vectors that happen to have the same length (an in-plane and an
out-of-plane neighbour, say) get a hopping each. Without a space group the
lattice's own symmetry (its holohedry) is used, found from the metric.

How it is fitted:

* **A linear fit.** The model is linear in ``e0`` and every ``t_n``, so the
  least-squares answer is one linear solve, exact and immediate, with the
  standard errors from its covariance.
* **The Fermi-surface-only case made explicit.** Points that all sit at
  one energy (a Fermi-surface contour) fix the *shape* of the band but not
  its energy scale: multiply every ``t_n`` and ``e0 - E`` by the same
  number and the contour does not move (and the trivial ``t = 0`` fits a
  single energy perfectly). A single-energy fit therefore holds the first
  hopping at a value you choose (``t1``, by default -1 eV, i.e. answers "in
  units of t1") and fits the rest -- the honest statement of what such
  data determine. Points at two or more energies (a few constant-energy
  contours, or a dispersion) fit everything. Even then a single contour
  fixes only about two shells: the cosines of more distant shells can be
  traded for one another along one curve, which the fit detects (the
  condition number of the scaled problem) and says.
* **Shells from a proper search.** All lattice vectors within the needed
  radius, split into symmetry orbits, for any 2-D or 3-D lattice.
* **Robust to stray points.** Band points traced automatically include a
  few that lie on something else (a flat region near a saddle point, a
  second band). The fit reweights iteratively (Tukey's biweight on the
  residual's robust spread), so such points are found and given no say,
  and how many were set aside is reported.
* **The in-plane orientation can be fitted.** The sample azimuth (how the
  lattice is turned against the map's kx axis) is often known only to a
  degree or two; :func:`fit_azimuth` scans it and keeps the best.

Qt-free, so it can be tested on its own.
"""
from __future__ import annotations

import numpy as np

#: Above this (scaled) condition number the fitted hoppings are not
#: determined by the points, whatever their residual.
ILL_CONDITIONED = 300.0

__all__ = ["ILL_CONDITIONED", "shells", "design_matrix", "TBFit", "fit", "evaluate",
           "fit_azimuth", "rotate", "lattice_2d", "read_points",
           "lattice_symmetry", "integer_coordinates", "TwoBandFit",
           "fit_two_band", "two_band_energies", "LOWER", "UPPER", "AUTO"]


def lattice_2d(a: float, b: float, gamma_deg: float) -> np.ndarray:
    """2-D real-space primitive vectors (rows) from a, b and the angle."""
    g = np.deg2rad(gamma_deg)
    return np.array([[a, 0.0], [b * np.cos(g), b * np.sin(g)]])


def rotate(vectors: np.ndarray, azimuth_deg: float) -> np.ndarray:
    """``vectors`` (rows) turned by ``azimuth_deg`` about the z axis."""
    vectors = np.asarray(vectors, dtype=float)
    c, s = np.cos(np.deg2rad(azimuth_deg)), np.sin(np.deg2rad(azimuth_deg))
    out = vectors.copy()
    out[:, 0] = c * vectors[:, 0] - s * vectors[:, 1]
    out[:, 1] = s * vectors[:, 0] + c * vectors[:, 1]
    return out


def _check_lattice(vectors: np.ndarray) -> int:
    dim = vectors.shape[0]
    if vectors.shape != (dim, dim) or dim not in (2, 3):
        raise ValueError("give 2 vectors in 2-D or 3 in 3-D")
    if abs(np.linalg.det(vectors)) < 1e-12:
        raise ValueError("the lattice vectors are not independent")
    return dim


def lattice_symmetry(vectors, operations=None, max_index: int = 3,
                     tolerance: float = 1e-6) -> np.ndarray:
    """The point-group operations as integer matrices ``M`` on the lattice
    coordinates of ``vectors`` (rows): ``R = n @ vectors`` goes to
    ``n @ M @ vectors``. Inversion is always included (t(R) = t(-R)).

    ``operations``: Cartesian ``(N, d, d)`` rotations in the frame of
    ``vectors`` -- the space group's point group, say
    (:func:`tools.crystal.lattice.point_group_operations`). Each must map
    the lattice onto itself. None: the lattice's own holohedry, every
    integer ``M`` that keeps the metric ``G = vectors @ vectors.T``.

    Integer matrices do not depend on how the lattice is turned, so the
    same ones serve every azimuth :func:`fit_azimuth` tries.
    """
    vectors = np.asarray(vectors, dtype=float)
    dim = _check_lattice(vectors)
    inverse = np.linalg.inv(vectors)
    found = []
    if operations is not None:
        for op in np.asarray(operations, dtype=float):
            m = vectors @ op.T @ inverse
            rounded = np.rint(m)
            if not np.allclose(m, rounded, atol=1e-6):
                raise ValueError("a symmetry operation does not map the "
                                 "lattice onto itself (do the cell and the "
                                 "space group agree?)")
            found.append(rounded.astype(int))
    else:
        gram = vectors @ vectors.T
        scale = float(np.max(np.abs(gram)))
        idx = np.arange(-max_index, max_index + 1)
        grid = np.stack(np.meshgrid(*[idx] * dim, indexing="ij"),
                        -1).reshape(-1, dim)
        norms = np.einsum("ij,jk,ik->i", grid, gram, grid)
        rows = [grid[np.abs(norms - gram[i, i]) <= tolerance * scale]
                for i in range(dim)]

        def extend(chosen):
            i = len(chosen)
            if i == dim:
                found.append(np.array(chosen, dtype=int))
                return
            for row in rows[i]:
                if all(abs(float(row @ gram @ chosen[j]) - gram[i, j])
                       <= tolerance * scale for j in range(i)):
                    extend(chosen + [row])

        extend([])
        found = [m for m in found if abs(round(np.linalg.det(m))) == 1]
    identity = np.eye(dim, dtype=int)
    found += [-m for m in found] + [identity, -identity]
    unique = {}
    for m in found:
        unique.setdefault(m.tobytes(), m)
    return np.array(list(unique.values()))


def integer_coordinates(vectors, points) -> np.ndarray:
    """``points`` (rows, Cartesian) in units of the lattice ``vectors``."""
    return np.rint(np.asarray(points, float) @ np.linalg.inv(
        np.asarray(vectors, float))).astype(int)


def shells(vectors: np.ndarray, count: int, tolerance: float = 1e-6,
           symmetry=None):
    """The first ``count`` neighbour shells of the lattice spanned by
    ``vectors`` (rows, 2-D or 3-D): each one orbit of lattice vectors under
    ``symmetry`` (integer matrices from :func:`lattice_symmetry`; None for
    the lattice's holohedry).

    Returns ``[(distance, R array (m, d)), ...]``, nearest first; orbits at
    one distance are ordered by their first vector.
    """
    vectors = np.asarray(vectors, dtype=float)
    dim = _check_lattice(vectors)
    if symmetry is None:
        symmetry = lattice_symmetry(vectors)
    symmetry = np.asarray(symmetry, dtype=int)
    reach = 2
    while True:
        ranges = [np.arange(-reach, reach + 1)] * dim
        grid = np.stack(np.meshgrid(*ranges, indexing="ij"), -1).reshape(-1, dim)
        grid = grid[np.any(grid != 0, axis=1)]
        points = grid @ vectors
        lengths = np.linalg.norm(points, axis=1)
        order = np.lexsort((*[-grid[:, i] for i in range(dim - 1, -1, -1)],
                            np.round(lengths / max(tolerance, 1e-12))))
        grid, points, lengths = grid[order], points[order], lengths[order]
        found = []
        start = 0
        while start < len(lengths) and len(found) < count:
            stop = start
            while stop < len(lengths) and lengths[stop] - lengths[start] <= \
                    tolerance * max(1.0, lengths[start]):
                stop += 1
            # split the vectors at this distance into symmetry orbits
            left = [tuple(n) for n in grid[start:stop]]
            members = set(left)
            for n in left:
                if n not in members:
                    continue
                orbit = {tuple(int(v) for v in np.asarray(n) @ m) for m in symmetry}
                orbit &= members
                members -= orbit
                ordered = [tuple(g) for g in grid[start:stop] if tuple(g) in orbit]
                found.append((float(lengths[start]),
                              np.array(ordered, dtype=float) @ vectors))
                if len(found) == count:
                    break
            start = stop
        # The search box must hold every vector up to the last shell found:
        # its inscribed radius is reach times the shortest height.
        heights = abs(np.linalg.det(vectors)) / np.array(
            [np.linalg.norm(np.cross(*np.delete(vectors, i, axis=0)))
             if dim == 3 else np.linalg.norm(vectors[1 - i])
             for i in range(dim)])
        if len(found) == count and found[-1][0] < reach * heights.min() - 1e-9:
            return found
        reach += 1
        if reach > 12:
            return found


def design_matrix(k_points: np.ndarray, shell_list) -> np.ndarray:
    """Columns: 1, S_1(k), S_2(k), ... for each k point (rows)."""
    k_points = np.atleast_2d(np.asarray(k_points, dtype=float))
    columns = [np.ones(len(k_points))]
    for _distance, vectors in shell_list:
        columns.append(np.cos(k_points @ np.asarray(vectors).T).sum(axis=1))
    return np.column_stack(columns)


class TBFit:
    """A fitted model: ``e0`` and ``t`` (one per shell), their standard
    errors (NaN for one held fixed), the rms residual, and whether only the
    shape was determined (one energy, ``t1`` held)."""

    def __init__(self, vectors, shell_list, e0, t, e0_err, t_err, rms,
                 n_points, shape_only, azimuth_deg=0.0):
        self.vectors = np.asarray(vectors, dtype=float)
        self.shells = shell_list
        self.e0 = float(e0)
        self.t = np.asarray(t, dtype=float)
        self.e0_err = float(e0_err)
        self.t_err = np.asarray(t_err, dtype=float)
        self.rms = float(rms)
        self.n_points = int(n_points)
        self.shape_only = bool(shape_only)
        self.azimuth_deg = float(azimuth_deg)
        self.condition = 1.0
        self.warning = ""
        self.outliers = 0
        self.weights = None
        self.score = 0.0

    def energy(self, k_points) -> np.ndarray:
        """E(k) for ``k_points`` (rows)."""
        return design_matrix(k_points, self.shells) @ np.concatenate(
            [[self.e0], self.t])

    def bands(self, k_points) -> list:
        """Every band of the model at ``k_points``: here the one."""
        return [self.energy(k_points)]

    def table(self):
        """``[(name, value, error, unit), ...]`` for display."""
        rows = [("e0", self.e0, self.e0_err, "eV")]
        for i, ((distance, vectors), value, error) in enumerate(
                zip(self.shells, self.t, self.t_err), start=1):
            rows.append((f"t{i}  (|R| = {distance:.4g} Å, {len(vectors)} "
                         f"neighbours, {shell_label(self.vectors, vectors)})",
                         value, error, "eV"))
        return rows


def shell_label(vectors, shell_vectors) -> str:
    """One shell's vectors named by a representative, in lattice
    coordinates: ``<1 0 0>``."""
    first = integer_coordinates(vectors, np.atleast_2d(shell_vectors)[:1])[0]
    return "<" + " ".join(str(int(v)) for v in first) + ">"


def fit(k_points, energies, vectors, n_shells: int, *, weights=None,
        t1=None, energy_tolerance: float = 1e-6, robust: bool = True,
        symmetry=None) -> TBFit:
    """Least-squares tight-binding fit.

    ``k_points``: (N, d) in Å⁻¹; ``energies``: (N,) in eV; ``vectors``: the
    real-space primitive vectors (rows, Å). ``t1`` holds the first hopping
    fixed: needed when every point has the same energy (see the module
    note); if None it is held at -1 eV in that case and left free
    otherwise. ``symmetry``: integer matrices from :func:`lattice_symmetry`
    that split the shells (None: the lattice's holohedry).
    """
    k_points = np.atleast_2d(np.asarray(k_points, dtype=float))
    energies = np.asarray(energies, dtype=float).ravel()
    if len(k_points) != len(energies):
        raise ValueError("as many energies as k points are needed")
    shell_list = shells(vectors, n_shells, symmetry=symmetry)
    matrix = design_matrix(k_points, shell_list)
    single = float(np.ptp(energies)) <= energy_tolerance if energies.size else True
    hold = t1 if t1 is not None else (-1.0 if single else None)
    free = list(range(matrix.shape[1]))
    target = energies.copy()
    if hold is not None:
        target = target - hold * matrix[:, 1]
        free.remove(1)
    if len(energies) < len(free) + 1:
        raise ValueError(f"{len(free)} parameters need at least "
                         f"{len(free) + 1} points; there are {len(energies)}")
    base = np.ones_like(energies) if weights is None else np.asarray(weights, float)
    w = base.copy()
    for _round in range(30 if robust else 1):
        sw = np.sqrt(np.clip(w, 0, None))
        a = matrix[:, free] * sw[:, None]
        solution, *_ = np.linalg.lstsq(a, target * sw, rcond=None)
        residual = target - matrix[:, free] @ solution
        if not robust:
            break
        # Tukey's biweight on the residual in units of its robust spread:
        # a point more than ~4.7 sigma off the band (a ridge traced on
        # something else) gets no say, the rest keep nearly full weight.
        scale = 1.4826 * float(np.median(np.abs(residual - np.median(residual))))
        if scale <= 0:
            break
        u = residual / (4.685 * scale)
        new = base * np.where(np.abs(u) < 1, (1 - u ** 2) ** 2, 0.0)
        if np.allclose(new, w, atol=1e-4):
            break
        w = new
    outliers = int(np.sum(w <= 0)) if robust else 0
    dof = max(1, len(energies) - len(free))
    sigma2 = float(np.sum(w * residual ** 2) / dof)
    try:
        covariance = sigma2 * np.linalg.inv(a.T @ a)
        errors = np.sqrt(np.clip(np.diag(covariance), 0, None))
    except np.linalg.LinAlgError:
        errors = np.full(len(free), np.nan)
    params = np.zeros(matrix.shape[1])
    errs = np.full(matrix.shape[1], np.nan)
    params[free] = solution
    errs[free] = errors
    if hold is not None:
        params[1] = hold
    rms = float(np.sqrt(np.mean(residual ** 2))) if residual.size else 0.0
    if robust:
        kept = w > 0
        rms = float(np.sqrt(np.mean(residual[kept] ** 2))) if kept.any() else rms
    model = TBFit(vectors, shell_list, params[0], params[1:], errs[0], errs[1:],
                  rms, len(energies), single and t1 is None)
    model.outliers = outliers
    model.weights = w
    # What fit_azimuth ranks orientations by: the typical misfit over every
    # point, so an orientation cannot win by declaring points outliers.
    model.score = float(np.median(np.abs(residual))) if residual.size else 0.0
    # Columns scaled to unit length, so the condition number measures how
    # nearly the shells' cosines can stand in for one another on these
    # points -- not their sizes.
    scaled = a / np.maximum(np.linalg.norm(a, axis=0), 1e-300)
    model.condition = float(np.linalg.cond(scaled))
    if model.condition > ILL_CONDITIONED:
        model.warning = (
            f"The points do not pin down {n_shells} shells: on them, the "
            f"shells' cosines nearly stand in for one another (condition "
            f"number {model.condition:.3g}), so other hoppings describe the "
            f"same points about as well. Use fewer shells, or points at more "
            f"energies.")
    return model


def fit_azimuth(k_points, energies, vectors, n_shells: int, *, around=0.0,
                span=10.0, steps=81, fitter=None, **options) -> TBFit:
    """Fit with the lattice turned by every azimuth in ``around +- span``
    degrees (in-plane, about z) and keep the best; then refine to a tenth
    of the step. ``fitter`` is :func:`fit` (the default) or
    :func:`fit_two_band`."""
    fitter = fitter or fit

    def trial(angle):
        model = fitter(k_points, energies, rotate(vectors, angle), n_shells,
                       **options)
        model.azimuth_deg = angle
        return model

    angles = np.linspace(around - span, around + span, steps)
    models = [trial(a) for a in angles]
    best = int(np.argmin([m.score for m in models]))
    step = angles[1] - angles[0] if steps > 1 else 1.0
    fine = np.linspace(angles[best] - step, angles[best] + step, 21)
    models = [trial(a) for a in fine]
    return models[int(np.argmin([m.score for m in models]))]


# ==========================================================================
# Two bands, hybridised
# ==========================================================================
#: Which branch a band point is on: the lower or the upper of the two
#: eigenvalues, or AUTO (whichever the model puts nearer, decided again at
#: every round of the fit).
LOWER, UPPER, AUTO = -1, 1, 0


def two_band_energies(design, params, n_a: int, n_b: int, n_v: int):
    """``(lower, upper, eps_a, eps_b, v)`` at the k points of ``design``
    (columns 1, S_1, S_2, ...) for the parameters ``[e_a, t_a..., e_b,
    t_b..., v0, v...]``."""
    params = np.asarray(params, dtype=float)
    pa = params[:1 + n_a]
    pb = params[1 + n_a:2 + n_a + n_b]
    pv = params[2 + n_a + n_b:3 + n_a + n_b + n_v]
    eps_a = design[:, :1 + n_a] @ pa
    eps_b = design[:, :1 + n_b] @ pb
    v = design[:, :1 + n_v] @ pv
    mean, half = (eps_a + eps_b) / 2.0, (eps_a - eps_b) / 2.0
    root = np.sqrt(half ** 2 + v ** 2)
    return mean - root, mean + root, eps_a, eps_b, v


def _two_band_jacobian(design, params, n_a, n_b, n_v, sign):
    """d E_branch / d params, ``sign`` -1 (lower) or +1 (upper) per point."""
    _lo, _hi, eps_a, eps_b, v = two_band_energies(design, params, n_a, n_b, n_v)
    half = (eps_a - eps_b) / 2.0
    root = np.maximum(np.sqrt(half ** 2 + v ** 2), 1e-12)
    d_a = 0.5 + sign * half / (2.0 * root)
    d_b = 0.5 - sign * half / (2.0 * root)
    d_v = sign * v / root
    return np.column_stack([design[:, :1 + n_a] * d_a[:, None],
                            design[:, :1 + n_b] * d_b[:, None],
                            design[:, :1 + n_v] * d_v[:, None]])


class TwoBandFit:
    """Two bands on one lattice, hybridised: ``eps_a(k)`` and ``eps_b(k)``,
    each ``e + sum_n t_n S_n(k)`` over symmetry-orbit shells, coupled by
    ``V(k) = v0 + sum_n v_n S_n(k)``; the measured bands are the two
    eigenvalues

        E_+-(k) = (eps_a + eps_b)/2 +- sqrt(((eps_a - eps_b)/2)^2 + V^2).

    ``V`` carries the full symmetry of the lattice (a coupling between two
    orbitals of the same parity -- two d orbitals, bonding and antibonding
    combinations of a bilayer); an odd coupling (s with p) is not this
    form. Where the bare bands cross, the gap is ``2 |V|``.
    """

    def __init__(self, vectors, shells_a, shells_b, shells_v, params, errors,
                 rms, n_points, branch, azimuth_deg=0.0):
        self.vectors = np.asarray(vectors, dtype=float)
        self.shells_a, self.shells_b, self.shells_v = shells_a, shells_b, shells_v
        self.params = np.asarray(params, dtype=float)
        self.errors = np.asarray(errors, dtype=float)
        self.rms = float(rms)
        self.n_points = int(n_points)
        self.branch = np.asarray(branch, dtype=int)
        self.azimuth_deg = float(azimuth_deg)
        self.shape_only = False
        self.condition = 1.0
        self.warning = ""
        self.outliers = 0
        self.weights = None
        self.score = 0.0
        # one-band names, so code that reads a single-band fit still works
        self.shells = shells_a

    @property
    def sizes(self):
        return len(self.shells_a), len(self.shells_b), len(self.shells_v)

    def _design(self, k_points):
        # the three shell lists are prefixes of one; the longest serves all
        longest = max((self.shells_a, self.shells_b, self.shells_v), key=len)
        return design_matrix(k_points, longest)

    def solve(self, k_points):
        """``(lower, upper, eps_a, eps_b, v)`` at ``k_points`` (rows)."""
        return two_band_energies(self._design(k_points), self.params, *self.sizes)

    def bands(self, k_points) -> list:
        lower, upper, *_ = self.solve(k_points)
        return [lower, upper]

    def energy(self, k_points) -> np.ndarray:
        """The lower band (what a one-band caller asks for)."""
        return self.solve(k_points)[0]

    def bare(self, k_points):
        """The two bands before hybridisation, ``(eps_a, eps_b)``."""
        _lo, _hi, eps_a, eps_b, _v = self.solve(k_points)
        return eps_a, eps_b

    def gap(self, k_points):
        """The smallest direct gap ``E_+ - E_-`` over ``k_points`` and where
        it is: ``(gap, k)``."""
        lower, upper, *_ = self.solve(k_points)
        i = int(np.argmin(upper - lower))
        return float(upper[i] - lower[i]), np.atleast_2d(k_points)[i]

    def groups(self):
        """``[(prefix, shells, values, errors), ...]`` for band a, band b and
        the coupling."""
        n_a, n_b, n_v = self.sizes
        cut = (0, 1 + n_a, 2 + n_a + n_b, 3 + n_a + n_b + n_v)
        names = (("a", self.shells_a), ("b", self.shells_b), ("v", self.shells_v))
        return [(prefix, shells, self.params[cut[i]:cut[i + 1]],
                 self.errors[cut[i]:cut[i + 1]])
                for i, (prefix, shells) in enumerate(names)]

    def table(self):
        rows = []
        for prefix, shells, values, errors in self.groups():
            head = "v0 (on-site coupling)" if prefix == "v" else f"e_{prefix}"
            rows.append((head, values[0], errors[0], "eV"))
            for i, ((distance, vectors), value, error) in enumerate(
                    zip(shells, values[1:], errors[1:]), start=1):
                name = f"v{i}" if prefix == "v" else f"t{i}_{prefix}"
                rows.append((f"{name}  (|R| = {distance:.4g} Å, {len(vectors)} "
                             f"neighbours, {shell_label(self.vectors, vectors)})",
                             value, error, "eV"))
        return rows


def fit_two_band(k_points, energies, vectors, n_shells: int, *,
                 n_shells_b: int = None, n_hybrid: int = 0, branch=None,
                 symmetry=None, robust: bool = True, rounds: int = 25,
                 starts: int = 24, seed: int = 0,
                 energy_tolerance: float = 1e-6) -> TwoBandFit:
    """Fit two hybridised bands (:class:`TwoBandFit`) to band points.

    ``n_shells`` / ``n_shells_b``: hoppings of band a / band b (b defaults
    to a's); ``n_hybrid``: shells in the coupling beyond the constant v0.
    ``branch``: per point :data:`LOWER`, :data:`UPPER` or :data:`AUTO`
    (None: all AUTO). An AUTO point is put on whichever branch the current
    model puts nearer, again at every round, so labelling a few points
    (one contour, say) is enough to tell the fit which is which.

    The fit is nonlinear. ``starts`` random starting models (seeded by
    ``seed``, so a fit is repeatable) and two from one-band fits are first
    fitted with each point scored against the nearer band; the best three
    are refined with the points assigned and the stray ones reweighted, and
    the one with the smallest mean misfit over every point is kept.
    Points at a single energy cannot fix the energy scale and are refused.
    """
    from scipy.optimize import least_squares

    k_points = np.atleast_2d(np.asarray(k_points, dtype=float))
    energies = np.asarray(energies, dtype=float).ravel()
    if len(k_points) != len(energies):
        raise ValueError("as many energies as k points are needed")
    if energies.size and float(np.ptp(energies)) <= energy_tolerance:
        raise ValueError("two bands need points at two or more energies: "
                         "one contour fixes no energy scale")
    n_a = int(n_shells)
    n_b = int(n_shells if n_shells_b is None else n_shells_b)
    n_v = int(n_hybrid)
    widest = max(n_a, n_b, n_v, 1)
    shell_list = shells(vectors, widest, symmetry=symmetry)
    design = design_matrix(k_points, shell_list)
    n_params = 3 + n_a + n_b + n_v
    if len(energies) < n_params + 1:
        raise ValueError(f"{n_params} parameters need at least {n_params + 1} "
                         f"points; there are {len(energies)}")
    branch = (np.zeros(len(energies), dtype=int) if branch is None
              else np.asarray(branch, dtype=int).ravel())
    fixed = branch != AUTO

    # -- starting points ---------------------------------------------------
    # Which band a point is on is not known in advance, so the start is
    # searched for: from many starting models, each point is scored against
    # the nearer band (a labelled point against its own), with a loss that
    # forgives the odd stray point, and the best few are refined below.
    def one_band(mask, n):
        a = design[mask][:, :1 + n]
        if mask.sum() < a.shape[1] + 1:
            return np.linalg.lstsq(design[:, :1 + n], energies, rcond=None)[0]
        return np.linalg.lstsq(a, energies[mask], rcond=None)[0]

    common = np.linalg.lstsq(design[:, :1 + max(n_a, n_b)], energies, rcond=None)[0]
    misfit = energies - design[:, :1 + max(n_a, n_b)] @ common
    split = np.where(fixed, branch, np.where(misfit >= 0, UPPER, LOWER))
    spread = float(np.std(energies)) or 0.1
    lo_e, hi_e = float(energies.min()), float(energies.max())
    pa, pb = one_band(split == LOWER, n_a), one_band(split == UPPER, n_b)
    candidates = [np.concatenate([pa, pb, [v0 * spread], np.zeros(n_v)])
                  for v0 in (0.05, 0.3)]
    rng = np.random.default_rng(seed)
    for _ in range(int(starts)):
        candidates.append(np.concatenate([
            [rng.uniform(lo_e - spread, hi_e + spread)], rng.normal(0, spread, n_a),
            [rng.uniform(lo_e - spread, hi_e + spread)], rng.normal(0, spread, n_b),
            [rng.uniform(0, spread)], rng.normal(0, 0.2 * spread, n_v)]))
    noise = max(1e-4, 0.05 * spread)

    def nearest_misfit(params):
        lower, upper, *_ = two_band_energies(design, params, n_a, n_b, n_v)
        near = np.minimum(np.abs(energies - lower), np.abs(energies - upper))
        own = np.abs(energies - np.where(branch == UPPER, upper, lower))
        return np.where(fixed, own, near)

    searched = []
    for start in candidates:
        try:
            found = least_squares(nearest_misfit, start, loss="soft_l1",
                                  f_scale=noise, max_nfev=300).x
        except ValueError:
            continue
        searched.append((float(np.mean(nearest_misfit(found))), found))
    searched.sort(key=lambda item: item[0])
    starts_kept = [params for _score, params in searched[:3]] or candidates[:1]

    def assign(params):
        lower, upper, *_ = two_band_energies(design, params, n_a, n_b, n_v)
        near = np.where(np.abs(energies - lower) <= np.abs(energies - upper),
                        LOWER, UPPER)
        return np.where(fixed, branch, near)

    def residual_of(params, side):
        lower, upper, *_ = two_band_energies(design, params, n_a, n_b, n_v)
        return energies - np.where(side == UPPER, upper, lower)

    def run(start):
        params = start.copy()
        weights = np.ones(len(energies))
        side = assign(params)
        for _round in range(rounds if robust else 3):
            sw = np.sqrt(weights)
            result = least_squares(
                lambda p: sw * residual_of(p, side), params,
                jac=lambda p: -sw[:, None] * _two_band_jacobian(
                    design, p, n_a, n_b, n_v, side.astype(float)),
                method="lm" if len(energies) > n_params else "trf")
            params = result.x
            new_side = assign(params)
            residual = residual_of(params, new_side)
            new_weights = np.ones(len(energies))
            if robust:
                scale = 1.4826 * float(np.median(np.abs(residual - np.median(residual))))
                if scale > 0:
                    u = residual / (4.685 * scale)
                    new_weights = np.where(np.abs(u) < 1, (1 - u ** 2) ** 2, 0.0)
            done = np.array_equal(new_side, side) and np.allclose(
                new_weights, weights, atol=1e-4)
            side, weights = new_side, new_weights
            if done:
                break
        residual = residual_of(params, side)
        # Ranked by the mean misfit over *every* point: a start that ends by
        # declaring many points outliers (a flat band through one contour,
        # say) cannot win by doing so.
        score = float(np.mean(np.abs(residual)))
        return score, params, side, weights, residual

    best = min((run(s) for s in starts_kept), key=lambda r: r[0])
    score, params, side, weights, residual = best
    # Conventions that do not change the bands: v0 >= 0 (only V^2 enters),
    # and, when the two have as many shells, band a the lower on average.
    if params[2 + n_a + n_b] < 0:
        params[2 + n_a + n_b:] = -params[2 + n_a + n_b:]
    if n_a == n_b:
        pa, pb = params[:1 + n_a], params[1 + n_a:2 + 2 * n_a]
        if np.mean(design[:, :1 + n_a] @ pa) > np.mean(design[:, :1 + n_b] @ pb):
            params = np.concatenate([pb, pa, params[2 + 2 * n_a:]])

    jac = _two_band_jacobian(design, params, n_a, n_b, n_v, side.astype(float))
    jw = jac * np.sqrt(weights)[:, None]
    dof = max(1, len(energies) - n_params)
    sigma2 = float(np.sum(weights * residual ** 2) / dof)
    try:
        errors = np.sqrt(np.clip(np.diag(sigma2 * np.linalg.inv(jw.T @ jw)), 0, None))
    except np.linalg.LinAlgError:
        errors = np.full(n_params, np.nan)
    kept = weights > 0
    rms = float(np.sqrt(np.mean(residual[kept] ** 2))) if kept.any() else 0.0
    model = TwoBandFit(vectors, shell_list[:n_a], shell_list[:n_b],
                       shell_list[:n_v], params, errors, rms, len(energies), side)
    model.outliers = int(np.sum(~kept)) if robust else 0
    model.weights = weights
    model.score = score
    scaled = jw / np.maximum(np.linalg.norm(jw, axis=0), 1e-300)
    model.condition = float(np.linalg.cond(scaled))
    if model.condition > ILL_CONDITIONED:
        model.warning = (
            f"The points do not pin down every parameter (condition number "
            f"{model.condition:.3g}): other bands and couplings describe the "
            f"same points about as well. Use fewer shells, points at more "
            f"energies, or points near where the two bands meet.")
    return model


def evaluate(model: TBFit, kx, ky, kz: float = 0.0) -> np.ndarray:
    """E on the grid ``kx`` x ``ky`` (and the plane ``kz`` for a 3-D
    lattice), indexed ``[ix, iy]``."""
    kx, ky = np.asarray(kx, float), np.asarray(ky, float)
    gx, gy = np.meshgrid(kx, ky, indexing="ij")
    columns = [gx.ravel(), gy.ravel()]
    if model.vectors.shape[1] == 3:
        columns.append(np.full(gx.size, float(kz)))
    return model.energy(np.column_stack(columns)).reshape(gx.shape)


def read_points(path: str, with_branch: bool = False):
    """Band points from a CSV (or whitespace) table: ``(k (N, d), E (N,))``,
    and with ``with_branch`` a third array: each point's branch, from a
    ``branch`` or ``band`` column (``lower``/``upper``, -1/+1, or 0 / blank
    for either), :data:`AUTO` throughout if there is none.

    The columns are found by their header -- ``kx``, ``ky``, ``kz`` and an
    energy column ("E", "Energy...", "E - E_F...") -- so the ridge points
    written by the ridge-detection window (energy, kx, ky, strength) are
    read as they are. Without a header the order is kx, ky[, kz], E.
    """
    import csv
    import re

    with open(path, encoding="utf-8-sig") as handle:
        text = handle.read()
    rows = [r for r in csv.reader(text.splitlines(), skipinitialspace=True) if r]
    if rows and len(rows[0]) == 1:
        rows = [line.split() for line in text.splitlines() if line.strip()]

    def numeric(row):
        try:
            [float(v) for v in row]
            return True
        except ValueError:
            return False

    header = None if numeric(rows[0]) else [h.strip().lower() for h in rows[0]]
    ib = None
    if header is not None:
        ib = next((i for i, name in enumerate(header)
                   if re.match(r"^(branch|band)\b", name)), None)

    def cell(i, value):
        if i == ib:
            text = str(value).strip().lower()
            if text in ("lower", "low", "-1", "-1.0", "l"):
                return float(LOWER)
            if text in ("upper", "up", "1", "+1", "1.0", "u"):
                return float(UPPER)
            return float(AUTO)
        return float(value)

    def parse(row):
        try:
            return [cell(i, v) for i, v in enumerate(row)]
        except ValueError:
            return None

    parsed = [parse(row) for row in rows[header is not None:]]
    data = np.array([row for row in parsed if row is not None], dtype=float)
    if header is None:
        if data.shape[1] < 3:
            raise ValueError("need at least kx, ky and E columns")
        k, energies = data[:, :-1], data[:, -1]
        return (k, energies, np.zeros(len(energies), dtype=int)) if with_branch \
            else (k, energies)

    def find(pattern):
        for i, name in enumerate(header):
            if re.search(pattern, name):
                return i
        return None

    ix, iy, iz = find(r"^kx|k_x"), find(r"^ky|k_y"), find(r"^kz|k_z")
    ie = find(r"^e\b|^e[ _-]|energy|^e$|binding")
    if ix is None or iy is None or ie is None:
        raise ValueError("could not find kx, ky and energy columns in: "
                         + ", ".join(header))
    columns = [ix, iy] + ([iz] if iz is not None else [])
    if not with_branch:
        return data[:, columns], data[:, ie]
    branch = (data[:, ib].astype(int) if ib is not None
              else np.zeros(len(data), dtype=int))
    return data[:, columns], data[:, ie], branch
