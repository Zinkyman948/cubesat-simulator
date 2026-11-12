import numpy as np
import pytest

from simcore.link.rf import (
    BOLTZMANN_DBW,
    atmospheric_path_factor,
    dish_gain_dbi,
    doppler_shift_hz,
    free_space_path_loss_db,
    slant_range_km,
    system_noise_temperature_k,
)


def test_boltzmann_in_db():
    assert BOLTZMANN_DBW == pytest.approx(-228.60, abs=0.005)


def test_free_space_path_loss_reference_values():
    # FSPL(dB) = 20 log10(d_km) + 20 log10(f_MHz) + 32.45
    assert free_space_path_loss_db(1.0, 1e9) == pytest.approx(92.45, abs=0.01)
    assert free_space_path_loss_db(1000.0, 437.5e6) == pytest.approx(
        60 + 20 * np.log10(437.5) + 32.45, abs=0.01
    )
    # Doubling distance adds 6.02 dB.
    assert free_space_path_loss_db(2000.0, 2.2e9) - free_space_path_loss_db(1000.0, 2.2e9) == pytest.approx(6.02, abs=0.01)


def test_dish_gain():
    # 3.7 m at 2245 MHz (lambda = 0.13354 m), 55% efficiency.
    assert dish_gain_dbi(3.7, 0.55, 2245e6) == pytest.approx(36.20, abs=0.01)
    # Doubling the diameter adds 6.02 dB.
    assert dish_gain_dbi(7.4, 0.55, 2245e6) - dish_gain_dbi(3.7, 0.55, 2245e6) == pytest.approx(6.02, abs=0.01)


def test_system_noise_temperature():
    # No line loss: T_ant + T_lna, with NF 3.0103 dB -> T_lna = 290 K.
    assert system_noise_temperature_k(100.0, 10 * np.log10(2), 0.0) == pytest.approx(390.0)
    # 3 dB line before an ideal LNA at T0 doubles noise referred to the antenna: T0 (L - 1).
    assert system_noise_temperature_k(0.0, 0.0, 10 * np.log10(2)) == pytest.approx(290.0)


def test_slant_range_geometry():
    assert slant_range_km(np.pi / 2, 500.0) == pytest.approx(500.0)
    # Horizon range for 500 km: sqrt((R+h)^2 - R^2)
    assert slant_range_km(0.0, 500.0) == pytest.approx(np.sqrt(6878.137**2 - 6378.137**2))


def test_atmospheric_path_factor():
    assert atmospheric_path_factor(np.pi / 2) == pytest.approx(1.0)
    assert atmospheric_path_factor(np.radians(30)) == pytest.approx(2.0, rel=0.01)
    horizon = atmospheric_path_factor(0.0)
    assert 30 < horizon < 50 and np.isfinite(horizon)
    assert atmospheric_path_factor(-0.1) == pytest.approx(horizon)


def test_doppler_sign_and_magnitude():
    # Approaching at 7 km/s at 437.5 MHz: about +10.2 kHz.
    assert doppler_shift_hz(-7.0, 437.5e6) == pytest.approx(10215.6, abs=0.5)
    assert doppler_shift_hz(7.0, 437.5e6) < 0
