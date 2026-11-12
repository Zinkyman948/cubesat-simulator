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


Vector3 = tuple[float, float, float]


def _check_direction(v: Vector3 | None, what: str) -> None:
    if v is not None and sum(c * c for c in v) < 1e-12:
        raise ValueError(f"{what} must be a non-zero vector")


class Attitude(_Model):
    """How the spacecraft body frame is oriented.

    - nadir: +Z toward Earth's center, +X along the velocity, +Y opposite the
      orbit normal (the usual LVLH frame).
    - sun: +Z toward the Sun, +X as close as possible to the orbit normal.
    - inertial: +Z fixed along `pointing` (GCRS), +X as close as possible to GCRS +X.
    - spin: +Z fixed along `spin_axis` (GCRS), spinning about it at
      `spin_rate_deg_s` (starting from the inertial orientation at the
      simulation start).
    - target: +Z toward the highest ground station that is above its
      elevation mask, +X as close as possible to the velocity; nadir when
      no station is visible.
    """

    mode: Literal["nadir", "sun", "inertial", "spin", "target"] = "nadir"
    pointing: Vector3 | None = None
    spin_axis: Vector3 | None = None
    spin_rate_deg_s: float | None = None

    @model_validator(mode="after")
    def _check_mode(self):
        if self.mode == "inertial" and self.pointing is None:
            raise ValueError("inertial attitude needs pointing: [x, y, z]")
        if self.mode == "spin" and (self.spin_axis is None or self.spin_rate_deg_s is None):
            raise ValueError("spin attitude needs spin_axis: [x, y, z] and spin_rate_deg_s")
        _check_direction(self.pointing, "pointing")
        _check_direction(self.spin_axis, "spin_axis")
        return self


class Spacecraft(_Model):
    name: str
    form_factor: Literal["1U", "1.5U", "2U", "3U", "6U", "12U", "16U"] = "3U"
    mass_kg: float = Field(default=4.0, gt=0)
    attitude: Attitude = Attitude()


class GroundStationConfig(_Model):
    name: str
    latitude_deg: float = Field(ge=-90.0, le=90.0)
    longitude_deg: float = Field(ge=-180.0, le=180.0)
    altitude_m: float = 0.0
    min_elevation_deg: float = Field(default=10.0, ge=0.0, lt=90.0)


# 10 log10(2): the peak of a cos^0 (hemispherical) pattern, the broadest patch.
MIN_COSINE_GAIN_DBI = 3.0103


class Antenna(_Model):
    """An antenna and its radiation pattern.

    Patterns (`pattern`, inferred when omitted: dish if a diameter is given,
    otherwise isotropic):
    - isotropic: `gain_dbi` in every direction.
    - cosine: patch-like, peak `gain_dbi` along `axis`, falling as cos^n.
    - turnstile: crossed dipoles, 1.76 dBi along `axis`, -1.25 dBi broadside.
    - dipole: half-wave dipole with its element along `axis`; 2.15 dBi peak.
    - dish: circular aperture of `dish_diameter_m`, peak along `axis`.

    `axis` is a direction in the spacecraft body frame. Ground antennas are
    assumed to track the spacecraft, so only their peak gain matters.
    """

    pattern: Literal["isotropic", "cosine", "turnstile", "dipole", "dish"] | None = None
    gain_dbi: float | None = None
    dish_diameter_m: float | None = Field(default=None, gt=0)
    dish_efficiency: float = Field(default=0.55, gt=0, le=1)
    axis: Vector3 = (0.0, 0.0, 1.0)

    @model_validator(mode="after")
    def _check_kind(self):
        if self.pattern is None:
            self.pattern = "dish" if self.dish_diameter_m is not None else "isotropic"
        needs_gain = self.pattern in ("isotropic", "cosine")
        if needs_gain != (self.gain_dbi is not None):
            raise ValueError(
                f"{self.pattern} antenna "
                + ("needs gain_dbi" if needs_gain else "has a fixed gain; remove gain_dbi")
            )
        if (self.pattern == "dish") != (self.dish_diameter_m is not None):
            raise ValueError(
                "dish antenna needs dish_diameter_m"
                if self.pattern == "dish"
                else f"dish_diameter_m only applies to dish antennas, not {self.pattern}"
            )
        if self.pattern == "cosine" and self.gain_dbi < MIN_COSINE_GAIN_DBI:
            raise ValueError(f"cosine (patch) gain must be at least {MIN_COSINE_GAIN_DBI} dBi")
        _check_direction(self.axis, "axis")
        return self


class Transmitter(_Model):
    power_w: float = Field(gt=0)
    line_loss_db: float = Field(default=0.0, ge=0)
    antenna: Antenna


class Receiver(_Model):
    """Receiver noise, referred to the antenna terminals.

    Give either `system_noise_temp_k` directly (already including line
    losses), or `antenna_noise_temp_k` + `noise_figure_db` + `line_loss_db`
    to have it computed. Typical antenna temperatures: ~290 K for a
    spacecraft antenna viewing Earth; 50-150 K for a ground dish at
    S/X-band; several hundred K at UHF due to galactic and man-made noise.
    """

    antenna: Antenna
    system_noise_temp_k: float | None = Field(default=None, gt=0)
    antenna_noise_temp_k: float | None = Field(default=None, ge=0)
    noise_figure_db: float | None = Field(default=None, ge=0)
    line_loss_db: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _check_noise(self):
        direct = self.system_noise_temp_k is not None
        computed = self.antenna_noise_temp_k is not None and self.noise_figure_db is not None
        if direct == computed:
            raise ValueError(
                "receiver needs either system_noise_temp_k, or both "
                "antenna_noise_temp_k and noise_figure_db"
            )
        if direct and self.line_loss_db:
            raise ValueError("line_loss_db is already included in system_noise_temp_k")
        return self


class Coding(_Model):
    """Forward error correction, modeled as a gain over uncoded operation.

    Typical gains at BER 1e-5: convolutional r=1/2 K=7 (soft) ~5 dB;
    RS(255,223) + conv r=1/2 ~7 dB; CCSDS LDPC r=1/2 ~8-9 dB.
    """

    gain_db: float = Field(default=0.0, ge=0)
    rate: float = Field(default=1.0, gt=0, le=1)


class Losses(_Model):
    polarization_db: float = Field(default=0.0, ge=0)
    pointing_db: float = Field(default=0.0, ge=0)
    implementation_db: float = Field(default=1.0, ge=0)
    # Extra loss at zenith, scaled by slant path (e.g. a radome or wet
    # antenna). Added on top of the scenario's atmosphere model.
    atmospheric_zenith_db: float = Field(default=0.0, ge=0)


class LinkConfig(_Model):
    name: str
    direction: Literal["downlink", "uplink"]
    frequency_mhz: float = Field(gt=0)
    data_rate_bps: float = Field(gt=0)
    modulation: Literal["bpsk", "qpsk", "8psk", "bfsk_coherent", "bfsk_noncoherent", "gmsk"]
    coding: Coding = Coding()
    target_ber: float = Field(default=1e-5, ge=1e-12, lt=0.5)
    transmitter: Transmitter
    receiver: Receiver
    losses: Losses = Losses()
    stations: list[str] | None = None  # default: every ground station

    @property
    def frequency_hz(self) -> float:
        return self.frequency_mhz * 1e6

    @property
    def spacecraft_antenna(self) -> Antenna:
        return self.transmitter.antenna if self.direction == "downlink" else self.receiver.antenna

    @property
    def ground_antenna(self) -> Antenna:
        return self.receiver.antenna if self.direction == "downlink" else self.transmitter.antenna


class AtmosphereConfig(_Model):
    """Tropospheric propagation model for all links.

    - itu-r: gas, cloud, rain and scintillation from the ITU-R models at each
      ground station, not exceeded for `availability_percent` of the year.
    - none: free space only (plus any per-link atmospheric_zenith_db).
    """

    model: Literal["itu-r", "none"] = "itu-r"
    # 99 % is a common CubeSat design point; the rain model covers 95-99.999 %.
    availability_percent: float = Field(default=99.0, ge=95.0, le=99.999)

    @property
    def exceedance_percent(self) -> float:
        return 100.0 - self.availability_percent


class SimulationConfig(_Model):
    start: datetime
    duration_hours: float = Field(gt=0, le=24 * 30)
    step_seconds: float = Field(default=30.0, gt=0, le=600)
    # Sampling step for link time series within each pass.
    link_step_seconds: float = Field(default=5.0, gt=0, le=60)

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
    links: list[LinkConfig] = []
    atmosphere: AtmosphereConfig = AtmosphereConfig()

    @model_validator(mode="after")
    def _check_propagator(self):
        is_tle = self.orbit.type == "tle"
        if is_tle != (self.propagator == "sgp4"):
            raise ValueError("TLE orbits require propagator 'sgp4', and 'sgp4' requires a TLE orbit")
        names = [gs.name for gs in self.ground_stations]
        if len(set(names)) != len(names):
            raise ValueError("ground station names must be unique")
        link_names = [link.name for link in self.links]
        if len(set(link_names)) != len(link_names):
            raise ValueError("link names must be unique")
        for link in self.links:
            unknown = set(link.stations or []) - set(names)
            if unknown:
                raise ValueError(f"link '{link.name}' references unknown stations: {sorted(unknown)}")
        return self

    def link_stations(self, link: LinkConfig) -> list[GroundStationConfig]:
        if link.stations is None:
            return list(self.ground_stations)
        return [gs for gs in self.ground_stations if gs.name in link.stations]
