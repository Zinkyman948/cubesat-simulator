"""Antenna radiation patterns.

Every pattern here is rotationally symmetric about the antenna `axis`, so
gain depends only on the angle theta between the axis and the direction of
interest. Gains are directivities in dBi (ohmic losses belong in the line
losses).
"""

from __future__ import annotations

import numpy as np
from scipy.special import j1

from simcore.link.rf import db, dish_gain_dbi, wavelength_m
from simcore.scenario.models import Antenna

TURNSTILE_PEAK_DBI = float(db(1.5))  # 1.76 dBi
DIPOLE_PEAK_DBI = float(db(1.641))  # 2.15 dBi
# Back-lobe level of directional antennas (cosine, dish), after the
# ITU-R S.465 reference envelope.
BACK_LOBE_DBI = -10.0
# Depth of a dipole's nulls along its element; real spacecraft fill them in
# through the structure and feed lines.
DIPOLE_NULL_DBI = -20.0


def peak_gain_dbi(antenna: Antenna, frequency_hz: float) -> float:
    if antenna.pattern in ("isotropic", "cosine"):
        return float(antenna.gain_dbi)
    if antenna.pattern == "turnstile":
        return TURNSTILE_PEAK_DBI
    if antenna.pattern == "dipole":
        return DIPOLE_PEAK_DBI
    return float(dish_gain_dbi(antenna.dish_diameter_m, antenna.dish_efficiency, frequency_hz))


def unit_axis(antenna: Antenna) -> np.ndarray:
    axis = np.asarray(antenna.axis, dtype=float)
    return axis / np.linalg.norm(axis)


def gain_dbi(antenna: Antenna, frequency_hz: float, cos_theta) -> np.ndarray:
    """Gain toward directions at angle theta from the antenna axis."""
    c = np.clip(np.asarray(cos_theta, dtype=float), -1.0, 1.0)
    pattern = antenna.pattern
    peak = peak_gain_dbi(antenna, frequency_hz)

    if pattern == "isotropic":
        return np.full_like(c, peak)

    if pattern == "turnstile":
        # Two crossed short dipoles fed in quadrature: D = 3/4 (1 + cos^2 theta).
        return db(0.75 * (1.0 + c**2))

    if pattern == "dipole":
        s = np.sqrt(1.0 - c**2)
        with np.errstate(divide="ignore", invalid="ignore"):
            d = 1.641 * (np.cos(np.pi / 2 * c) / s) ** 2
            g = db(d)
        return np.where(s > 1e-6, np.maximum(g, DIPOLE_NULL_DBI), DIPOLE_NULL_DBI)

    if pattern == "cosine":
        # G0 cos^n(theta) over the front hemisphere; normalization gives G0 = 2 (n + 1).
        n = 10.0 ** (peak / 10.0) / 2.0 - 1.0
        with np.errstate(divide="ignore"):
            g = np.where(c > 0, peak + 10.0 * n * np.log10(np.where(c > 0, c, 1.0)), -np.inf)
        return np.maximum(g, BACK_LOBE_DBI)

    # dish: uniformly illuminated circular aperture, [2 J1(x) / x]^2 with
    # x = (pi D / lambda) sin(theta), scaled to the efficiency-reduced peak.
    x = np.pi * antenna.dish_diameter_m / wavelength_m(frequency_hz) * np.sqrt(1.0 - c**2)
    with np.errstate(divide="ignore", invalid="ignore"):
        airy = np.where(x > 1e-9, (2.0 * j1(x) / x) ** 2, 1.0)
        g = peak + db(airy)
    return np.where(c > 0, np.maximum(g, BACK_LOBE_DBI), BACK_LOBE_DBI)
