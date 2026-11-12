"""Ground stations and topocentric look angles."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from simcore.frames import enu_matrix, geodetic_to_ecef


@dataclass
class LookAngles:
    azimuth: np.ndarray  # rad, clockwise from true north
    elevation: np.ndarray  # rad above the local horizon (geodetic)
    range_km: np.ndarray
    range_rate_km_s: np.ndarray  # positive when receding


@dataclass
class GroundStation:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0
    min_elevation_deg: float = 10.0

    ecef: np.ndarray = field(init=False, repr=False)
    _enu: np.ndarray = field(init=False, repr=False)

    def __post_init__(self):
        lat = np.radians(self.latitude_deg)
        lon = np.radians(self.longitude_deg)
        self.ecef = geodetic_to_ecef(lat, lon, self.altitude_m / 1000.0)
        self._enu = enu_matrix(lat, lon)

    @property
    def min_elevation(self) -> float:
        return np.radians(self.min_elevation_deg)

    def look_angles(self, r_ecef: np.ndarray, v_ecef: np.ndarray) -> LookAngles:
        """Look angles to a satellite given its Earth-fixed state.

        Elevation is purely geometric (no refraction correction).
        """
        rho = r_ecef - (self.ecef if r_ecef.ndim == 1 else self.ecef[:, None])
        east, north, up = self._enu @ rho
        rng = np.sqrt(east**2 + north**2 + up**2)
        return LookAngles(
            azimuth=np.mod(np.arctan2(east, north), 2.0 * np.pi),
            elevation=np.arcsin(up / rng),
            range_km=rng,
            range_rate_km_s=np.sum(rho * v_ecef, axis=0) / rng,
        )
