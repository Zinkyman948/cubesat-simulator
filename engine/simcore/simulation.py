"""Run a scenario end to end: build the propagator, sample the ephemeris,
predict passes for every ground station, and evaluate every link over
those passes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simcore.attitude import AttitudeModel, gcrs_axes_to_itrs
from simcore.frames import ecef_to_geodetic, gcrs_to_itrs
from simcore.link.analysis import LinkPass, analyze_pass
from simcore.link.budget import LinkModel
from simcore.orbit.elements import KeplerianElements, keplerian_to_cartesian
from simcore.orbit.propagators import J2Propagator, Propagator, SGP4Propagator, TwoBodyPropagator
from simcore.scenario.models import KeplerianOrbit, Scenario
from simcore.timeutil import from_datetime, offset, seconds_between
from simcore.visibility.groundstation import GroundStation
from simcore.visibility.passes import Pass, find_passes


@dataclass
class Ephemeris:
    seconds: np.ndarray  # TT seconds since simulation start
    utc: list[str]  # ISO 8601 timestamps
    r_gcrs_km: np.ndarray  # (3, N)
    v_gcrs_km_s: np.ndarray  # (3, N)
    latitude_deg: np.ndarray
    longitude_deg: np.ndarray
    altitude_km: np.ndarray
    # Spacecraft body axes in the Earth-fixed frame, (3, 3, N): columns X, Y, Z.
    body_axes_itrs: np.ndarray

    def to_dict(self) -> dict:
        axes = self.body_axes_itrs
        return {
            "seconds": self.seconds.tolist(),
            "utc": self.utc,
            "r_gcrs_km": self.r_gcrs_km.T.tolist(),
            "v_gcrs_km_s": self.v_gcrs_km_s.T.tolist(),
            "latitude_deg": self.latitude_deg.tolist(),
            "longitude_deg": self.longitude_deg.tolist(),
            "altitude_km": self.altitude_km.tolist(),
            "body_x_itrs": axes[:, 0, :].T.tolist(),
            "body_y_itrs": axes[:, 1, :].T.tolist(),
            "body_z_itrs": axes[:, 2, :].T.tolist(),
        }


@dataclass
class SimulationResult:
    scenario: Scenario
    ephemeris: Ephemeris
    passes: dict[str, list[Pass]]
    link_passes: list[LinkPass]

    def to_dict(self, include_ephemeris: bool = False) -> dict:
        out = {
            "scenario": self.scenario.model_dump(mode="json"),
            "passes": {name: [p.to_dict() for p in ps] for name, ps in self.passes.items()},
            "link_passes": [lp.to_dict() for lp in self.link_passes],
        }
        if include_ephemeris:
            out["ephemeris"] = self.ephemeris.to_dict()
        return out


def keplerian_elements(orbit: KeplerianOrbit) -> KeplerianElements:
    return KeplerianElements(
        a=orbit.semi_major_axis,
        e=orbit.eccentricity,
        i=np.radians(orbit.inclination_deg),
        raan=np.radians(orbit.raan_deg),
        argp=np.radians(orbit.arg_perigee_deg),
        nu=np.radians(orbit.true_anomaly_deg),
    )


def build_propagator(scenario: Scenario) -> Propagator:
    orbit = scenario.orbit
    if scenario.propagator == "sgp4":
        return SGP4Propagator(orbit.line1, orbit.line2, scenario.spacecraft.name)

    epoch = from_datetime(orbit.epoch or scenario.simulation.start)
    elements = keplerian_elements(orbit)
    if scenario.propagator == "two_body":
        return TwoBodyPropagator(elements, epoch)

    r0, v0 = keplerian_to_cartesian(elements)
    return J2Propagator(
        r0, v0, epoch,
        t_start=from_datetime(scenario.simulation.start),
        t_end=from_datetime(scenario.simulation.end),
    )


def build_stations(scenario: Scenario) -> dict[str, GroundStation]:
    return {cfg.name: GroundStation(**cfg.model_dump()) for cfg in scenario.ground_stations}


def build_attitude(scenario: Scenario, stations: dict[str, GroundStation]) -> AttitudeModel:
    return AttitudeModel(
        scenario.spacecraft.attitude,
        list(stations.values()),
        from_datetime(scenario.simulation.start),
    )


def compute_ephemeris(
    scenario: Scenario, propagator: Propagator, attitude: AttitudeModel | None = None
) -> Ephemeris:
    sim = scenario.simulation
    start = from_datetime(sim.start)
    total = float(seconds_between(start, from_datetime(sim.end)))
    seconds = np.append(np.arange(0.0, total, sim.step_seconds), total)
    times = offset(start, seconds)
    r, v = propagator.state(times)
    r_ecef, _ = gcrs_to_itrs(times, r, v)
    lat, lon, alt = ecef_to_geodetic(r_ecef)
    attitude = attitude or build_attitude(scenario, build_stations(scenario))
    return Ephemeris(
        seconds=seconds,
        utc=[t.isoformat() for t in times.utc_datetime()],
        r_gcrs_km=r,
        v_gcrs_km_s=v,
        latitude_deg=np.degrees(lat),
        longitude_deg=np.degrees(lon),
        altitude_km=alt,
        body_axes_itrs=gcrs_axes_to_itrs(times, attitude.axes(times, r, v)),
    )


def run(scenario: Scenario) -> SimulationResult:
    sim = scenario.simulation
    start = from_datetime(sim.start)
    end = from_datetime(sim.end)
    propagator = build_propagator(scenario)
    stations = build_stations(scenario)
    attitude = build_attitude(scenario, stations)
    ephemeris = compute_ephemeris(scenario, propagator, attitude)

    passes = {
        name: find_passes(propagator, station, start, end, sim.step_seconds)
        for name, station in stations.items()
    }

    link_passes = []
    for link in scenario.links:
        model = LinkModel(link)
        for cfg in scenario.link_stations(link):
            for k, p in enumerate(passes[cfg.name]):
                link_passes.append(
                    analyze_pass(
                        model, propagator, attitude, stations[cfg.name], start, p, k, sim.link_step_seconds
                    )
                )

    return SimulationResult(scenario=scenario, ephemeris=ephemeris, passes=passes, link_passes=link_passes)
