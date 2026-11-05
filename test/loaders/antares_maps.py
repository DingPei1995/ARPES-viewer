"""A small ANTARES deflector map written the way the beamline writes one:
``/DeflX_0002/scan_data`` with ``actuator_1_1`` (the deflector), the scale
triplets ``data_01``-``data_06`` (one value per step) and the images in
``data_09`` (step, slit angle, energy) -- the layout of a real file whose
``h5info`` is in the Test-data repository. Every dataset is created at the
length the scan *planned*; a scan stopped early leaves the rest at the fill
value (zero) or, for the deflector readback, at ``unmeasured_axis``."""
import h5py
import numpy as np


def write_deflector_map(path, steps=12, measured=None, partial=None,
                        n_angle=20, n_energy=30, unmeasured_axis=0.0,
                        entry="DeflX_0002"):
    """``measured`` steps hold a full image; ``partial`` (a fraction) makes
    the last measured one that much of a full image, as when the scan
    stopped part-way through its sweeps."""
    measured = steps if measured is None else measured
    rng = np.random.default_rng(0)
    deflx = np.linspace(-6.0, 6.0, steps)
    images = np.zeros((steps, n_angle, n_energy), dtype=np.int32)
    energy = np.linspace(0.0, 1.0, n_energy)
    edge = 1.0 / (1.0 + np.exp((energy - 0.7) / 0.03))
    for i in range(measured):
        frame = 200.0 * edge[None, :] * (1.0 + 0.1 * rng.random((n_angle, 1)))
        if partial is not None and i == measured - 1:
            frame = frame * partial
        images[i] = np.round(frame).astype(np.int32)
    readback = deflx.copy()
    readback[measured:] = unmeasured_axis
    with h5py.File(path, "w") as f:
        sd = f.create_group(f"{entry}/scan_data")
        sd["actuator_1_1"] = readback
        for name, value in (("data_01", 100.0), ("data_02", 0.01),
                            ("data_03", 100.0 + 0.01 * (n_energy - 1)),
                            ("data_04", -10.0), ("data_05", 1.0),
                            ("data_06", -10.0 + (n_angle - 1))):
            column = np.full(steps, value)
            column[measured:] = 0.0
            sd[name] = column
        sd["data_09"] = images
    return path
