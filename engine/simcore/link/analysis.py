"""Evaluate links over predicted passes, and static link budget tables."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skyfield.timelib import Time

from simcore.link.budget import LinkModel, LinkSamples
from simcore.link.rf import BOLTZMANN_DBW, db, slant_range_km
from simcore.orbit.propagators import Propagator
from simcore.timeutil import from_datetime, offset, seconds_between
from simcore.visibility.groundstation import GroundStation
from simcore.visibility.passes import Pass, look_angles


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
    station: GroundStation,
    start: Time,
    pass_: Pass,
    pass_index: int,
    step_s: float,
) -> LinkPass:
    s_aos = float(seconds_between(start, from_datetime(pass_.aos)))
    s_los = float(seconds_between(start, from_datetime(pass_.los)))
    seconds = np.append(np.arange(s_aos, s_los, step_s), s_los)
    times = offset(start, seconds)
    angles = look_angles(propagator, station, times)
    samples = model.evaluate(angles.range_km, angles.range_rate_km_s, angles.elevation)

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
    model: LinkModel, altitude_km: float, station_alt_km: float, elevation_deg: float
) -> list[tuple[str, float, str]]:
    """Classic link budget line items at a single elevation angle."""
    cfg = model.config
    el = np.radians(elevation_deg)
    rng = float(slant_range_km(el, altitude_km, station_alt_km))
    s = model.evaluate(np.array([rng]), np.array([0.0]), np.array([el]))
    first = {k: float(np.asarray(v)[0]) for k, v in s.__dict__.items()}
    return [
        ("Frequency", cfg.frequency_mhz, "MHz"),
        ("Elevation", elevation_deg, "deg"),
        ("Slant range", rng, "km"),
        ("Transmit power", float(db(cfg.transmitter.power_w)), "dBW"),
        ("Transmit line loss", -cfg.transmitter.line_loss_db, "dB"),
        ("Transmit antenna gain", model.tx_antenna_gain_dbi, "dBi"),
        ("EIRP", model.eirp_dbw, "dBW"),
        ("Free-space path loss", -first["path_loss_db"], "dB"),
        ("Atmospheric loss", -first["atmospheric_loss_db"], "dB"),
        ("Polarization loss", -cfg.losses.polarization_db, "dB"),
        ("Pointing loss", -cfg.losses.pointing_db, "dB"),
        ("Receive antenna gain", model.rx_antenna_gain_dbi, "dBi"),
        ("Received power", first["received_power_dbm"], "dBm"),
        ("System noise temperature", model.system_noise_temp_k, "K"),
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
