import numpy as np
import pytest

from simcore.constants import MU_EARTH
from simcore.orbit.elements import (
    KeplerianElements,
    cartesian_to_keplerian,
    eccentric_from_mean,
    eccentric_from_true,
    keplerian_to_cartesian,
    mean_from_eccentric,
    true_from_eccentric,
)


@pytest.mark.parametrize("e", [0.0, 0.001, 0.1, 0.5, 0.9, 0.99])
def test_kepler_equation_solution(e):
    M = np.linspace(0, 2 * np.pi, 361, endpoint=False)
    E = eccentric_from_mean(M, e)
    assert np.allclose(mean_from_eccentric(E, e), M, atol=1e-12)


@pytest.mark.parametrize("e", [0.0, 0.3, 0.8])
def test_anomaly_round_trip(e):
    nu = np.linspace(-np.pi + 0.01, np.pi - 0.01, 50)
    assert np.allclose(true_from_eccentric(eccentric_from_true(nu, e), e), nu, atol=1e-12)


@pytest.mark.parametrize(
    "el",
    [
        KeplerianElements(7000.0, 0.01, np.radians(51.6), 1.0, 2.0, 3.0),
        KeplerianElements(6878.0, 0.001, np.radians(97.4), 5.5, 0.3, 0.1),
        KeplerianElements(26560.0, 0.7, np.radians(63.4), 0.2, np.radians(270), 4.0),
        KeplerianElements(42164.0, 0.2, np.radians(5.0), 3.0, 1.0, 6.0),
    ],
)
def test_elements_round_trip(el):
    r, v = keplerian_to_cartesian(el)
    back = cartesian_to_keplerian(r, v)
    assert back.a == pytest.approx(el.a, rel=1e-12)
    assert back.e == pytest.approx(el.e, abs=1e-12)
    for name in ("i", "raan", "argp", "nu"):
        assert np.angle(np.exp(1j * (getattr(back, name) - getattr(el, name)))) == pytest.approx(0, abs=1e-9)


def test_circular_speed_and_radius():
    a = 6878.137
    r, v = keplerian_to_cartesian(KeplerianElements(a, 0.0, 0.5, 0.2, 0.0, 1.0))
    assert np.linalg.norm(r) == pytest.approx(a)
    assert np.linalg.norm(v) == pytest.approx(np.sqrt(MU_EARTH / a))
    assert np.dot(r, v) == pytest.approx(0.0, abs=1e-9)


def test_vectorized_true_anomaly_shape():
    el = KeplerianElements(7000.0, 0.1, 0.9, 0.0, 0.0, 0.0)
    r, v = keplerian_to_cartesian(el, nu=np.linspace(0, 1, 7))
    assert r.shape == (3, 7) and v.shape == (3, 7)
