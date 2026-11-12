"""RF fundamentals. Powers in dB units, frequencies in Hz, distances in km."""

from __future__ import annotations

import numpy as np

from simcore.constants import R_EARTH

C_LIGHT_KM_S = 299792.458
BOLTZMANN_DBW = 10.0 * np.log10(1.380649e-23)  # dBW/K/Hz, about -228.6
T0_K = 290.0  # IEEE reference temperature for noise figure


def db(x):
    return 10.0 * np.log10(x)


def undb(x_db):
    return 10.0 ** (np.asarray(x_db) / 10.0)


def wavelength_m(frequency_hz: float) -> float:
    return C_LIGHT_KM_S * 1000.0 / frequency_hz


def free_space_path_loss_db(range_km, frequency_hz: float):
    """Friis free-space loss, 20 log10(4 pi d / lambda)."""
    return 20.0 * np.log10(4.0 * np.pi * np.asarray(range_km) * 1000.0 / wavelength_m(frequency_hz))


def dish_gain_dbi(diameter_m: float, efficiency: float, frequency_hz: float) -> float:
    """Peak gain of a circular aperture."""
    return db(efficiency * (np.pi * diameter_m / wavelength_m(frequency_hz)) ** 2)


def system_noise_temperature_k(antenna_temp_k: float, noise_figure_db: float, line_loss_db: float) -> float:
    """System noise temperature referred to the antenna terminals.

    Chain: antenna -> lossy line (at T0) -> LNA. Later stages are assumed
    negligible after the LNA's gain.
    """
    loss = undb(line_loss_db)
    t_lna = T0_K * (undb(noise_figure_db) - 1.0)
    return float(antenna_temp_k + T0_K * (loss - 1.0) + loss * t_lna)


def slant_range_km(elevation_rad, altitude_km: float, station_alt_km: float = 0.0):
    """Range from a station to a satellite at a given altitude (spherical Earth)."""
    rs = R_EARTH + station_alt_km
    rsat = R_EARTH + altitude_km
    sin_el = np.sin(elevation_rad)
    return np.sqrt(rsat**2 - (rs * np.cos(elevation_rad)) ** 2) - rs * sin_el


def atmospheric_path_factor(elevation_rad, shell_height_km: float = 8.0):
    """Slant-to-zenith path length ratio through a uniform spherical shell.

    Equal to 1/sin(el) at high elevation, but stays finite at the horizon
    (about 40 for an 8 km shell) instead of diverging. Negative elevations
    are treated as 0.
    """
    el = np.maximum(np.asarray(elevation_rad), 0.0)
    r = R_EARTH
    path = np.sqrt((r + shell_height_km) ** 2 - (r * np.cos(el)) ** 2) - r * np.sin(el)
    return path / shell_height_km


def doppler_shift_hz(range_rate_km_s, frequency_hz: float):
    """Received minus transmitted frequency; positive while approaching."""
    return -np.asarray(range_rate_km_s) / C_LIGHT_KM_S * frequency_hz
