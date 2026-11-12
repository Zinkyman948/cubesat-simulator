"""Pass prediction: AOS / TCA / LOS above a station's elevation mask."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import brentq, minimize_scalar
from skyfield.timelib import Time

from simcore.frames import gcrs_to_itrs
from simcore.orbit.propagators import Propagator
from simcore.timeutil import offset, seconds_between
from simcore.visibility.groundstation import GroundStation, LookAngles

# Root and maximum refinement tolerance, seconds.
_TIME_TOL_S = 1e-3


@dataclass
class Pass:
    station: str
    aos: datetime  # acquisition of signal (rises above mask)
    tca: datetime  # time of closest approach / maximum elevation
    los: datetime  # loss of signal (sets below mask)
    duration_s: float
    max_elevation_deg: float
    aos_azimuth_deg: float
    los_azimuth_deg: float
    # True when the pass was already in progress at the scenario start,
    # or still in progress at the scenario end.
    truncated_start: bool = False
    truncated_end: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        for key in ("aos", "tca", "los"):
            d[key] = d[key].isoformat()
        return d


def look_angles(propagator: Propagator, station: GroundStation, t: Time) -> LookAngles:
    r, v = propagator.state(t)
    r_ecef, v_ecef = gcrs_to_itrs(t, r, v)
    return station.look_angles(r_ecef, v_ecef)


def find_passes(
    propagator: Propagator,
    station: GroundStation,
    start: Time,
    end: Time,
    step_s: float = 30.0,
) -> list[Pass]:
    """Find all passes between `start` and `end`.

    Elevation is sampled every `step_s` seconds and each mask crossing is
    refined with Brent's method to ~1 ms. Passes shorter than `step_s`
    that start and end between two samples can be missed, so keep the
    step well below the shortest pass of interest.
    """
    total = float(seconds_between(start, end))
    grid = np.append(np.arange(0.0, total, step_s), total)
    mask = station.min_elevation

    def height(s: float) -> float:
        return float(look_angles(propagator, station, offset(start, s)).elevation) - mask

    above = look_angles(propagator, station, offset(start, grid)).elevation > mask
    changes = np.flatnonzero(above[1:] != above[:-1])
    crossings = [brentq(height, grid[k], grid[k + 1], xtol=_TIME_TOL_S) for k in changes]

    # Pair rise/set crossings, closing passes open at either boundary.
    rises = ([0.0] if above[0] else []) + [c for c, k in zip(crossings, changes) if not above[k]]
    sets = [c for c, k in zip(crossings, changes) if above[k]] + ([total] if above[-1] else [])

    return [
        _build_pass(propagator, station, start, s_aos, s_los, s_aos == 0.0 and above[0],
                    s_los == total and above[-1])
        for s_aos, s_los in zip(rises, sets)
    ]


def _build_pass(propagator, station, start, s_aos, s_los, truncated_start, truncated_end) -> Pass:
    def neg_elevation(s: float) -> float:
        return -float(look_angles(propagator, station, offset(start, s)).elevation)

    s_tca = minimize_scalar(
        neg_elevation, bounds=(s_aos, s_los), method="bounded",
        options={"xatol": _TIME_TOL_S},
    ).x

    times = offset(start, np.array([s_aos, s_tca, s_los]))
    angles = look_angles(propagator, station, times)
    aos, tca, los = times.utc_datetime()
    return Pass(
        station=station.name,
        aos=aos,
        tca=tca,
        los=los,
        duration_s=float(s_los - s_aos),
        max_elevation_deg=float(np.degrees(angles.elevation[1])),
        aos_azimuth_deg=float(np.degrees(angles.azimuth[0])),
        los_azimuth_deg=float(np.degrees(angles.azimuth[2])),
        truncated_start=bool(truncated_start),
        truncated_end=bool(truncated_end),
    )
