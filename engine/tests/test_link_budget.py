import numpy as np
import pytest
from pydantic import ValidationError

from simcore import simulation
from simcore.link.analysis import budget_table, time_above_zero
from simcore.link.budget import LinkModel
from simcore.scenario import load_scenario
from simcore.scenario.models import LinkConfig

SIMPLE = {
    "name": "simple",
    "direction": "downlink",
    "frequency_mhz": 437.5,
    "data_rate_bps": 9600,
    "modulation": "bpsk",
    "transmitter": {"power_w": 1.0, "antenna": {"gain_dbi": 0.0}},
    "receiver": {"antenna": {"gain_dbi": 0.0}, "system_noise_temp_k": 290.0},
    "losses": {"implementation_db": 0.0},
}


def test_hand_calculated_budget():
    """1 W, isotropic antennas, 1000 km, 437.5 MHz, 290 K, 9600 bps."""
    model = LinkModel(LinkConfig.model_validate(SIMPLE))
    s = model.evaluate(np.array([1000.0]), np.array([0.0]), np.array([np.pi / 2]))

    fspl = 20 * np.log10(1000) + 20 * np.log10(437.5) + 32.45
    cn0 = 0.0 - fspl + 228.60 - 10 * np.log10(290)
    ebn0 = cn0 - 10 * np.log10(9600)
    assert s.path_loss_db[0] == pytest.approx(fspl, abs=0.01)
    assert s.received_power_dbm[0] == pytest.approx(30 - fspl, abs=0.01)
    assert s.cn0_dbhz[0] == pytest.approx(cn0, abs=0.01)
    assert s.ebn0_db[0] == pytest.approx(ebn0, abs=0.01)
    assert s.margin_db[0] == pytest.approx(ebn0 - 9.59, abs=0.02)
    assert s.delay_ms[0] == pytest.approx(3.3356, abs=1e-4)


def test_losses_and_coding_shift_margin_one_for_one():
    base = LinkModel(LinkConfig.model_validate(SIMPLE))
    lossy = LinkModel(LinkConfig.model_validate({
        **SIMPLE,
        "losses": {"polarization_db": 3, "pointing_db": 1, "implementation_db": 2},
        "coding": {"gain_db": 5.0, "rate": 0.5},
    }))
    args = (np.array([1500.0]), np.array([0.0]), np.array([0.5]))
    assert lossy.evaluate(*args).margin_db[0] - base.evaluate(*args).margin_db[0] == pytest.approx(-6 + 5)
    # Rate-1/2 coding doubles the symbol rate, halving Es/N0 relative to Eb/N0.
    s = lossy.evaluate(*args)
    assert s.ebn0_db[0] - s.esn0_db[0] == pytest.approx(10 * np.log10(2))


def test_computed_noise_temperature_and_dish_gain():
    cfg = {**SIMPLE, "receiver": {
        "antenna": {"dish_diameter_m": 3.7}, "antenna_noise_temp_k": 80,
        "noise_figure_db": 0.8, "line_loss_db": 0.3,
    }, "frequency_mhz": 2245}
    model = LinkModel(LinkConfig.model_validate(cfg))
    assert model.rx_antenna_gain_dbi == pytest.approx(36.20, abs=0.01)
    assert 150 < model.system_noise_temp_k < 170


@pytest.mark.parametrize(
    "receiver",
    [
        {"antenna": {"gain_dbi": 0}},  # no noise spec
        {"antenna": {"gain_dbi": 0}, "system_noise_temp_k": 300, "antenna_noise_temp_k": 50, "noise_figure_db": 1},
        {"antenna": {"gain_dbi": 0}, "system_noise_temp_k": 300, "line_loss_db": 1.0},
        {"antenna": {"gain_dbi": 0, "dish_diameter_m": 2}, "system_noise_temp_k": 300},
    ],
)
def test_invalid_receivers(receiver):
    with pytest.raises(ValidationError):
        LinkConfig.model_validate({**SIMPLE, "receiver": receiver})


def test_time_above_zero_interpolates_crossings():
    t = np.array([0.0, 10.0, 20.0, 30.0])
    assert time_above_zero(t, np.array([-1.0, 1.0, 1.0, -1.0])) == pytest.approx(20.0)
    assert time_above_zero(t, np.array([1.0, 1.0, 1.0, 1.0])) == pytest.approx(30.0)
    assert time_above_zero(t, np.array([-1.0, -1.0, -1.0, -1.0])) == 0.0


def test_budget_table_ends_in_consistent_margin():
    model = LinkModel(LinkConfig.model_validate(SIMPLE))
    rows = {label: value for label, value, _ in budget_table(model, 500.0, 0.0, 90.0)}
    assert rows["Slant range"] == pytest.approx(500.0)
    assert rows["Link margin"] == pytest.approx(rows["Eb/N0"] - rows["Required Eb/N0"])


@pytest.fixture(scope="module")
def demo_result():
    scenario = load_scenario(__import__("conftest").SCENARIOS / "sso_3u_demo.yaml")
    scenario.simulation.duration_hours = 6
    return simulation.run(scenario)


def test_demo_link_passes_are_physically_consistent(demo_result):
    uhf = [lp for lp in demo_result.link_passes if lp.link == "UHF telemetry"]
    assert uhf
    for lp in uhf:
        s = lp.samples
        tca = np.argmin(s.range_km)
        # Doppler goes from positive (approaching) to negative (receding).
        assert s.doppler_hz[0] > 0 > s.doppler_hz[-1]
        # Best margin occurs at closest approach (within one sample).
        assert abs(int(np.argmax(s.margin_db)) - int(tca)) <= 1
        # Peak |Doppler| for UHF from LEO is about +/-10 kHz.
        assert lp.max_abs_doppler_hz < 11e3
        assert lp.data_volume_bits == pytest.approx(lp.link_closed_s * 9600)


def test_link_station_filter(demo_result):
    stations = {lp.station for lp in demo_result.link_passes if lp.link == "S-band payload"}
    assert stations <= {"Svalbard", "Boulder"}
