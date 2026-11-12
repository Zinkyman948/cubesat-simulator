"""Analytic Sun position.

Low-precision formula from the Astronomical Almanac (section C5): about
0.01 deg in ecliptic longitude between 1950 and 2050. It is referred to the
mean equinox of date, which differs from GCRS by precession (~0.36 deg in
2026). That is plenty for attitude and eclipse modeling, and needs no
ephemeris download.
"""

from __future__ import annotations

import numpy as np
from skyfield.timelib import Time

AU_KM = 149597870.7


def sun_position_km(t: Time) -> np.ndarray:
    """Geocentric Sun position (km), shaped (3,) or (3, N)."""
    n = (t.whole - 2451545.0) + t.tt_fraction  # days since J2000.0 (TT)
    L = np.radians(280.460 + 0.9856474 * n)  # mean longitude
    g = np.radians(357.528 + 0.9856003 * n)  # mean anomaly
    lam = L + np.radians(1.915) * np.sin(g) + np.radians(0.020) * np.sin(2 * g)
    eps = np.radians(23.439 - 0.0000004 * n)  # obliquity of the ecliptic
    r_au = 1.00014 - 0.01671 * np.cos(g) - 0.00014 * np.cos(2 * g)
    return AU_KM * r_au * np.array(
        [np.cos(lam), np.cos(eps) * np.sin(lam), np.sin(eps) * np.sin(lam)]
    )
