"""Scenario schema: everything needed to define a simulation run.

Scenarios are written in YAML (see /scenarios) and validated here.
Angles are in degrees and distances in km in the file; the engine
converts to radians internally.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from simcore.constants import R_EARTH


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def tle_checksum(line: str) -> int:
    """TLE mod-10 checksum: digits count their value, '-' counts as 1."""
    return sum(int(c) if c.isdigit() else c == "-" for c in line[:68]) % 10


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KeplerianOrbit(_Model):
    """Osculating classical elements in the GCRS (J2000-aligned) frame.

    Give exactly one of `semi_major_axis_km` or `altitude_km` (the latter
    is height above the equatorial radius, a convenience for near-circular
    orbits).
    """

    type: Literal["keplerian"]
    epoch: datetime | None = None  # defaults to the simulation start
    semi_major_axis_km: float | None = Field(default=None, gt=0)
    altitude_km: float | None = Field(default=None, gt=0)
    eccentricity: float = Field(default=0.0, ge=0.0, lt=1.0)
    inclination_deg: float = Field(ge=0.0, le=180.0)
    raan_deg: float = 0.0
    arg_perigee_deg: float = 0.0
    true_anomaly_deg: float = 0.0

    @field_validator("epoch")
    @classmethod
    def _utc_epoch(cls, v: datetime | None) -> datetime | None:
        return None if v is None else _as_utc(v)

    @model_validator(mode="after")
    def _check_size(self):
        if (self.semi_major_axis_km is None) == (self.altitude_km is None):
            raise ValueError("give exactly one of semi_major_axis_km or altitude_km")
        perigee_alt = self.semi_major_axis * (1.0 - self.eccentricity) - R_EARTH
        if perigee_alt < 100.0:
            raise ValueError(f"perigee altitude {perigee_alt:.1f} km is below 100 km")
        return self

    @property
    def semi_major_axis(self) -> float:
        if self.semi_major_axis_km is not None:
            return self.semi_major_axis_km
        return R_EARTH + self.altitude_km


class TLEOrbit(_Model):
    """A NORAD two-line element set. Only valid with the sgp4 propagator."""

    type: Literal["tle"]
    line1: str
    line2: str

    @field_validator("line1", "line2")
    @classmethod
    def _check_line(cls, line: str, info) -> str:
        line = line.rstrip()
        number = "1" if info.field_name == "line1" else "2"
        if len(line) != 69 or not line.startswith(number + " "):
            raise ValueError(f"TLE line {number} must be 69 characters starting with '{number} '")
        if tle_checksum(line) != int(line[68]):
            raise ValueError(f"TLE line {number} checksum mismatch")
        return line


Orbit = Annotated[Union[KeplerianOrbit, TLEOrbit], Field(discriminator="type")]


class Spacecraft(_Model):
    name: str
    form_factor: Literal["1U", "1.5U", "2U", "3U", "6U", "12U", "16U"] = "3U"
    mass_kg: float = Field(default=4.0, gt=0)


class GroundStationConfig(_Model):
    name: str
    latitude_deg: float = Field(ge=-90.0, le=90.0)
    longitude_deg: float = Field(ge=-180.0, le=180.0)
    altitude_m: float = 0.0
    min_elevation_deg: float = Field(default=10.0, ge=0.0, lt=90.0)


class SimulationConfig(_Model):
    start: datetime
    duration_hours: float = Field(gt=0, le=24 * 30)
    step_seconds: float = Field(default=30.0, gt=0, le=600)

    @field_validator("start")
    @classmethod
    def _utc_start(cls, v: datetime) -> datetime:
        return _as_utc(v)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(hours=self.duration_hours)


class Scenario(_Model):
    name: str
    description: str = ""
    simulation: SimulationConfig
    spacecraft: Spacecraft
    orbit: Orbit
    propagator: Literal["two_body", "j2", "sgp4"]
    ground_stations: list[GroundStationConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_propagator(self):
        is_tle = self.orbit.type == "tle"
        if is_tle != (self.propagator == "sgp4"):
            raise ValueError("TLE orbits require propagator 'sgp4', and 'sgp4' requires a TLE orbit")
        names = [gs.name for gs in self.ground_stations]
        if len(set(names)) != len(names):
            raise ValueError("ground station names must be unique")
        return self
