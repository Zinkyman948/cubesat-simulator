"""Reference frame conversions: GCRS (inertial), ITRS (Earth-fixed), geodetic.

GCRS -> ITRS uses skyfield's IAU 2000A precession-nutation and Earth
rotation model. Vectors are (3,) or (3, N); km and km/s.
"""

from __future__ import annotations

import numpy as np
from skyfield.framelib import itrs
from skyfield.functions import mxv
from skyfield.timelib import Time

from simcore.constants import OMEGA_EARTH, R_EARTH, WGS84_E2


def gcrs_to_itrs(t: Time, r: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rotate an inertial state into the Earth-fixed frame.

    The Earth-fixed velocity includes the transport term -omega x r.
    """
    R = itrs.rotation_at(t)
    r_ecef = mxv(R, r)
    v_rot = mxv(R, v)
    omega_cross_r = OMEGA_EARTH * np.array([-r_ecef[1], r_ecef[0], np.zeros_like(r_ecef[2])])
    return r_ecef, v_rot - omega_cross_r


def geodetic_to_ecef(lat: float, lon: float, alt_km: float) -> np.ndarray:
    """WGS84 geodetic latitude/longitude (rad) and height (km) to ECEF (km)."""
    sin_lat = np.sin(lat)
    N = R_EARTH / np.sqrt(1.0 - WGS84_E2 * sin_lat**2)
    return np.array(
        [
            (N + alt_km) * np.cos(lat) * np.cos(lon),
            (N + alt_km) * np.cos(lat) * np.sin(lon),
            (N * (1.0 - WGS84_E2) + alt_km) * sin_lat,
        ]
    )


def ecef_to_geodetic(r_ecef: np.ndarray, iterations: int = 6):
    """ECEF (km) to WGS84 geodetic latitude, longitude (rad) and height (km).

    Fixed-point iteration on latitude; converges to sub-millimetre in a few
    iterations for any LEO/MEO altitude.
    """
    x, y, z = r_ecef
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1.0 - WGS84_E2))
    for _ in range(iterations):
        N = R_EARTH / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
        alt = p / np.cos(lat) - N
        lat = np.arctan2(z, p * (1.0 - WGS84_E2 * N / (N + alt)))
    N = R_EARTH / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
    alt = p / np.cos(lat) - N
    return lat, lon, alt


def enu_matrix(lat: float, lon: float) -> np.ndarray:
    """Rotation from ECEF to local East-North-Up at a geodetic location."""
    sl, cl = np.sin(lat), np.cos(lat)
    so, co = np.sin(lon), np.cos(lon)
    return np.array(
        [
            [-so, co, 0.0],
            [-sl * co, -sl * so, cl],
            [cl * co, cl * so, sl],
        ]
    )
