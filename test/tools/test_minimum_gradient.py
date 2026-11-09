"""The minimum-gradient picture: bands as the valleys of |grad I|."""
import numpy as np
import pytest

import arpes_viewer.tools.processing.process as P

K = np.linspace(-0.6, 0.6, 241)
E = np.linspace(-0.5, 0.05, 221)


def _band(k0=lambda e: 0.25 + 0.5 * e, width=0.03, noise=0.0, matrix=None,
          seed=0):
    """A Lorentzian band on a flat background, optionally with an
    intensity that falls along the band (a matrix element)."""
    kk, ee = np.meshgrid(K, E, indexing="ij")
    values = 1.0 / (1.0 + ((kk - k0(ee)) / width) ** 2)
    if matrix is not None:
        values = values * matrix(ee)
    values = values + 0.02
    if noise:
        values = values + noise * np.random.default_rng(seed).standard_normal(
            values.shape)
    return values


def _ridge(picture, rows):
    """Where each MDC of ``picture`` peaks, in k."""
    return K[np.nanargmax(picture[:, rows], axis=0)]


ROWS = np.arange(30, E.size - 30, 10)


def test_the_band_is_where_the_ratio_peaks():
    out = P.minimum_gradient(_band(), [K, E])
    assert out.shape == (K.size, E.size)
    np.testing.assert_allclose(_ridge(out, ROWS), 0.25 + 0.5 * E[ROWS],
                               atol=K[1] - K[0])
    # and the band is far narrower in it than in the data
    row = out[:, ROWS[5]]
    assert (row > 0.5 * row.max()).sum() < 0.4 * (
        _band()[:, ROWS[5]] > 0.5 * _band()[:, ROWS[5]].max()).sum()


def test_the_three_forms():
    data = _band()
    modulus = P.minimum_gradient(data, [K, E], form="modulus")
    inverse = P.minimum_gradient(data, [K, E], form="inverse")
    ratio = P.minimum_gradient(data, [K, E], form="ratio")
    on = np.argmin(np.abs(K - (0.25 + 0.5 * E[100])))       # on the band
    slope = on + 3                                          # on its flank
    far = np.argmin(np.abs(K + 0.5))                        # empty region
    assert modulus[on, 100] < 0.2 * modulus[slope, 100]     # a valley
    assert inverse[on, 100] > 3 * inverse[slope, 100]
    assert ratio[on, 100] > 3 * ratio[slope, 100]
    # the empty region: bright in 1/|grad|, dark in I/|grad|
    assert inverse[far, 100] >= 0.9 * inverse[on, 100]
    assert ratio[far, 100] < 0.2 * ratio[on, 100]
    with pytest.raises(ValueError, match="form"):
        P.minimum_gradient(data, [K, E], form="nonsense")
    with pytest.raises(ValueError, match="2-D"):
        P.minimum_gradient(np.zeros((4, 4, 4)), [K, E, E])


def test_an_intensity_that_fades_along_the_band_cancels():
    """A band 20 times weaker at one end: nearly as bright there in
    I/|grad I|, where the data and a second derivative lose it."""
    fading = _band(matrix=lambda e: np.exp(6.0 * (e + 0.05)))
    out = P.minimum_gradient(fading, [K, E], floor=0.01)
    weak, strong = 20, E.size - 25
    data_contrast = fading[:, weak].max() / fading[:, strong].max()
    picture_contrast = out[:, weak].max() / out[:, strong].max()
    assert data_contrast < 0.1 < 0.5 < picture_contrast
    second = P.derivative(fading, [K, E], 0, 2)
    assert second[:, weak].max() / second[:, strong].max() < 0.1


def test_the_floor_caps_flat_patches_and_nans_stay():
    data = _band()
    low = P.minimum_gradient(data, [K, E], form="inverse", floor=0.01)
    high = P.minimum_gradient(data, [K, E], form="inverse", floor=0.5)
    assert np.nanmax(low) == pytest.approx(50 * np.nanmax(high), rel=1e-6)
    assert np.isfinite(low).all()
    flat = P.minimum_gradient(np.ones((30, 30)), [K[:30], E[:30]])
    assert np.isfinite(flat).all()                 # no division by zero
    holed = data.copy()
    holed[:20, :15] = np.nan
    out = P.minimum_gradient(holed, [K, E])
    assert np.isnan(out[:20, :15]).all() and np.isfinite(out[40:, 40:]).all()


def test_it_does_not_depend_on_the_units_of_the_axes_or_the_counts():
    data = _band()
    reference = P.minimum_gradient(data, [K, E])
    rescaled = P.minimum_gradient(1e4 * data + 7.0, [K * 57.3, E * 1000.0])
    np.testing.assert_allclose(rescaled, reference, rtol=1e-6, atol=1e-9)
    # the anisotropy ratio is what changes the balance, on purpose
    assert not np.allclose(P.minimum_gradient(data, [K, E], ratio=5.0),
                           reference)


def test_it_follows_a_band_through_its_turning_point():
    """At the bottom of a parabola dE/dk = 0: the EDC peak is all there is
    and an MDC second derivative shows two flanks there, not the bottom."""
    bottom = -0.3
    kk, ee = np.meshgrid(K, E, indexing="ij")
    values = 1.0 / (1.0 + ((ee - (bottom + 2.0 * kk ** 2)) / 0.03) ** 2) + 0.02
    out = P.minimum_gradient(values, [K, E])
    centre = np.argmin(np.abs(K))
    assert E[np.nanargmax(out[centre])] == pytest.approx(bottom, abs=0.01)
    side = np.argmin(np.abs(K - 0.3))
    assert E[np.nanargmax(out[side])] == pytest.approx(bottom + 2 * 0.09,
                                                       abs=0.01)


def test_noise_costs_less_than_in_a_second_derivative():
    """Signal to noise of the band in the picture, off the same smoothed
    data: first derivatives against second ones."""
    def contrast(picture):
        on = np.array([picture[np.argmin(np.abs(K - (0.25 + 0.5 * E[j]))), j]
                       for j in ROWS])
        empty = picture[:60, 30:-30]
        return (np.mean(on) - np.mean(empty)) / np.std(empty)

    scores = {"gradient": [], "second": []}
    for seed in range(3):
        noisy = P.gaussian_smooth(_band(noise=0.05, seed=seed), [K, E],
                                  (0.01, 0.005))
        scores["gradient"].append(contrast(P.minimum_gradient(noisy, [K, E])))
        scores["second"].append(contrast(P.derivative(noisy, [K, E], 0, 2)))
    assert np.mean(scores["gradient"]) > np.mean(scores["second"])


def test_the_old_name_is_the_ratio_form():
    data = _band()
    np.testing.assert_array_equal(P.gradient_enhance(data, [K, E]),
                                  P.minimum_gradient(data, [K, E]))
