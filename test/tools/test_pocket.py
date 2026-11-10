"""A Fermi pocket of a quasi-two-dimensional sample from a k-map: the
contour ray by ray, its area, and what the area gives."""
import numpy as np
import pytest

import arpes_viewer.tools.spectra.pocket as PK
from arpes_viewer.tools.spectra.dispersion import HBAR2_OVER_2M

KX = np.linspace(-0.8, 0.8, 129)
KY = np.linspace(-0.7, 0.7, 113)
ENERGY = np.linspace(-0.4, 0.05, 91)
MASS, MU, WARP = 1.2, 0.3, 0.12          # m_e, eV, hexagonal warping
C = HBAR2_OVER_2M / MASS
CENTRE = (0.05, -0.03)


def cube(noise=0.0, hole=False, seed=0, centre=CENTRE):
    """A band ``C k^2 (1 + w cos 6 phi) - mu`` about ``centre`` (or its
    mirror in energy, a hole band), as a k-map with a Fermi cut-off."""
    x, y, e = np.meshgrid(KX - centre[0], KY - centre[1], ENERGY, indexing="ij")
    band = C * (x ** 2 + y ** 2) * (1 + WARP * np.cos(6 * np.arctan2(y, x))) - MU
    if hole:
        band = -band - 0.25
    values = 0.03 ** 2 / ((e - band) ** 2 + 0.03 ** 2) / (np.exp(e / 0.004) + 1)
    values = values + 0.03
    if noise:
        values = values + noise * np.random.default_rng(seed).standard_normal(
            values.shape)
    return values


def area_of(energy):
    """The area inside the contour at ``energy``, exactly."""
    return (energy + MU) / (2 * C) * 2 * np.pi / np.sqrt(1 - WARP ** 2)


AXES = (KX, KY, ENERGY)


def test_the_plane_is_the_mean_over_the_window():
    values = cube()
    plane, used = PK.energy_plane(values, AXES, -0.05, 0.006)
    inside = np.abs(ENERGY + 0.05) <= 0.006
    np.testing.assert_allclose(plane, values[:, :, inside].mean(axis=2))
    assert used == (ENERGY[inside].min(), ENERGY[inside].max())
    nearest, used = PK.energy_plane(values, AXES, -0.0513, 0.0)
    assert used[0] == used[1] == ENERGY[np.argmin(np.abs(ENERGY + 0.0513))]
    with pytest.raises(ValueError, match="map"):
        PK.energy_plane(values[:, :, 0], AXES, 0.0)


def test_one_ray_gives_the_crossing_with_an_error():
    plane, _ = PK.energy_plane(cube(), AXES, -0.05, 0.006)
    radii = np.linspace(0.1, 0.6, 120)
    profile = PK.radial_profiles(plane, KX, KY, CENTRE, [0.0], radii,
                                 sector=0.05)[0]
    fit = PK.fit_ray(radii, profile, 0.1, 0.6)
    expected = np.sqrt((MU - 0.05) / (C * (1 + WARP)))
    assert fit["ok"] and fit["k"] == pytest.approx(expected, abs=0.004)
    assert 0 < fit["k_error"] < 0.005 and 0.01 < fit["width"] < 0.1
    assert np.isfinite(fit["model"]).sum() > 50
    # a ring that misses the band, and one with no data in it
    assert not PK.fit_ray(radii, profile, 0.1, 0.2)["ok"]
    empty = PK.fit_ray(radii, np.full(radii.size, np.nan), 0.1, 0.6)
    assert not empty["ok"] and "no data" in empty["why"]


@pytest.mark.parametrize("noise", [0.0, 0.05])
def test_the_area_of_a_warped_pocket(noise):
    plane, _ = PK.energy_plane(cube(noise), AXES, -0.05, 0.006)
    contour = PK.trace(plane, KX, KY, CENTRE, 0.1, 0.6)
    assert contour.ok.sum() >= 70
    fitted = contour.fourier(6, fold=6)
    area, error = fitted.area()
    assert area == pytest.approx(area_of(-0.05), rel=0.01)
    assert 0 < error < 0.01 * area
    assert contour.polygon_area() == pytest.approx(area, rel=0.01)
    low, at_low, high, at_high = fitted.extremes()
    assert np.degrees(at_low) % 60 == pytest.approx(0.0, abs=1.0)   # warping
    assert np.degrees(at_high) % 60 == pytest.approx(30.0, abs=1.0)
    assert high / low == pytest.approx(np.sqrt((1 + WARP) / (1 - WARP)), rel=0.02)
    x, y = contour.xy()
    assert x.size == contour.ok.sum() == y.size


def test_the_area_does_not_depend_on_the_centre():
    """From a point well off the middle the contour is another function of
    the angle, and the area the same; its centre of area leads back."""
    plane, _ = PK.energy_plane(cube(), AXES, -0.05, 0.006)
    off = (CENTRE[0] + 0.08, CENTRE[1] - 0.06)
    contour = PK.trace(plane, KX, KY, off, 0.05, 0.6)
    fitted = contour.fourier(10)
    assert fitted.area()[0] == pytest.approx(area_of(-0.05), rel=0.015)
    middle = fitted.centroid(contour.centre)
    assert middle == pytest.approx(CENTRE, abs=0.006)


def test_a_circle_is_harmonic_zero_and_too_few_rays_say_so():
    plane, _ = PK.energy_plane(cube(), AXES, -0.05, 0.006)
    contour = PK.trace(plane, KX, KY, CENTRE, 0.1, 0.6, n_angles=24)
    circle = contour.fourier(0)
    assert circle.harmonics.size == 0
    assert circle.area()[0] == pytest.approx(np.pi * circle.coefficients[0] ** 2)
    assert circle.area()[0] == pytest.approx(area_of(-0.05), rel=0.03)
    many = contour.fourier(40)                    # capped by the rays there are
    assert many.coefficients.size <= contour.ok.sum() // 3
    contour.ok[:] = False
    with pytest.raises(ValueError, match="fewer than three"):
        contour.fourier(4)
    with pytest.raises(ValueError, match="ring"):
        PK.trace(plane, KX, KY, CENTRE, 0.3, 0.3)


def test_a_second_band_in_the_ring_does_not_take_rays_away():
    """A stronger band crossing part of the ring: the rays it captured
    disagree with their neighbours, are looked at again near them, and the
    area holds."""
    values = cube()
    plane, _ = PK.energy_plane(values, AXES, -0.05, 0.006)
    x, y = np.meshgrid(KX, KY, indexing="ij")
    intruder = 2.0 / (1 + ((x - 0.52) / 0.02) ** 2)       # a line at kx = 0.52
    contour = PK.trace(plane + intruder, KX, KY, CENTRE, 0.1, 0.6)
    assert contour.fourier(6, fold=6).area()[0] == pytest.approx(
        area_of(-0.05), rel=0.02)
    # where part of the map is missing, those rays are dropped, not invented
    holed = plane.copy()
    holed[KX > 0.2, :] = np.nan
    partial = PK.trace(holed, KX, KY, CENTRE, 0.1, 0.6)
    assert 20 < partial.ok.sum() < 60
    gone = np.cos(partial.angles) > 0.9
    assert not partial.ok[gone].any()
    assert partial.fourier(6, fold=6).area()[0] == pytest.approx(
        area_of(-0.05), rel=0.03)                 # the symmetry bridges it


def test_what_the_area_gives():
    n = PK.numbers(0.3, 0.003, spin=2, pockets=1,
                   cell=PK.cell_area(3.3, None, 120.0))
    assert n["k_f"] == pytest.approx(np.sqrt(0.3 / np.pi))
    assert n["density"] == pytest.approx(2 * 0.3 / (2 * np.pi) ** 2 * 1e16)
    assert n["density_error"] == pytest.approx(0.01 * n["density"])
    # the Onsager relation: 1 A^-2 is 10.48 kT
    assert PK.FREQUENCY_FACTOR == pytest.approx(1.0476e4, rel=1e-4)
    assert n["frequency"] == pytest.approx(0.3 * PK.FREQUENCY_FACTOR)
    zone = (2 * np.pi) ** 2 / (3.3 * 3.3 * np.sin(np.radians(120)))
    assert n["zone_area"] == pytest.approx(zone)
    assert n["per_cell"] == pytest.approx(2 * 0.3 / zone)
    # a full zone of a spin-degenerate band holds two electrons per cell
    assert PK.numbers(zone, cell=PK.cell_area(3.3, None, 120.0))["per_cell"] \
        == pytest.approx(2.0)
    # spin-split, three pockets; no cell, no count per cell
    split = PK.numbers(0.3, spin=1, pockets=3)
    assert split["density"] == pytest.approx(1.5 * n["density"])
    assert "per_cell" not in split
    assert PK.cell_area(3.0, 4.0) == pytest.approx(12.0)


def test_the_mass_and_the_carrier_from_the_area_against_energy():
    energies = np.linspace(-0.02, -0.2, 10)
    found = PK.series(cube(0.02), AXES, CENTRE, energies, 0.1, 0.6,
                      half_width=0.006, fold=6)
    assert np.isfinite(found.areas).all()
    np.testing.assert_allclose(found.areas, area_of(energies), rtol=0.015)
    mass, error = found.mass()
    # the cyclotron mass of the warped band: m / sqrt(1 - w^2)
    assert mass == pytest.approx(MASS / np.sqrt(1 - WARP ** 2), rel=0.02)
    assert 0 < error < 0.02 and found.carrier() == "electron"
    assert found.area_at_ef()[0] == pytest.approx(area_of(0.0), rel=0.01)
    assert found.band_edge() == pytest.approx(-MU, abs=0.01)
    velocity, _error = found.fermi_velocity()
    k_f = np.sqrt(area_of(0.0) / np.pi)
    assert velocity == pytest.approx(2 * HBAR2_OVER_2M * k_f / mass, rel=0.01)
    assert len(found.contours) == energies.size
    assert found.contours[3].energy == pytest.approx(energies[3])


def test_a_hole_pocket_shrinks_with_energy():
    energies = np.linspace(-0.02, -0.12, 8)
    found = PK.series(cube(0.02, hole=True), AXES, CENTRE, energies, 0.05, 0.6,
                      half_width=0.006)
    assert np.all(np.diff(found.areas) > 0)       # larger further below E_F
    mass, error = found.mass()
    assert mass == pytest.approx(-MASS / np.sqrt(1 - WARP ** 2), rel=0.05)
    assert found.carrier() == "hole"


def test_energies_without_a_pocket_are_left_out():
    # below the band bottom there is nothing to trace
    found = PK.series(cube(), AXES, CENTRE, [-0.05, -0.38], 0.1, 0.6,
                      half_width=0.006)
    assert np.isfinite(found.areas[0]) and np.isnan(found.areas[1])
    assert found.line() is None and np.isnan(found.mass()[0])
    assert found.carrier() == ""


def test_the_module_says_what_it_is_for():
    assert "quasi-two-dimensional" in PK.NOTICE and "Under test" in PK.NOTICE
    assert "quasi-two-dimensional" in PK.__doc__
