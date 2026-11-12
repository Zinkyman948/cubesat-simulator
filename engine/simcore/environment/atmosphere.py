"""Tropospheric attenuation from the ITU-R models (via ITU-Rpy).

Uses ITU-R P.618 for the slant path: gaseous absorption (P.676), cloud
(P.840), rain (P.837/P.838/P.839) and tropospheric scintillation, combined
as A = A_gas + sqrt((A_rain + A_cloud)^2 + A_scint^2), all exceeded for
`exceedance_percent` of an average year at the station's location (the
ITU climate maps supply rain rate, water vapour, temperature and cloud
liquid water).

Validity: the ITU-R models cover 1-55 GHz (rain) and elevations of 5 deg or
more. Below 1 GHz the tropospheric terms are a small fraction of a dB and
are evaluated as is; below 5 deg the models are extrapolated.
"""

from __future__ import annotations

import threading
import warnings
from dataclasses import dataclass

import numpy as np

# Mean radiating temperature of rain and cloud for sky-noise estimates (P.618).
MEAN_RADIATING_TEMP_K = 275.0

# ITU-Rpy fills its climate-map caches lazily without locking; concurrent
# first calls (e.g. the server's warm-up and a request) can see half-filled
# caches. Serialize all calls into it.
_ITUR_LOCK = threading.Lock()


@dataclass
class AtmosphericLoss:
    gas_db: np.ndarray
    cloud_db: np.ndarray
    rain_db: np.ndarray
    scintillation_db: np.ndarray
    total_db: np.ndarray
    # Rise in a ground antenna's noise temperature from rain and cloud
    # (clear-sky gaseous emission is assumed to be in its noise temperature).
    sky_noise_k: np.ndarray


def _itur():
    # Imported lazily: loading ITU-Rpy and its climate maps takes seconds.
    import astropy.units as u
    import itur

    return itur, u


def warm_up() -> None:
    """Load the ITU climate maps ahead of the first simulation."""
    SlantPathAtmosphere(0.0, 0.0, 0.0, 2e9, 1.0, 1.0, 0.5, 10.0)


class SlantPathAtmosphere:
    """Attenuation versus elevation for one station and frequency.

    Computed once on an elevation grid (dense near the horizon, where it
    changes fastest) and interpolated per sample.
    """

    def __init__(
        self,
        latitude_deg: float,
        longitude_deg: float,
        altitude_km: float,
        frequency_hz: float,
        exceedance_percent: float,
        antenna_diameter_m: float,
        antenna_efficiency: float,
        min_elevation_deg: float,
    ):
        itur, u = _itur()
        low = max(0.5, min_elevation_deg - 0.5)
        self.grid = np.unique(np.concatenate([np.arange(low, 10.0, 0.25), np.arange(10.0, 90.0, 1.0), [90.0]]))
        with _ITUR_LOCK, warnings.catch_warnings():
            # ITU-Rpy warns on every call below 5 deg; that range is documented above.
            warnings.simplefilter("ignore", RuntimeWarning)
            parts = itur.atmospheric_attenuation_slant_path(
                latitude_deg,
                longitude_deg,
                frequency_hz / 1e9 * u.GHz,
                self.grid,
                exceedance_percent,
                antenna_diameter_m * u.m,
                hs=max(altitude_km, 0.0) * u.km,
                eta=antenna_efficiency,
                return_contributions=True,
            )
        self.gas, self.cloud, self.rain, self.scint, self.total = (
            np.broadcast_to(np.asarray(p.value, dtype=float), self.grid.shape) for p in parts
        )

    def at(self, elevation_deg) -> AtmosphericLoss:
        el = np.clip(np.asarray(elevation_deg, dtype=float), self.grid[0], 90.0)

        def interp(values):
            return np.interp(el, self.grid, values)

        rain, cloud = interp(self.rain), interp(self.cloud)
        return AtmosphericLoss(
            gas_db=interp(self.gas),
            cloud_db=cloud,
            rain_db=rain,
            scintillation_db=interp(self.scint),
            total_db=interp(self.total),
            sky_noise_k=MEAN_RADIATING_TEMP_K * (1.0 - 10.0 ** (-(rain + cloud) / 10.0)),
        )
