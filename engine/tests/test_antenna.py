import numpy as np
import pytest
from pydantic import ValidationError

from simcore.link.antenna import BACK_LOBE_DBI, gain_dbi, peak_gain_dbi
from simcore.link.rf import wavelength_m
from simcore.scenario.models import Antenna

F = 2.245e9
MU = np.linspace(-1, 1, 400001)  # cos(theta), uniform in solid angle


def mean_directivity(antenna):
    return np.trapezoid(10 ** (gain_dbi(antenna, F, MU) / 10), MU) / 2


@pytest.mark.parametrize("pattern", ["turnstile", "dipole"])
def test_lossless_patterns_conserve_power(pattern):
    assert mean_directivity(Antenna(pattern=pattern)) == pytest.approx(1.0, abs=1e-3)


@pytest.mark.parametrize("gain", [3.0103, 6.0, 9.0])
def test_cosine_pattern_conserves_power_apart_from_back_lobe(gain):
    # The -10 dBi back-lobe floor adds about 0.05 over the rear hemisphere.
    assert mean_directivity(Antenna(pattern="cosine", gain_dbi=gain)) == pytest.approx(1.05, abs=0.01)


def test_reference_values():
    turnstile = Antenna(pattern="turnstile")
    assert gain_dbi(turnstile, F, 1.0) == pytest.approx(1.76, abs=0.01)
    assert gain_dbi(turnstile, F, 0.0) == pytest.approx(-1.25, abs=0.01)
    dipole = Antenna(pattern="dipole")
    assert gain_dbi(dipole, F, 0.0) == pytest.approx(2.15, abs=0.01)  # broadside
    assert gain_dbi(dipole, F, 1.0) == pytest.approx(-20.0)  # along the element (null)
    patch = Antenna(pattern="cosine", gain_dbi=6.0)
    # 6 dBi -> n ~ 1: about 3 dB down at 60 degrees.
    assert gain_dbi(patch, F, np.cos(np.radians(60))) == pytest.approx(6.0 - 2.97, abs=0.05)
    assert gain_dbi(patch, F, -0.5) == BACK_LOBE_DBI


def test_dish_beamwidth_and_peak():
    dish = Antenna(pattern="dish", dish_diameter_m=0.5)
    peak = peak_gain_dbi(dish, F)
    assert gain_dbi(dish, F, 1.0) == pytest.approx(peak)
    # Uniform circular aperture: half-power full beamwidth 1.029 lambda / D.
    hpbw = 1.029 * wavelength_m(F) / 0.5
    assert gain_dbi(dish, F, np.cos(hpbw / 2)) == pytest.approx(peak - 3.01, abs=0.05)
    # First sidelobe of the Airy pattern: -17.6 dB.
    theta = np.linspace(hpbw, 3 * hpbw, 20001)
    g = gain_dbi(dish, F, np.cos(theta))
    first_null = np.argmin(g[: len(g) // 2])
    assert g[first_null:].max() - peak == pytest.approx(-17.57, abs=0.05)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"pattern": "cosine"}, "needs gain_dbi"),
        ({"pattern": "dipole", "gain_dbi": 2}, "fixed gain"),
        ({"pattern": "cosine", "gain_dbi": 2.0}, "at least"),
        ({"pattern": "dish"}, "needs dish_diameter_m"),
        ({"gain_dbi": 1, "axis": (0, 0, 0)}, "non-zero"),
    ],
)
def test_invalid_antennas(kwargs, message):
    with pytest.raises(ValidationError, match=message):
        Antenna(**kwargs)


def test_pattern_inferred_for_existing_scenarios():
    assert Antenna(gain_dbi=3).pattern == "isotropic"
    assert Antenna(dish_diameter_m=3.7).pattern == "dish"
