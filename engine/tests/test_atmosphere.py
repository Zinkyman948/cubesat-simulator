import warnings

import astropy.units as u
import itur
import numpy as np
import pytest

from simcore.environment.atmosphere import MEAN_RADIATING_TEMP_K, SlantPathAtmosphere
from simcore.link.analysis import link_atmosphere
from simcore.link.budget import LinkModel
from simcore.scenario.models import AtmosphereConfig, GroundStationConfig, LinkConfig

SINGAPORE = (1.35, 103.82, 0.015)
SVALBARD = (78.23, 15.41, 0.45)
X_BAND = 8.2e9


def atmosphere(site, f=X_BAND, p=1.0, diameter=5.4, eff=0.6, mask=5.0):
    return SlantPathAtmosphere(*site, f, p, diameter, eff, mask)


def test_matches_itu_rpy_between_grid_points():
    atm = atmosphere(SINGAPORE)
    els = np.array([7.3, 12.6, 33.3, 71.9])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        direct = itur.atmospheric_attenuation_slant_path(
            SINGAPORE[0], SINGAPORE[1], 8.2 * u.GHz, els, 1.0, 5.4 * u.m,
            hs=SINGAPORE[2] * u.km, eta=0.6, return_contributions=True,
        )
    ours = atm.at(els)
    for mine, theirs in zip(
        (ours.gas_db, ours.cloud_db, ours.rain_db, ours.scintillation_db, ours.total_db), direct
    ):
        assert np.allclose(mine, theirs.value, atol=0.02)


def test_physical_trends():
    tropics, arctic = atmosphere(SINGAPORE), atmosphere(SVALBARD)
    # Longer paths through the atmosphere at low elevation. (Up to 70 deg: the
    # P.618 rain model itself rises by ~0.02 dB between 88 and 90 deg.)
    els = np.linspace(5, 70, 40)
    assert np.all(np.diff(tropics.at(els).total_db) < 0)
    assert tropics.at(90.0).total_db < tropics.at(60.0).total_db
    # Heavy tropical rain versus dry polar climate.
    assert tropics.at(20.0).rain_db > 5 * arctic.at(20.0).rain_db
    # Higher frequency and stricter availability both cost more.
    assert atmosphere(SINGAPORE, f=20e9).at(20.0).total_db > tropics.at(20.0).total_db
    assert atmosphere(SINGAPORE, p=0.1).at(20.0).rain_db > tropics.at(20.0).rain_db
    # UHF barely notices the troposphere.
    assert atmosphere(SINGAPORE, f=437.5e6, diameter=1.5, eff=0.5).at(20.0).total_db < 0.2


def test_sky_noise_from_rain_and_cloud():
    loss = atmosphere(SINGAPORE).at(10.0)
    expected = MEAN_RADIATING_TEMP_K * (1 - 10 ** (-(loss.rain_db + loss.cloud_db) / 10))
    assert loss.sky_noise_k == pytest.approx(expected)
    assert 50 < float(loss.sky_noise_k) < MEAN_RADIATING_TEMP_K


def _link(direction: str, ground_antenna: dict) -> LinkConfig:
    spacecraft = {"pattern": "cosine", "gain_dbi": 12.0}
    ground_side = "receiver" if direction == "downlink" else "transmitter"
    tx = {"power_w": 2.0, "antenna": ground_antenna if ground_side == "transmitter" else spacecraft}
    rx = {"antenna": ground_antenna if ground_side == "receiver" else spacecraft, "system_noise_temp_k": 150}
    return LinkConfig.model_validate({
        "name": "X", "direction": direction, "frequency_mhz": 8200, "data_rate_bps": 1e6,
        "modulation": "qpsk", "transmitter": tx, "receiver": rx,
    })


def test_sky_noise_only_affects_downlinks():
    station = GroundStationConfig(name="SG", latitude_deg=1.35, longitude_deg=103.82)
    config = AtmosphereConfig(availability_percent=99.0)
    for direction, expect_noise_rise in (("downlink", True), ("uplink", False)):
        link = _link(direction, {"dish_diameter_m": 5.4})
        atm = link_atmosphere(config, link, station).at(np.array([10.0]))
        s = LinkModel(link).evaluate(np.array([1700.0]), np.array([0.0]), np.radians([10.0]), atmosphere=atm)
        assert (s.system_noise_temp_k[0] > 150.0) == expect_noise_rise
        assert s.atmospheric_loss_db[0] == pytest.approx(atm.total_db[0])


def test_non_dish_ground_antennas_use_equivalent_aperture(monkeypatch):
    captured = {}

    def fake_init(self, lat, lon, alt, f, p, diameter, eff, mask):
        captured.update(diameter=diameter, eff=eff)

    monkeypatch.setattr(SlantPathAtmosphere, "__init__", fake_init)
    link = _link("downlink", {"gain_dbi": 14.0})
    link_atmosphere(AtmosphereConfig(), link, GroundStationConfig(name="A", latitude_deg=0, longitude_deg=0))
    # D = (lambda / pi) sqrt(G / eta) for a 14 dBi antenna at 8.2 GHz, eta = 0.5.
    expected = (299792458 / 8.2e9) / np.pi * np.sqrt(10 ** 1.4 / 0.5)
    assert captured == {"diameter": pytest.approx(expected), "eff": 0.5}


def test_model_none_disables_atmosphere():
    station = GroundStationConfig(name="SG", latitude_deg=1.35, longitude_deg=103.82)
    assert link_atmosphere(AtmosphereConfig(model="none"), _link("downlink", {"gain_dbi": 30}), station) is None


@pytest.mark.parametrize("availability", [94.9, 99.9999])
def test_availability_range(availability):
    with pytest.raises(ValueError):
        AtmosphereConfig(availability_percent=availability)


def test_concurrent_first_use_is_safe():
    """ITU-Rpy's lazy map loading races without the module lock."""
    import importlib
    import threading

    import itur.models.itu840 as itu840

    importlib.reload(itu840)  # fresh, empty caches
    import itur

    itur.models.itu840 = itu840
    errors = []

    def work(lat):
        try:
            atmosphere((lat, 10.0, 0.0)).at(20.0)
        except Exception as e:  # pragma: no cover - the failure being tested for
            errors.append(e)

    threads = [threading.Thread(target=work, args=(lat,)) for lat in (0, 20, 40, 60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
