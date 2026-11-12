"""Thermospheric density from NRLMSIS 2.1 (via pymsis), and the solar and
geomagnetic activity that drives it."""

from __future__ import annotations

import numpy as np

from simcore.constants import OMEGA_EARTH
from simcore.frames import ecef_to_geodetic
from simcore.scenario.models import SOLAR_ACTIVITY_PRESETS, DragConfig

# Rough solar cycle for multi-year runs: F10.7 swings between these values
# with an 11-year period, minimum at 2019.9 (the start of cycle 25).
CYCLE_MIN_F107, CYCLE_MAX_F107 = 70.0, 180.0
CYCLE_MIN_YEAR, CYCLE_PERIOD_YEARS = 2019.9, 11.0
UNIX_EPOCH_JD = 2440587.5


def decimal_year(jd: np.ndarray) -> np.ndarray:
    return 2000.0 + (np.asarray(jd) - 2451545.0) / 365.25


def solar_indices(config: DragConfig, jd: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """F10.7 (used for both daily and 81-day mean) and Ap at UTC Julian dates."""
    jd = np.atleast_1d(np.asarray(jd, dtype=float))
    if config.solar_activity == "custom":
        f107, ap = config.f107, config.ap
    elif config.solar_activity == "cycle":
        phase = 2 * np.pi * (decimal_year(jd) - CYCLE_MIN_YEAR) / CYCLE_PERIOD_YEARS
        f107 = CYCLE_MIN_F107 + (CYCLE_MAX_F107 - CYCLE_MIN_F107) * (1 - np.cos(phase)) / 2
        # Geomagnetic activity loosely follows the solar flux.
        ap = 5.0 + 0.1 * (f107 - CYCLE_MIN_F107)
        return f107, ap
    else:
        f107, ap = SOLAR_ACTIVITY_PRESETS[config.solar_activity]
    return np.full(jd.shape, float(f107)), np.full(jd.shape, float(ap))


def gmst_rad(jd_ut1: np.ndarray) -> np.ndarray:
    """Greenwich mean sidereal time (IAU 1982, low precision)."""
    d = np.asarray(jd_ut1) - 2451545.0
    return np.radians((280.46061837 + 360.98564736629 * d) % 360.0)


def inertial_to_geodetic(r_km: np.ndarray, jd_utc: np.ndarray):
    """Approximate geodetic latitude/longitude (deg) and altitude (km) from
    inertial positions, rotating by GMST only. Ample for density lookups."""
    r = np.asarray(r_km, dtype=float).reshape(3, -1)
    theta = gmst_rad(np.broadcast_to(jd_utc, r.shape[1:]))
    c, s = np.cos(theta), np.sin(theta)
    ecef = np.array([c * r[0] + s * r[1], -s * r[0] + c * r[1], r[2]])
    lat, lon, alt = ecef_to_geodetic(ecef)
    return np.degrees(lat), np.degrees(lon), alt


class DensityModel:
    def __init__(self, config: DragConfig):
        self.config = config

    def density(self, jd_utc, lat_deg, lon_deg, alt_km) -> np.ndarray:
        """Total mass density (kg/m^3)."""
        import pymsis

        jd = np.atleast_1d(np.asarray(jd_utc, dtype=float))
        lat, lon, alt = (np.broadcast_to(np.asarray(v, dtype=float), jd.shape) for v in (lat_deg, lon_deg, alt_km))
        f107, ap = solar_indices(self.config, jd)
        dates = ((jd - UNIX_EPOCH_JD) * 86400e3).astype("int64").astype("datetime64[ms]")
        out = pymsis.calculate(
            dates, lon.ravel(), lat.ravel(), alt.ravel(),
            f107s=f107.ravel(), f107as=f107.ravel(), aps=np.repeat(ap.ravel()[:, None], 7, axis=1),
            version=2.1,
        )
        rho = np.asarray(out)[..., 0].reshape(jd.shape)
        # MSIS returns NaN far above its range; there is effectively no drag there.
        return np.nan_to_num(rho, nan=0.0)


def drag_acceleration(r_km: np.ndarray, v_km_s: np.ndarray, rho: float, ballistic: float, pole: np.ndarray):
    """Drag acceleration (km/s^2) for a (3,) state, with the atmosphere
    co-rotating with the Earth about `pole`."""
    v_rel = (v_km_s - OMEGA_EARTH * np.cross(pole, r_km)) * 1000.0  # m/s
    speed = np.linalg.norm(v_rel)
    return -0.5 * rho * ballistic * speed * v_rel / 1000.0
