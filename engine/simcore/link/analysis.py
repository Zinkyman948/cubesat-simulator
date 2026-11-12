"""Evaluate links over predicted passes, and static link budget tables."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skyfield.timelib import Time

from simcore.attitude import AttitudeModel, station_positions_gcrs
from simcore.environment.atmosphere import SlantPathAtmosphere
from simcore.frames import gcrs_to_itrs
from simcore.link.antenna import gain_dbi, peak_gain_dbi, unit_axis
from simcore.link.budget import LinkModel, LinkSamples
from simcore.link.rf import BOLTZMANN_DBW, db, slant_range_km, undb, wavelength_m
from simcore.scenario.models import AtmosphereConfig, GroundStationConfig, LinkConfig
from simcore.orbit.propagators import Propagator
from simcore.timeutil import from_datetime, offset, seconds_between
from simcore.visibility.groundstation import GroundStation
from simcore.visibility.passes import Pass


@dataclass
class LinkPass:
    link: str
    station: str
    pass_index: int  # index into that station's pass list
    seconds: np.ndarray  # TT seconds since simulation start
    utc: list[str]
    samples: LinkSamples
    doppler_rate_hz_s: np.ndarray
    max_abs_doppler_hz: float
    max_abs_doppler_rate_hz_s: float
    peak_margin_db: float
    link_closed_s: float  # time with margin >= 0
    data_volume_bits: float

    def to_dict(self, include_series: bool = True) -> dict:
        out = {
            "link": self.link,
            "station": self.station,
            "pass_index": self.pass_index,
            "max_abs_doppler_hz": self.max_abs_doppler_hz,
            "max_abs_doppler_rate_hz_s": self.max_abs_doppler_rate_hz_s,
            "peak_margin_db": self.peak_margin_db,
            "link_closed_s": self.link_closed_s,
            "data_volume_bits": self.data_volume_bits,
        }
        if include_series:
            out["series"] = {
                "seconds": self.seconds.tolist(),
                "utc": self.utc,
                "doppler_rate_hz_s": self.doppler_rate_hz_s.tolist(),
                **self.samples.to_dict(),
            }
        return out


# Aperture efficiency assumed for non-dish ground antennas when sizing them
# for scintillation (the P.618 default).
EQUIVALENT_APERTURE_EFFICIENCY = 0.5


def link_atmosphere(
    config: AtmosphereConfig, link: LinkConfig, station: GroundStationConfig
) -> SlantPathAtmosphere | None:
    """The tropospheric model for one link at one station (None if disabled)."""
    if config.model == "none":
        return None
    antenna = link.ground_antenna
    if antenna.pattern == "dish":
        diameter, efficiency = antenna.dish_diameter_m, antenna.dish_efficiency
    else:
        # Equivalent circular aperture with the same gain: D = (lambda/pi) sqrt(G/eta).
        efficiency = EQUIVALENT_APERTURE_EFFICIENCY
        gain = undb(peak_gain_dbi(antenna, link.frequency_hz))
        diameter = wavelength_m(link.frequency_hz) / np.pi * np.sqrt(gain / efficiency)
    return SlantPathAtmosphere(
        station.latitude_deg,
        station.longitude_deg,
        station.altitude_m / 1000.0,
        link.frequency_hz,
        config.exceedance_percent,
        float(diameter),
        efficiency,
        station.min_elevation_deg,
    )


def time_above_zero(t: np.ndarray, y: np.ndarray) -> float:
    """Total time a sampled signal spends >= 0, linearly interpolating crossings."""
    total = 0.0
    for t0, t1, y0, y1 in zip(t[:-1], t[1:], y[:-1], y[1:]):
        if y0 >= 0 and y1 >= 0:
            total += t1 - t0
        elif (y0 >= 0) != (y1 >= 0):
            frac = y0 / (y0 - y1)  # crossing point within the interval
            total += (t1 - t0) * (frac if y0 >= 0 else 1.0 - frac)
    return float(total)


def analyze_pass(
    model: LinkModel,
    propagator: Propagator,
    attitude: AttitudeModel,
    station: GroundStation,
    start: Time,
    pass_: Pass,
    pass_index: int,
    step_s: float,
    atmosphere: SlantPathAtmosphere | None = None,
) -> LinkPass:
    s_aos = float(seconds_between(start, from_datetime(pass_.aos)))
    s_los = float(seconds_between(start, from_datetime(pass_.los)))
    seconds = np.append(np.arange(s_aos, s_los, step_s), s_los)
    times = offset(start, seconds)

    r, v = propagator.state(times)
    angles = station.look_angles(*gcrs_to_itrs(times, r, v))

    # Spacecraft antenna gain: the line of sight to the station, measured
    # from the antenna axis as mounted on the (attitude-dependent) body.
    los = station_positions_gcrs(times, station) - r
    los /= np.linalg.norm(los, axis=0)
    sc_antenna = model.config.spacecraft_antenna
    axis_gcrs = np.einsum("ijn,j->in", attitude.axes(times, r, v), unit_axis(sc_antenna))
    cos_theta = np.clip(np.sum(axis_gcrs * los, axis=0), -1.0, 1.0)

    samples = model.evaluate(
        angles.range_km,
        angles.range_rate_km_s,
        angles.elevation,
        sc_gain_dbi=gain_dbi(sc_antenna, model.config.frequency_hz, cos_theta),
        sc_angle_deg=np.degrees(np.arccos(cos_theta)),
        atmosphere=atmosphere.at(np.degrees(angles.elevation)) if atmosphere else None,
    )

    doppler_rate = (
        np.gradient(samples.doppler_hz, seconds) if seconds.size > 1 else np.zeros_like(seconds)
    )
    closed = time_above_zero(seconds, samples.margin_db)
    return LinkPass(
        link=model.config.name,
        station=station.name,
        pass_index=pass_index,
        seconds=seconds,
        utc=[t.isoformat() for t in times.utc_datetime()],
        samples=samples,
        doppler_rate_hz_s=doppler_rate,
        max_abs_doppler_hz=float(np.max(np.abs(samples.doppler_hz))),
        max_abs_doppler_rate_hz_s=float(np.max(np.abs(doppler_rate))),
        peak_margin_db=float(np.max(samples.margin_db)),
        link_closed_s=closed,
        data_volume_bits=closed * model.config.data_rate_bps,
    )


def budget_table(
    model: LinkModel,
    altitude_km: float,
    station_alt_km: float,
    elevation_deg: float,
    atmosphere: SlantPathAtmosphere | None = None,
) -> list[tuple[str, float, str]]:
    """Classic link budget line items at a single elevation angle (peak antenna gains)."""
    cfg = model.config
    el = np.radians(elevation_deg)
    rng = float(slant_range_km(el, altitude_km, station_alt_km))
    atm = atmosphere.at(np.array([elevation_deg])) if atmosphere else None
    s = model.evaluate(np.array([rng]), np.array([0.0]), np.array([el]), atmosphere=atm)
    first = {k: float(np.asarray(v)[0]) for k, v in s.__dict__.items()}
    return [
        ("Frequency", cfg.frequency_mhz, "MHz"),
        ("Elevation", elevation_deg, "deg"),
        ("Slant range", rng, "km"),
        ("Transmit power", float(db(cfg.transmitter.power_w)), "dBW"),
        ("Transmit line loss", -cfg.transmitter.line_loss_db, "dB"),
        ("Transmit antenna gain (peak)", model.tx_antenna_gain_dbi, "dBi"),
        ("EIRP", model.eirp_dbw, "dBW"),
        ("Free-space path loss", -first["path_loss_db"], "dB"),
        ("Gaseous absorption", -first["gas_loss_db"], "dB"),
        ("Cloud attenuation", -first["cloud_loss_db"], "dB"),
        ("Rain attenuation", -first["rain_loss_db"], "dB"),
        ("Scintillation", -first["scintillation_db"], "dB"),
        ("Atmospheric loss (combined)", -first["atmospheric_loss_db"], "dB"),
        ("Polarization loss", -cfg.losses.polarization_db, "dB"),
        ("Pointing loss", -cfg.losses.pointing_db, "dB"),
        ("Receive antenna gain (peak)", model.rx_antenna_gain_dbi, "dBi"),
        ("Received power", first["received_power_dbm"], "dBm"),
        ("System noise temperature", first["system_noise_temp_k"], "K"),
        ("G/T", model.g_over_t_dbk, "dB/K"),
        ("Boltzmann constant", BOLTZMANN_DBW, "dBW/K/Hz"),
        ("C/N0", first["cn0_dbhz"], "dB-Hz"),
        ("Data rate", float(db(cfg.data_rate_bps)), "dB-Hz"),
        ("Implementation loss", -cfg.losses.implementation_db, "dB"),
        ("Eb/N0", first["ebn0_db"], "dB"),
        (f"Required Eb/N0 (uncoded, BER {cfg.target_ber:g})", model.uncoded_required_ebn0_db, "dB"),
        ("Coding gain", cfg.coding.gain_db, "dB"),
        ("Required Eb/N0", model.required_ebn0_db, "dB"),
        ("Link margin", first["margin_db"], "dB"),
    ]
