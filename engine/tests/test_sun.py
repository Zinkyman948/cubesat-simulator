import numpy as np
import pytest

from simcore.environment.sun import AU_KM, sun_position_km
from simcore.timeutil import timescale

TS = timescale()


def declination_deg(r):
    return np.degrees(np.arcsin(r[2] / np.linalg.norm(r)))


@pytest.mark.parametrize(
    "when, dec",
    [
        ((2026, 3, 20, 14, 46), 0.0),  # March equinox
        ((2026, 6, 21, 8, 24), 23.44),  # June solstice
        ((2026, 9, 23, 0, 5), 0.0),  # September equinox
        ((2026, 12, 21, 20, 50), -23.44),  # December solstice
    ],
)
def test_declination_at_equinoxes_and_solstices(when, dec):
    assert declination_deg(sun_position_km(TS.utc(*when))) == pytest.approx(dec, abs=0.05)


def test_distance_at_perihelion_and_aphelion():
    perihelion = np.linalg.norm(sun_position_km(TS.utc(2026, 1, 3))) / AU_KM
    aphelion = np.linalg.norm(sun_position_km(TS.utc(2026, 7, 6))) / AU_KM
    assert perihelion == pytest.approx(0.9833, abs=0.0005)
    assert aphelion == pytest.approx(1.0167, abs=0.0005)


def test_vectorized_shape():
    assert sun_position_km(TS.utc(2026, 1, 1, 0, [0, 30, 60])).shape == (3, 3)
