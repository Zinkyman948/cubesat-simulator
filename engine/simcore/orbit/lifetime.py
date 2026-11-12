"""Orbit lifetime under atmospheric drag.

Years of decay can't be integrated orbit by orbit, so this follows the
orbit-averaged (secular) evolution instead. At each step the current orbit
is sampled at 72 points evenly spaced in time (mean anomaly); NRLMSIS gives
the density at each point (so day/night and latitude variations are
included); and Gauss's equations for an along-track drag force,

    da/dt = 2 a^2 v f / mu        de/dt = 2 (e + cos nu) f / v,
    f = -1/2 rho B F v^2,  F = (1 - omega_E r cos i / v)^2,

are averaged over the orbit. F accounts for the co-rotating atmosphere. J2
precesses the node and perigee. The step adapts so the semi-major axis
changes by at most `max_da_km` per step (and at most a day), and the run
ends when perigee falls below `reentry_altitude_km`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from simcore.constants import J2, MU_EARTH, OMEGA_EARTH, R_EARTH
from simcore.environment.density import DensityModel, inertial_to_geodetic, solar_indices
from simcore.orbit.elements import (
    eccentric_from_mean,
    perifocal_to_inertial,
    true_from_eccentric,
)
from simcore.scenario.models import DragConfig

MU_SI = MU_EARTH * 1e9  # m^3/s^2
SAMPLES_PER_ORBIT = 72


@dataclass
class MeanElements:
    a: float  # km
    e: float
    i: float  # rad
    raan: float  # rad
    argp: float  # rad


@dataclass
class LifetimeResult:
    start_jd: float
    days: np.ndarray
    perigee_km: np.ndarray
    apogee_km: np.ndarray
    f107: np.ndarray
    reentered: bool
    lifetime_days: float  # time to re-entry, or the span simulated if it didn't
    max_years: float
    reentry_altitude_km: float
    ballistic_coefficient: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "start_jd": self.start_jd,
            "days": self.days.tolist(),
            "perigee_km": self.perigee_km.tolist(),
            "apogee_km": self.apogee_km.tolist(),
            "f107": self.f107.tolist(),
            "reentered": bool(self.reentered),
            "lifetime_days": float(self.lifetime_days),
            "max_years": self.max_years,
            "reentry_altitude_km": self.reentry_altitude_km,
            "ballistic_coefficient": self.ballistic_coefficient,
            "notes": self.notes,
        }


def orbit_average_rates(
    el: MeanElements, jd: float, density: DensityModel, ballistic: float
) -> tuple[float, float]:
    """Orbit-averaged da/dt (km/s) and de/dt (1/s) from drag."""
    a_m = el.a * 1000.0
    n = np.sqrt(MU_SI / a_m**3)
    M = np.linspace(0.0, 2 * np.pi, SAMPLES_PER_ORBIT, endpoint=False)
    E = eccentric_from_mean(M, el.e)
    nu = true_from_eccentric(E, el.e)
    r_m = a_m * (1.0 - el.e * np.cos(E))
    v = np.sqrt(MU_SI * (2.0 / r_m - 1.0 / a_m))

    # Positions around the orbit, at the times the satellite reaches them.
    p_km = el.a * (1.0 - el.e**2)
    r_km = p_km / (1.0 + el.e * np.cos(nu))
    r_pf = np.array([r_km * np.cos(nu), r_km * np.sin(nu), np.zeros_like(nu)])
    r_inertial = perifocal_to_inertial(el.i, el.raan, el.argp) @ r_pf
    jd_samples = jd + M / n / 86400.0
    lat, lon, alt = inertial_to_geodetic(r_inertial, jd_samples)
    rho = density.density(jd_samples, lat, lon, alt)

    wind = (1.0 - OMEGA_EARTH * r_m * np.cos(el.i) / v) ** 2
    f = -0.5 * rho * ballistic * wind * v**2  # m/s^2, along track
    da_dt = np.mean(2.0 * a_m**2 * v * f / MU_SI) / 1000.0
    de_dt = np.mean(2.0 * (el.e + np.cos(nu)) * f / v)
    return float(da_dt), float(de_dt)


def j2_secular_rates(el: MeanElements) -> tuple[float, float]:
    """Secular node and perigee rates (rad/s) from J2."""
    n = np.sqrt(MU_EARTH / el.a**3)
    p = el.a * (1.0 - el.e**2)
    k = 1.5 * n * J2 * (R_EARTH / p) ** 2
    return -k * np.cos(el.i), k * (2.0 - 2.5 * np.sin(el.i) ** 2)


def estimate_lifetime(
    elements: MeanElements,
    start_jd: float,
    drag: DragConfig,
    ballistic_coefficient: float,
    max_years: float = 25.0,
    reentry_altitude_km: float = 120.0,
    max_da_km: float = 0.5,
) -> LifetimeResult:
    density = DensityModel(drag)
    el = MeanElements(**elements.__dict__)
    t_days = 0.0
    end_days = max_years * 365.25
    days, perigee, apogee = [0.0], [el.a * (1 - el.e) - R_EARTH], [el.a * (1 + el.e) - R_EARTH]
    reentered = perigee[0] <= reentry_altitude_km

    while not reentered and t_days < end_days:
        jd = start_jd + t_days
        da_dt, de_dt = orbit_average_rates(el, jd, density, ballistic_coefficient)
        period_s = 2 * np.pi * np.sqrt(el.a**3 / MU_EARTH)
        # At most max_da_km per step, at most a day, at least one orbit.
        dt = min(86400.0, max(period_s, max_da_km / max(abs(da_dt), 1e-12)))
        dt = min(dt, (end_days - t_days) * 86400.0)

        raan_dot, argp_dot = j2_secular_rates(el)
        el.a += da_dt * dt
        el.e = max(0.0, el.e + de_dt * dt)
        el.raan += raan_dot * dt
        el.argp += argp_dot * dt
        t_days += dt / 86400.0

        days.append(t_days)
        perigee.append(el.a * (1 - el.e) - R_EARTH)
        apogee.append(el.a * (1 + el.e) - R_EARTH)
        reentered = perigee[-1] <= reentry_altitude_km
        if reentered:
            # The last step overshoots: interpolate to the crossing itself.
            frac = (perigee[-2] - reentry_altitude_km) / (perigee[-2] - perigee[-1])
            for series in (days, perigee, apogee):
                series[-1] = series[-2] + frac * (series[-1] - series[-2])
            t_days = days[-1]

    days_arr = np.array(days)
    # Keep the output to a manageable size for charts (always keep the end).
    if days_arr.size > 2000:
        keep = np.unique(np.append(np.linspace(0, days_arr.size - 1, 2000).astype(int), days_arr.size - 1))
    else:
        keep = np.arange(days_arr.size)
    f107, _ = solar_indices(drag, start_jd + days_arr[keep])
    notes = []
    if not reentered:
        notes.append(f"Still in orbit after {max_years:g} years (the simulated span).")
    return LifetimeResult(
        start_jd=start_jd,
        days=days_arr[keep],
        perigee_km=np.array(perigee)[keep],
        apogee_km=np.array(apogee)[keep],
        f107=np.asarray(f107),
        reentered=bool(reentered),
        lifetime_days=float(t_days),
        max_years=max_years,
        reentry_altitude_km=reentry_altitude_km,
        ballistic_coefficient=ballistic_coefficient,
        notes=notes,
    )
