import numpy as np
import pytest

from simcore.constants import J2, MU_EARTH, R_EARTH
from simcore.orbit.elements import KeplerianElements, cartesian_to_keplerian, keplerian_to_cartesian
from simcore.orbit.propagators import J2Propagator, SGP4Propagator, TwoBodyPropagator
from simcore.timeutil import offset, timescale

from conftest import ISS_LINE1, ISS_LINE2

TS = timescale()
EPOCH = TS.utc(2026, 11, 11)
SSO = KeplerianElements(a=R_EARTH + 500.0, e=0.001, i=np.radians(97.4), raan=0.8, argp=0.3, nu=0.0)


def test_two_body_returns_after_one_period():
    prop = TwoBodyPropagator(SSO, EPOCH)
    r0, v0 = prop.state(EPOCH)
    r1, v1 = prop.state(offset(EPOCH, SSO.period()))
    assert np.allclose(r1, r0, atol=1e-6)
    assert np.allclose(v1, v0, atol=1e-9)


def test_two_body_conserves_energy_and_momentum():
    prop = TwoBodyPropagator(KeplerianElements(9000.0, 0.2, 1.0, 0.5, 1.5, 0.0), EPOCH)
    r, v = prop.state(offset(EPOCH, np.linspace(0, 86400, 500)))
    energy = np.sum(v**2, axis=0) / 2 - MU_EARTH / np.linalg.norm(r, axis=0)
    h = np.cross(r, v, axis=0)
    assert np.ptp(energy) < 1e-9
    assert np.ptp(h, axis=1).max() < 1e-6


def _j2_energy(r, v, pole):
    r_mag = np.linalg.norm(r, axis=0)
    sin_lat = (pole @ r) / r_mag
    potential = -MU_EARTH / r_mag * (1 - J2 * (R_EARTH / r_mag) ** 2 * (3 * sin_lat**2 - 1) / 2)
    return np.sum(v**2, axis=0) / 2 + potential


def test_j2_conserves_energy_and_polar_angular_momentum():
    r0, v0 = keplerian_to_cartesian(SSO)
    prop = J2Propagator(r0, v0, EPOCH, EPOCH, offset(EPOCH, 3 * 86400))
    r, v = prop.state(offset(EPOCH, np.linspace(0, 3 * 86400, 2000)))
    energy = _j2_energy(r, v, prop.pole)
    h_pole = prop.pole @ np.cross(r, v, axis=0)
    assert np.ptp(energy) / abs(energy[0]) < 1e-10
    assert np.ptp(h_pole) / abs(h_pole[0]) < 1e-10


def test_j2_nodal_regression_matches_theory():
    """Sun-synchronous orbit: RAAN must drift ~ +0.9856 deg/day."""
    r0, v0 = keplerian_to_cartesian(SSO)
    days = 5
    prop = J2Propagator(r0, v0, EPOCH, EPOCH, offset(EPOCH, days * 86400), pole=[0, 0, 1])
    seconds = np.linspace(0, days * 86400, 3000)
    r, v = prop.state(offset(EPOCH, seconds))
    raan = np.unwrap([cartesian_to_keplerian(r[:, k], v[:, k]).raan for k in range(seconds.size)])
    measured = np.polyfit(seconds, raan, 1)[0]

    n = np.sqrt(MU_EARTH / SSO.a**3)
    p = SSO.a * (1 - SSO.e**2)
    expected = -1.5 * n * J2 * (R_EARTH / p) ** 2 * np.cos(SSO.i)
    assert measured == pytest.approx(expected, rel=5e-3)
    assert np.degrees(measured) * 86400 == pytest.approx(0.9856, abs=0.01)


def test_j2_forward_and_backward_from_mid_epoch():
    r0, v0 = keplerian_to_cartesian(SSO)
    start, end = offset(EPOCH, -3600.0), offset(EPOCH, 3600.0)
    prop = J2Propagator(r0, v0, EPOCH, start, end)
    r, v = prop.state(EPOCH)
    assert np.allclose(r, r0, atol=1e-9) and np.allclose(v, v0, atol=1e-12)
    r_b, _ = prop.state(start)
    r_f, _ = prop.state(end)
    assert r_b.shape == r_f.shape == (3,)
    with pytest.raises(ValueError):
        prop.state(offset(EPOCH, 7200.0))


def test_j2_stays_close_to_two_body_over_one_orbit():
    """J2 perturbation over one LEO orbit is tens of km, not thousands."""
    r0, v0 = keplerian_to_cartesian(SSO)
    t = offset(EPOCH, SSO.period())
    j2 = J2Propagator(r0, v0, EPOCH, EPOCH, t)
    diff = np.linalg.norm(j2.state(t)[0] - TwoBodyPropagator(SSO, EPOCH).state(t)[0])
    assert 1.0 < diff < 100.0


def test_sgp4_orbit_is_iss_like():
    prop = SGP4Propagator(ISS_LINE1, ISS_LINE2)
    r, v = prop.state(offset(prop.epoch, np.linspace(0, 86400, 200)))
    alt = np.linalg.norm(r, axis=0) - R_EARTH
    assert 380 < alt.min() and alt.max() < 440
    assert np.all(np.abs(np.linalg.norm(v, axis=0) - 7.66) < 0.05)
