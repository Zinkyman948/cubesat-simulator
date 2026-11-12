import numpy as np
import pytest
from pydantic import ValidationError
from scipy.integrate import solve_ivp

from simcore.constants import MU_EARTH, OMEGA_EARTH, R_EARTH
from simcore.environment.density import DensityModel, drag_acceleration, inertial_to_geodetic, solar_indices
from simcore.orbit.elements import KeplerianElements, cartesian_to_keplerian, keplerian_to_cartesian
from simcore.orbit.lifetime import MeanElements, estimate_lifetime, orbit_average_rates
from simcore.orbit.propagators import J2Propagator, j2_acceleration
from simcore.scenario.models import DragConfig, Spacecraft
from simcore.timeutil import offset, timescale

TS = timescale()
EPOCH = TS.utc(2026, 11, 11)
B_3U = Spacecraft(name="x", form_factor="3U", mass_kg=4.0).ballistic_coefficient


class ConstantDensity(DensityModel):
    def __init__(self, rho):
        super().__init__(DragConfig())
        self.rho = rho

    def density(self, jd_utc, lat_deg, lon_deg, alt_km):
        return np.full(np.shape(np.atleast_1d(jd_utc)), self.rho)


def test_ballistic_coefficient_from_form_factor():
    sc = Spacecraft(name="x", form_factor="3U", mass_kg=4.0)
    # Tumbling average of a 10 x 10 x 34.05 cm box: surface area / 4.
    assert sc.effective_drag_area_m2 == pytest.approx((2 * 0.01 + 4 * 0.1 * 0.3405) / 4)
    assert sc.ballistic_coefficient == pytest.approx(2.2 * sc.effective_drag_area_m2 / 4.0)
    assert Spacecraft(name="x", drag_area_m2=0.05, mass_kg=5.0).ballistic_coefficient == pytest.approx(0.022)


def test_density_is_physical_and_follows_solar_activity():
    jd = 2461355.5  # 2026-11-11
    low, high = DensityModel(DragConfig(solar_activity="low")), DensityModel(DragConfig(solar_activity="high"))
    rho = [low.density(jd, 0, 0, alt)[0] for alt in (300, 400, 500)]
    assert 1e-12 < rho[0] < 1e-10 and rho[0] > rho[1] > rho[2]
    assert high.density(jd, 0, 0, 400)[0] > 5 * low.density(jd, 0, 0, 400)[0]


def test_solar_cycle_peaks_mid_cycle():
    config = DragConfig(solar_activity="cycle")
    jd = 2451545.0 + (np.array([2019.9, 2025.4, 2030.9]) - 2000.0) * 365.25
    f107, ap = solar_indices(config, jd)
    assert f107[0] == pytest.approx(70) and f107[1] == pytest.approx(180) and f107[2] == pytest.approx(70)
    assert ap[1] > ap[0]


def test_drag_opposes_motion_relative_to_the_atmosphere():
    r, v = keplerian_to_cartesian(KeplerianElements(R_EARTH + 400, 0.0, 0.9, 0, 0, 0))
    acc = drag_acceleration(r, v, 5e-12, B_3U, np.array([0.0, 0.0, 1.0]))
    v_rel = v - OMEGA_EARTH * np.cross([0, 0, 1.0], r)
    assert np.allclose(np.cross(acc, v_rel), 0, atol=1e-18) and np.dot(acc, v_rel) < 0


def test_orbit_average_matches_circular_decay_formula():
    """Constant density, circular polar orbit: da/dt = -B rho sqrt(mu a)
    (times the small co-rotation factor, which is 1 for i = 90 deg)."""
    a, rho = R_EARTH + 400.0, 4e-12
    el = MeanElements(a=a, e=0.0, i=np.pi / 2, raan=0.0, argp=0.0)
    da_dt, de_dt = orbit_average_rates(el, 2461355.5, ConstantDensity(rho), B_3U)
    expected = -B_3U * rho * np.sqrt(MU_EARTH * 1e9 * a * 1e3) / 1000.0
    assert da_dt == pytest.approx(expected, rel=1e-6)
    assert abs(de_dt) < 1e-15


def test_drag_eccentric_orbits_circularize():
    el = MeanElements(a=R_EARTH + 800.0, e=0.05, i=1.0, raan=0.0, argp=0.0)  # perigee ~430 km
    _, de_dt = orbit_average_rates(el, 2461355.5, DensityModel(DragConfig()), B_3U)
    assert de_dt < 0


def test_propagator_drag_matches_brute_force_integration():
    """Density sampling along the trajectory (iterated) vs calling NRLMSIS at
    every integrator step, over 6 hours at 350 km."""
    hours = 6
    r0, v0 = keplerian_to_cartesian(KeplerianElements(R_EARTH + 350, 0.001, np.radians(51.6), 1.0, 0.5, 0.0))
    density = DensityModel(DragConfig(solar_activity="high"))
    end = offset(EPOCH, hours * 3600.0)
    fast = J2Propagator(r0, v0, EPOCH, EPOCH, end, density=density, ballistic_coefficient=B_3U)
    pole = fast.pole

    def rhs(s, y):
        t = offset(EPOCH, s)
        lat, lon, alt = inertial_to_geodetic(y[:3], t.ut1)
        rho = density.density(t.ut1, lat, lon, alt)[0]
        return np.concatenate([y[3:], j2_acceleration(y[:3], pole) + drag_acceleration(y[:3], y[3:], rho, B_3U, pole)])

    brute = solve_ivp(rhs, (0, hours * 3600.0), np.concatenate([r0, v0]), method="DOP853", rtol=1e-10, atol=1e-8)
    drag_free = J2Propagator(r0, v0, EPOCH, EPOCH, end).state(end)[0]
    effect = np.linalg.norm(brute.y[:3, -1] - drag_free)
    error = np.linalg.norm(fast.state(end)[0] - brute.y[:3, -1])
    assert effect > 5.0  # drag matters over this span...
    assert error < 0.02 * effect  # ...and the fast method captures it


def test_lifetime_model_agrees_with_numerical_decay():
    """Orbit-averaged decay vs numerical drag propagation, 10 days at 350 km."""
    days = 10
    el0 = KeplerianElements(R_EARTH + 350, 0.0005, np.radians(97.0), 0.5, 0.0, 0.0)
    r0, v0 = keplerian_to_cartesian(el0)
    drag = DragConfig(solar_activity="moderate")
    end = offset(EPOCH, days * 86400.0)
    prop = J2Propagator(r0, v0, EPOCH, EPOCH, end, density=DensityModel(drag), ballistic_coefficient=B_3U)
    s = np.linspace(0, days * 86400.0, 4000)
    r, v = prop.state(offset(EPOCH, s))
    a = np.array([cartesian_to_keplerian(r[:, k], v[:, k]).a for k in range(s.size)])
    numerical_drop = np.polyval(np.polyfit(s, a, 2), 0) - np.polyval(np.polyfit(s, a, 2), s[-1])

    # Mean size at the start, as in simulation.mean_elements: the mean orbital
    # radius over the first orbit (not the averaged osculating a; see there).
    first_orbit = s < el0.period()
    mean_radius = float(np.linalg.norm(r[:, first_orbit], axis=0).mean())
    mean = MeanElements(a=mean_radius, e=0.0005, i=el0.i, raan=el0.raan, argp=0.0)
    result = estimate_lifetime(mean, float(EPOCH.ut1), drag, B_3U, max_years=days / 365.25)
    model_a = (result.perigee_km + result.apogee_km) / 2  # semi-major axis (as altitude)
    model_drop = model_a[0] - model_a[-1]
    assert numerical_drop > 5.0  # ~1 km/day at 350 km, moderate activity
    assert model_drop == pytest.approx(numerical_drop, rel=0.05)


def test_lifetimes_are_in_the_expected_range_for_a_3u():
    def years(alt, activity):
        el = MeanElements(a=R_EARTH + alt, e=0.0, i=np.radians(97.4), raan=0.0, argp=0.0)
        r = estimate_lifetime(el, 2461355.5, DragConfig(solar_activity=activity), B_3U, max_years=40)
        assert r.reentered
        return r.lifetime_days / 365.25

    # ISS-deployed 3U CubeSats (~400 km) typically last months to ~1.5 years.
    assert 0.2 < years(400, "moderate") < 2.0
    assert years(400, "low") > years(400, "moderate") > years(400, "high")
    assert years(500, "moderate") > 4 * years(400, "moderate")


def test_drag_requires_numerical_propagator():
    from simcore.scenario import Scenario

    base = {
        "name": "x",
        "simulation": {"start": "2026-11-11T00:00:00Z", "duration_hours": 1},
        "spacecraft": {"name": "x"},
        "orbit": {"type": "keplerian", "altitude_km": 400, "inclination_deg": 51.6},
        "ground_stations": [{"name": "A", "latitude_deg": 0, "longitude_deg": 0}],
        "drag": {"enabled": True},
    }
    Scenario.model_validate({**base, "propagator": "j2"})
    with pytest.raises(ValidationError, match="numerical propagator"):
        Scenario.model_validate({**base, "propagator": "two_body"})
    with pytest.raises(ValidationError, match="custom solar activity"):
        Scenario.model_validate({**base, "propagator": "j2", "drag": {"enabled": True, "solar_activity": "custom"}})


def test_reentry_ends_exactly_at_the_reentry_altitude():
    el = MeanElements(a=R_EARTH + 250.0, e=0.0, i=np.radians(51.6), raan=0.0, argp=0.0)
    result = estimate_lifetime(el, 2461355.5, DragConfig(solar_activity="high"), B_3U, max_years=1)
    assert result.reentered
    assert result.perigee_km[-1] == pytest.approx(120.0)
    assert result.lifetime_days == pytest.approx(result.days[-1])
