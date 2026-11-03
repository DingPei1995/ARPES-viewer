"""Angle and photon energy into k_par and k_z.

The conversion is a coordinate change, so the tests are mostly of the kind
"put a known thing in and get it back": a band built to be periodic in k_z
with a known inner potential must come out periodic with that period, and
the map must invert exactly.

The one test worth reading is
``test_the_manipulator_angle_comes_out_of_kz``: the second in-plane momentum
component that a tilted manipulator produces must come out of k_z. It is not
a small effect.
"""
import numpy as np
import pytest

from arpes_viewer.tools.momentum import kzconv


A = kzconv.A_CONST


def make_scan(*, inner_potential=12.0, spacing=6.0, work_function=4.5,
              photon=(40.0, 120.0, 41), angles=(-15.0, 15.0, 120),
              energies=(-0.5, 0.1, 40), theta_position=0.0,
              effective_mass=1.0):
    """A photon-energy scan of a band that is periodic along k_z.

    Built by evaluating the band at the k each measured point really
    corresponds to, so the only way the conversion recovers the period is by
    getting the geometry right.
    """
    hv = np.linspace(*photon[:2], photon[2])
    angle = np.linspace(*angles[:2], angles[2])
    energy = np.linspace(*energies[:2], energies[2])
    g = 2 * np.pi / spacing

    kinetic = hv[:, None, None] - work_function + energy[None, None, :]
    alpha = np.radians(angle)[None, :, None]
    k_par, k_z = kzconv.forward(
        np.broadcast_to(kinetic, (hv.size, angle.size, energy.size)),
        np.broadcast_to(alpha, (hv.size, angle.size, energy.size)),
        inner_potential=inner_potential, effective_mass=effective_mass,
        theta_position=np.radians(theta_position))
    cube = (0.5 * (1 + np.cos(2 * np.pi * k_z / g))
            * np.exp(-(k_par / 0.6) ** 2))
    return hv, angle, energy, np.nan_to_num(cube), g


# --------------------------------------------------------------------------
# The map
# --------------------------------------------------------------------------
def test_the_constant_is_the_familiar_prefactor():
    """k = 0.5123 sqrt(E[eV]) sin(theta), to four figures."""
    assert np.sqrt(A) == pytest.approx(0.5123, abs=5e-5)


@pytest.mark.parametrize("theta_position", [0.0, 0.1, -0.25, 0.4])
def test_forward_and_inverse_are_exact_inverses(theta_position):
    rng = np.random.default_rng(0)
    for _ in range(2000):
        kinetic = rng.uniform(20.0, 150.0)
        alpha = rng.uniform(-0.35, 0.35)
        v0 = rng.uniform(5.0, 25.0)
        mass = rng.uniform(0.7, 1.5)
        k_par, k_z = kzconv.forward(
            kinetic, alpha, inner_potential=v0, effective_mass=mass,
            theta_position=theta_position)
        back_e, back_a = kzconv.inverse(
            k_z, k_par, inner_potential=v0, effective_mass=mass,
            theta_position=theta_position)
        assert back_e == pytest.approx(kinetic, abs=1e-9)
        assert back_a == pytest.approx(alpha, abs=1e-9)


def test_normal_emission_is_pure_kz():
    k_par, k_z = kzconv.forward(80.0, 0.0, inner_potential=12.0)
    assert k_par == pytest.approx(0.0, abs=1e-12)
    assert k_z == pytest.approx(np.sqrt(A * (80.0 + 12.0)), rel=1e-12)


def test_the_manipulator_angle_comes_out_of_kz():
    """The tilted manipulator, as a number.

    A tilted manipulator gives the emitted electron a second in-plane
    momentum component. Leaving it in k_z inflates k_z, and at 20 degrees that is a quarter of a zone for a
    6 A repeat.
    """
    kinetic, v0 = 80.0, 12.0
    _k_par, upright = kzconv.forward(kinetic, 0.0, inner_potential=v0,
                                     theta_position=0.0)
    _k_par, tilted = kzconv.forward(kinetic, 0.0, inner_potential=v0,
                                    theta_position=np.radians(20.0))
    assert tilted < upright
    difference = float(upright - tilted)
    assert difference == pytest.approx(0.2566, abs=0.01)
    assert difference / (2 * np.pi / 6.0) > 0.2      # of a zone


def test_kz_is_always_real_for_a_free_electron_final_state():
    """Worth pinning down, because it is why an abort-on-imaginary check
    almost never fires.

    With ``m* = 1`` the requirement is ``A E sin^2(a) > A (E + V0)``, and
    since ``sin^2 <= 1`` that cannot happen for any positive inner
    potential -- at any kinetic energy, at any angle.
    """
    for kinetic in (1.0, 5.0, 50.0, 500.0):
        for degrees in (0.0, 45.0, 85.0, 89.9):
            _k_par, k_z = kzconv.forward(kinetic, np.radians(degrees),
                                         inner_potential=0.5)
            assert np.isfinite(k_z), (kinetic, degrees)


def test_momentum_beyond_the_final_state_is_not_a_number():
    """A final state lighter than a free electron *can* be outrun by the
    in-plane momentum. Those points have no real k_z, which is a region to
    leave blank rather than an error to raise on.
    """
    _k_par, k_z = kzconv.forward(100.0, np.radians(80.0), inner_potential=10.0,
                                 effective_mass=0.5)
    assert np.isnan(k_z)


def test_an_effective_mass_that_cancels_the_tilt_is_refused():
    with pytest.raises(ValueError, match="no unique solution"):
        kzconv.inverse(1.0, 0.0, inner_potential=12.0,
                       effective_mass=np.sin(np.radians(30.0)) ** 2,
                       theta_position=np.radians(30.0))


# --------------------------------------------------------------------------
# Converting a cube
# --------------------------------------------------------------------------
def test_the_converted_cube_has_the_period_it_was_built_with():
    hv, angle, energy, cube, g = make_scan(inner_potential=12.0, spacing=6.0)
    kz_axis, _kpar, _e, out = kzconv.to_kz_cube(
        hv, angle, energy, cube, inner_potential=12.0, work_function=4.5,
        n_kz=300, n_kpar=64)
    import warnings
    middle = out[:, 24:40, :10]
    with warnings.catch_warnings():
        # k_z rows outside the measured band are all-NaN, which is the
        # point of them; averaging those is not a problem to report.
        warnings.simplefilter("ignore", RuntimeWarning)
        profile = np.nanmean(middle, axis=(1, 2))
    found = kzconv._dominant_period(kz_axis, profile, g)
    assert found == pytest.approx(g, rel=0.03)


def test_kz_leads_and_the_energy_axis_is_untouched():
    hv, angle, energy, cube, _g = make_scan()
    kz_axis, kpar_axis, out_energy, out = kzconv.to_kz_cube(
        hv, angle, energy, cube, inner_potential=12.0, work_function=4.5,
        n_kz=64, n_kpar=48)
    assert out.shape == (64, 48, energy.size)
    assert np.allclose(out_energy, energy)
    # k_z is the first axis and increases; k_par straddles zero
    assert kz_axis[0] < kz_axis[-1]
    assert kz_axis[0] > 0
    assert kpar_axis[0] < 0 < kpar_axis[-1]


def test_points_the_measurement_never_reached_are_blank():
    """The measured region is a curved band; its bounding rectangle is not.
    The corners have to be NaN rather than the nearest sample smeared out."""
    hv, angle, energy, cube, _g = make_scan()
    _kz, _kpar, _e, out = kzconv.to_kz_cube(
        hv, angle, energy, cube, inner_potential=12.0, work_function=4.5,
        n_kz=80, n_kpar=80)
    blank = ~np.isfinite(out)
    assert blank.any(), "a rectangle around a curved region has empty corners"
    assert not blank.all()


def test_nan_in_the_input_stays_nan():
    """The Fermi-surface correction pads the ends of its energy axis with
    NaN, and those pads must not be smeared into the converted cube."""
    hv, angle, energy, cube, _g = make_scan()
    cube = cube.copy()
    cube[:, :, :3] = np.nan                      # what a correction leaves
    _kz, _kpar, _e, out = kzconv.to_kz_cube(
        hv, angle, energy, cube, inner_potential=12.0, work_function=4.5,
        n_kz=48, n_kpar=48)
    assert not np.isfinite(out[:, :, :3]).any()
    assert np.isfinite(out[:, :, 10:]).any()


def test_a_bigger_inner_potential_pushes_kz_out():
    hv, angle, energy, cube, _g = make_scan()
    first, *_ = kzconv.to_kz_cube(hv, angle, energy, cube, inner_potential=5.0,
                                  work_function=4.5, n_kz=32, n_kpar=32)
    second, *_ = kzconv.to_kz_cube(hv, angle, energy, cube, inner_potential=25.0,
                                   work_function=4.5, n_kz=32, n_kpar=32)
    assert second[0] > first[0]
    # ... and narrows the span, which is why the period barely constrains it
    assert (second[-1] - second[0]) < (first[-1] - first[0])


def test_a_mismatched_cube_is_refused():
    hv, angle, energy, cube, _g = make_scan()
    with pytest.raises(ValueError, match="but the axes say"):
        kzconv.to_kz_cube(hv, angle, energy, cube[:, :, :-1],
                          inner_potential=12.0, work_function=4.5)


def test_one_photon_energy_cannot_be_converted():
    """There is nothing to interpolate along k_z with."""
    hv, angle, energy, cube, _g = make_scan(photon=(40.0, 40.0, 1))
    with pytest.raises(ValueError, match="at least two photon energies"):
        kzconv.to_kz_cube(hv, angle, energy, cube, inner_potential=12.0,
                          work_function=4.5)


def test_progress_is_reported_once_per_energy_slice():
    hv, angle, energy, cube, _g = make_scan(energies=(-0.2, 0.1, 7))
    seen = []
    kzconv.to_kz_cube(hv, angle, energy, cube, inner_potential=12.0,
                      work_function=4.5, n_kz=16, n_kpar=16,
                      progress=lambda done, total: seen.append((done, total)))
    assert [d for d, _ in seen] == list(range(7))
    assert {t for _, t in seen} == {7}


# --------------------------------------------------------------------------
# The inner potential
# --------------------------------------------------------------------------
def test_the_scan_finds_the_inner_potential_it_was_built_with():
    hv, angle, energy, cube, _g = make_scan(inner_potential=12.0, spacing=6.0)
    result = kzconv.scan_inner_potential(
        hv, angle, energy, cube, spacing=6.0, work_function=4.5,
        inner_potentials=np.arange(4.0, 26.0, 1.0))
    assert result.best is not None
    assert result.best == pytest.approx(12.0, abs=4.0)


def test_the_scan_says_how_weak_it_is():
    """A couple of zones of coverage pins V0 to a few eV at best, and the
    number has to come out rather than be left for someone to discover."""
    hv, angle, energy, cube, _g = make_scan()
    result = kzconv.scan_inner_potential(
        hv, angle, energy, cube, spacing=6.0, work_function=4.5,
        inner_potentials=np.arange(4.0, 26.0, 1.0))
    assert result.sensitivity < 0          # period shrinks as V0 grows
    assert 0.5 < result.uncertainty() < 30.0


def test_the_scan_reports_the_period_the_lattice_wants():
    hv, angle, energy, cube, _g = make_scan()
    result = kzconv.scan_inner_potential(
        hv, angle, energy, cube, spacing=6.0, work_function=4.5,
        inner_potentials=np.arange(8.0, 18.0, 2.0))
    assert result.target == pytest.approx(2 * np.pi / 6.0)


# --------------------------------------------------------------------------
# Is the Fermi surface flat?
# --------------------------------------------------------------------------
def test_a_flat_edge_reads_as_flat():
    from arpes_viewer.tools.spectra.fermi import fermi_edge_model
    angle = np.linspace(-15, 15, 40)
    energy = np.linspace(-0.6, 0.3, 120)
    edge = fermi_edge_model(energy, ef=0.0, temperature=25.0, resolution=0.02,
                            dos0=100.0, dos1=0.0, bkg0=2.0, bkg1=0.0)
    cube = np.broadcast_to(edge, (5, angle.size, energy.size)).copy()
    spread, _positions, _angles = kzconv.edge_flatness(cube, angle, energy)
    assert spread < 0.02


def test_a_bent_edge_is_measured():
    from arpes_viewer.tools.spectra.fermi import fermi_edge_model
    angle = np.linspace(-15, 15, 40)
    energy = np.linspace(-0.6, 0.3, 200)
    bend = 0.15 * (angle / 15.0) ** 2
    cube = np.empty((3, angle.size, energy.size))
    for j, shift in enumerate(bend):
        cube[:, j] = fermi_edge_model(energy, ef=shift, temperature=25.0,
                                      resolution=0.02, dos0=100.0, dos1=0.0,
                                      bkg0=2.0, bkg1=0.0)
    spread, positions, angles = kzconv.edge_flatness(cube, angle, energy)
    assert spread == pytest.approx(0.15, abs=0.03)
    assert positions.size == angles.size >= 20


def test_one_stray_channel_does_not_set_the_bend():
    """A flat edge with a band crossing E_F in a few channels, and weak,
    noisy channels at the slit ends: the screening number stays small."""
    from arpes_viewer.tools.spectra.fermi import fermi_edge_model
    rng = np.random.default_rng(1)
    angle = np.linspace(-15, 15, 120)
    energy = np.linspace(-0.4, 0.2, 200)
    edge = fermi_edge_model(energy, ef=0.0, temperature=25.0, resolution=0.02,
                            dos0=100.0, dos1=0.0, bkg0=2.0, bkg1=0.0)
    frame = np.broadcast_to(edge, (angle.size, energy.size)).copy()
    frame[55:60] += 300.0 * np.exp(-0.5 * ((energy + 0.25) / 0.02) ** 2)
    frame[:6] *= 0.05
    frame[-6:] *= 0.05
    frame += rng.normal(0.0, 3.0, frame.shape)
    cube = np.broadcast_to(frame, (3,) + frame.shape).copy()
    spread, _positions, _angles = kzconv.edge_flatness(cube, angle, energy)
    assert spread < 0.03


def test_the_flatness_check_ignores_the_correction_padding():
    """An FS-corrected cube has NaN at the ends of its grown energy axis."""
    from arpes_viewer.tools.spectra.fermi import fermi_edge_model
    angle = np.linspace(-15, 15, 30)
    energy = np.linspace(-0.6, 0.3, 150)
    edge = fermi_edge_model(energy, ef=0.0, temperature=25.0, resolution=0.02,
                            dos0=100.0, dos1=0.0, bkg0=2.0, bkg1=0.0)
    cube = np.broadcast_to(edge, (4, angle.size, energy.size)).copy()
    cube[:, :5, :] = np.nan                  # channels the shift emptied
    spread, _positions, angles = kzconv.edge_flatness(cube, angle, energy)
    assert np.isfinite(spread)
    assert angles.size > 0 and angles.min() > angle[4]


# --------------------------------------------------------------------------
# Grid, Γ and the photon-energy calibration
# --------------------------------------------------------------------------
def _hv_scan():
    hv = np.linspace(60.0, 100.0, 21)
    angle = np.linspace(-12.0, 12.0, 300)
    energy = np.linspace(-0.3, 0.05, 8)
    rng = np.random.default_rng(3)
    cube = rng.random((hv.size, angle.size, energy.size))
    return hv, angle, energy, cube


def test_a_constant_calibration_is_the_single_work_function():
    hv, angle, energy, cube = _hv_scan()
    one = kzconv.to_kz_cube(hv, angle, energy, cube, inner_potential=12.0,
                            work_function=4.3, n_kz=40, n_kpar=50)
    each = kzconv.to_kz_cube(hv, angle, energy, cube, inner_potential=12.0,
                             work_function=np.full(hv.size, 4.3),
                             n_kz=40, n_kpar=50)
    assert np.allclose(one[0], each[0]) and np.allclose(one[1], each[1])
    assert np.allclose(one[3], each[3], equal_nan=True)


def test_a_calibrated_scan_samples_each_photon_energy_where_it_belongs():
    """A slice that is bright only at one photon energy lands at the k_z of
    that photon energy's own E_kin(E_F), not of its nominal hv."""
    hv, angle, energy, _cube = _hv_scan()
    cube = np.zeros((hv.size, angle.size, energy.size))
    cube[10] = 1.0
    phi = 4.3 + np.linspace(0.0, 0.6, hv.size)
    kz_axis, kpar_axis, _e, out = kzconv.to_kz_cube(
        hv, angle, energy, cube, inner_potential=12.0, work_function=phi,
        n_kz=400, n_kpar=31)
    centre = kpar_axis.size // 2
    profile = np.nan_to_num(out[:, centre, -2])
    kz_peak = kz_axis[int(np.argmax(profile))]
    expected = np.sqrt(kzconv.A_CONST * (hv[10] - phi[10] + energy[-2] + 12.0))
    assert kz_peak == pytest.approx(expected, abs=2 * (kz_axis[1] - kz_axis[0]))


def test_an_out_of_order_calibration_is_refused():
    hv = np.array([60.0, 61.0, 62.0])
    with pytest.raises(ValueError):
        kzconv.calibrated_photon_axis(hv, np.array([4.0, 5.5, 4.0]))


def test_the_default_grid_keeps_the_angle_channels_and_square_pixels():
    hv, angle, energy, _cube = _hv_scan()
    n_kz, n_kpar = kzconv.default_grid(hv, angle, energy, inner_potential=12.0,
                                       work_function=4.3)
    assert n_kpar == angle.size
    (kz_lo, kz_hi), (p_lo, p_hi) = kzconv.kz_bounds(
        hv, angle, energy, inner_potential=12.0, work_function=4.3)
    assert (kz_hi - kz_lo) / (n_kz - 1) == pytest.approx(
        (p_hi - p_lo) / (n_kpar - 1), rel=0.05)


def test_v0_for_gamma_puts_gamma_at_that_photon_energy():
    period = 2 * np.pi / 6.0
    v0, n = kzconv.inner_potential_for_gamma(80.0, period, work_function=4.3)
    kz = np.sqrt(kzconv.A_CONST * (80.0 - 4.3 + v0))
    assert kz == pytest.approx(n * period)
    # the order chosen is the one whose V0 is nearest 12 eV
    others = [kzconv.inner_potential_for_gamma(80.0, period, work_function=4.3,
                                               order=m)[0] for m in (n - 1, n + 1)]
    assert all(abs(v0 - 12.0) <= abs(v - 12.0) for v in others)
    v_next, _ = kzconv.inner_potential_for_gamma(80.0, period,
                                                 work_function=4.3, order=n + 1)
    assert v_next > v0


def test_measured_work_functions_undo_the_loader_reference():
    hv = np.array([60.0, 70.0, 80.0])
    table = np.array([4.2, 4.2, 4.2])
    true = np.array([4.65, 4.65, 4.99])
    start = hv - true - 0.5        # each window starts 0.5 eV below its E_F
    first_binding = start[0] - hv[0] + table[0]
    # where the stacked cube (member one's axis) shows each E_F
    ef = first_binding + 0.5
    info = {"kz.fermi_level_eV": np.full(3, ef),
            "cassiopee.member_photon_energy_eV": hv,
            "cassiopee.member_work_function_eV": table,
            "cassiopee.member_kinetic_start_eV": start}
    assert kzconv.measured_work_functions(info) == pytest.approx(true)
    assert kzconv.measured_work_functions({}) is None
