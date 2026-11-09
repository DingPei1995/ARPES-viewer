"""The self-energy from an MDC series: Re and Im against a stated bare
band, the Kramers-Kronig relation between them, and what is read off."""
from types import SimpleNamespace

import numpy as np
import pytest

import arpes_viewer.tools.spectra.dispersion as D

V_BARE, K_F = 3.0, 0.5          # eV*A, 1/A
STEP, MODE, OFFSET = 0.03, 0.07, 0.008   # eV: an Einstein-like mode


def _im(energy, width=0.008):
    """|Im Sigma|: a constant (defects) plus a broadened step at the mode."""
    return OFFSET + STEP * 0.5 * (1 + np.tanh((np.abs(energy) - MODE) / width))


def _re_exact(energy, width=0.008):
    """Re Sigma of ``_im`` by brute force on a dense, wide, symmetric grid
    -- nothing in common with the function under test but the definition."""
    reach, grid = 40.0, np.linspace(-40.0, 40.0, 1_600_001)
    values = _im(grid, width)
    out = []
    for e in np.atleast_1d(energy):
        with np.errstate(divide="ignore", invalid="ignore"):
            f = (values - _im(e, width)) / (grid - e)
        f[~np.isfinite(f)] = 0.0
        out.append(-(np.trapezoid(f, grid)
                     + _im(e, width) * np.log(abs((reach - e) / (-reach - e))))
                   / np.pi)
    return np.array(out)


def _series(energy, noise=0.0, seed=0):
    """What an MDC fit of a band with that self-energy returns."""
    rng = np.random.default_rng(seed)
    k = K_F + (energy - _re_exact(energy)) / V_BARE
    fwhm = 2.0 * _im(energy) / V_BARE
    k_error = np.full(energy.size, 5e-4)
    w_error = np.full(energy.size, 1.5e-3)
    k = k + noise * k_error * rng.standard_normal(energy.size)
    fwhm = fwhm + noise * w_error * rng.standard_normal(energy.size)
    return SimpleNamespace(
        direction="mdc", positions=energy, names=["band 1"],
        centres=k[:, None], centre_errors=k_error[:, None],
        widths=fwhm[:, None], width_errors=w_error[:, None])


ENERGY = np.linspace(-0.30, -0.004, 100)


def test_kramers_kronig_of_a_sharp_step_is_the_logarithm():
    """|Im| = g beyond a mode energy W, the same on both sides of E_F:
    Re = (g/pi) ln|(W - E)/(W + E)|, positive below E_F."""
    energy = np.linspace(-0.3, -0.002, 600)
    imaginary = np.where(np.abs(energy) > MODE, STEP, 0.0) + OFFSET
    expected = STEP / np.pi * np.log(np.abs((MODE - energy) / (MODE + energy)))
    found = D.kramers_kronig(energy, imaginary)
    assert found[np.argmin(np.abs(energy + 0.05))] > 0
    # away from the jump itself, which the grid draws as a ramp one step wide
    away = np.abs(np.abs(energy) - MODE) > 0.01
    np.testing.assert_allclose(found[away], expected[away], atol=5e-4)


def test_kramers_kronig_matches_the_integral_done_the_long_way():
    found = D.kramers_kronig(ENERGY, _im(ENERGY))
    np.testing.assert_allclose(found, _re_exact(ENERGY), atol=3e-4)
    # an uneven grid, given in any order, and E_F somewhere else
    rng = np.random.default_rng(1)
    uneven = np.sort(rng.uniform(-0.3, -0.004, 150))
    order = rng.permutation(uneven.size)
    shifted = D.kramers_kronig(uneven[order] + 16.5, _im(uneven[order]), ef=16.5)
    np.testing.assert_allclose(shifted, _re_exact(uneven[order]), atol=6e-4)


def test_a_constant_width_gives_no_real_part():
    """Defect scattering alone: |Im| constant, Re zero everywhere -- not
    the logarithmic spikes a transform cut off at the data's ends gives."""
    found = D.kramers_kronig(ENERGY, np.full(ENERGY.size, 0.02))
    np.testing.assert_allclose(found, 0.0, atol=1e-12)
    cut_off = D.kramers_kronig(ENERGY, np.full(ENERGY.size, 0.02), tail=False)
    assert np.max(np.abs(cut_off)) > 5e-3


def test_the_self_energy_is_recovered_with_the_true_bare_band():
    series = _series(ENERGY)
    result = D.self_energy(series, D.bare_band_line(K_F, V_BARE))
    np.testing.assert_allclose(result.real, _re_exact(ENERGY), atol=1e-9)
    np.testing.assert_allclose(result.imaginary, _im(ENERGY), atol=1e-9)
    assert result.consistency() < 0.02          # Re and KK[Im] are a pair
    assert result.k_f == pytest.approx(K_F, abs=2e-4)
    # the coupling, twice: the slope of Re at E_F and the velocity ratio
    coupling, error, window = result.coupling()
    assert coupling == pytest.approx(V_BARE / result.v_f - 1.0, abs=0.01)
    assert 0.2 < coupling < 0.4 and error < 0.02 and 0 < window < MODE
    kink_energy, kink_value, inside = result.kink()
    assert inside and kink_energy == pytest.approx(-MODE, abs=0.01)
    assert kink_value > 0.02
    at_ef, at_ef_error = result.imaginary_at_ef()
    assert at_ef == pytest.approx(OFFSET, abs=1e-3)
    path, _error = result.mean_free_path()
    assert path == pytest.approx(V_BARE / (2 * OFFSET), rel=0.1)
    lifetime, _error = result.lifetime_fs()
    assert lifetime == pytest.approx(D.HBAR_EVFS / (2 * OFFSET), rel=0.1)
    text = "\n".join(result.summary())
    assert "λ" in text and "meV" in text and "mean free path" in text


def test_a_wrong_bare_band_fails_the_kramers_kronig_check():
    series = _series(ENERGY)
    good = D.self_energy(series, D.bare_band_line(K_F, V_BARE)).consistency()
    for velocity in (0.8 * V_BARE, 1.5 * V_BARE):
        bad = D.self_energy(series, D.bare_band_line(K_F, velocity))
        assert bad.consistency() > 10 * good and bad.consistency() > 0.3


@pytest.mark.parametrize("noise, tolerance", [(0.0, 0.01), (1.0, 0.1)])
def test_the_bare_velocity_is_found_from_the_two_curves_alone(noise, tolerance):
    series = _series(ENERGY, noise=noise, seed=3)
    velocity, mismatch, k_f, v_f = D.suggest_bare_velocity(series)
    assert velocity == pytest.approx(V_BARE, rel=tolerance)
    assert k_f == pytest.approx(K_F, abs=2e-3) and 0 < v_f < V_BARE
    assert mismatch < 0.3


def test_the_resolution_is_removed_from_the_width_in_quadrature():
    series = _series(ENERGY)
    resolution = 0.01
    series.widths = np.hypot(series.widths, resolution)
    bare = D.bare_band_line(K_F, V_BARE)
    np.testing.assert_allclose(
        D.self_energy(series, bare, resolution=resolution).imaginary,
        _im(ENERGY), atol=1e-9)
    assert np.all(D.self_energy(series, bare).imaginary > _im(ENERGY))


def test_an_anchor_at_the_fermi_level_is_reached_not_clipped():
    """The fit stops 4 meV below E_F; a bare band "through E_F" must go
    through the band's crossing, not through the last fitted point."""
    series = _series(ENERGY)
    k, energy = series.centres[:, 0], series.positions
    bare = D.bare_band_from_anchors(k, energy, [0.0, -0.30])
    assert bare.crossing(0.0)[0] == pytest.approx(K_F, abs=3e-4)
    assert float(bare.value(k[0])) == pytest.approx(-0.30, abs=2e-3)
    # one stray point at an anchor counts for part of what it would alone
    k_stray = k.copy()
    k_stray[0] += 0.01
    tilt = {}
    for average in (2, 5):
        true = D.bare_band_from_anchors(k, energy, [0.0, -0.30], average=average)
        stray = D.bare_band_from_anchors(k_stray, energy, [0.0, -0.30],
                                         average=average)
        tilt[average] = abs(float(stray.slope(K_F)) / float(true.slope(K_F)) - 1)
    assert tilt[5] < 0.7 * tilt[2]
    with pytest.raises(ValueError):
        D.bare_band_from_anchors(k, energy, [0.0])


def test_edc_series_and_a_range_without_a_kink_are_said_so():
    series = _series(ENERGY)
    series.direction = "edc"
    with pytest.raises(ValueError, match="MDC"):
        D.self_energy(series, D.bare_band_line(K_F, V_BARE))
    shallow = np.linspace(-0.04, -0.004, 30)      # stops above the mode
    result = D.self_energy(_series(shallow), D.bare_band_line(K_F, V_BARE))
    assert not result.kink()[2]
    assert any("no maximum" in line for line in result.summary())
