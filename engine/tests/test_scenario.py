import copy

import pytest
from pydantic import ValidationError

from simcore import simulation
from simcore.scenario import Scenario, load_scenario

from conftest import ISS_LINE1, ISS_LINE2

BASE = {
    "name": "test",
    "simulation": {"start": "2026-11-11T00:00:00Z", "duration_hours": 2},
    "spacecraft": {"name": "T"},
    "propagator": "two_body",
    "orbit": {"type": "keplerian", "altitude_km": 500, "inclination_deg": 97.4},
    "ground_stations": [{"name": "GS", "latitude_deg": 78.2, "longitude_deg": 15.4}],
}


def with_changes(**changes):
    data = copy.deepcopy(BASE)
    for key, value in changes.items():
        data[key] = value
    return data


@pytest.mark.parametrize("name", ["sso_3u_demo.yaml", "iss_tle_sgp4.yaml"])
def test_example_scenarios_load_and_run(scenarios_dir, name):
    scenario = load_scenario(scenarios_dir / name)
    scenario.simulation.duration_hours = 3
    result = simulation.run(scenario)
    assert set(result.passes) == {gs.name for gs in scenario.ground_stations}
    assert result.ephemeris.r_gcrs_km.shape[0] == 3
    result.to_dict(include_ephemeris=True)  # JSON-serializable shapes


def test_naive_start_is_utc():
    s = Scenario.model_validate(with_changes(simulation={"start": "2026-11-11T00:00:00", "duration_hours": 1}))
    assert s.simulation.start.utcoffset().total_seconds() == 0


def test_requires_exactly_one_size():
    orbit = {**BASE["orbit"], "semi_major_axis_km": 6878.0}
    with pytest.raises(ValidationError, match="exactly one"):
        Scenario.model_validate(with_changes(orbit=orbit))


def test_rejects_perigee_inside_atmosphere():
    orbit = {"type": "keplerian", "semi_major_axis_km": 7000.0, "eccentricity": 0.1, "inclination_deg": 50}
    with pytest.raises(ValidationError, match="perigee"):
        Scenario.model_validate(with_changes(orbit=orbit))


def test_tle_requires_sgp4():
    orbit = {"type": "tle", "line1": ISS_LINE1, "line2": ISS_LINE2}
    with pytest.raises(ValidationError, match="sgp4"):
        Scenario.model_validate(with_changes(orbit=orbit))
    Scenario.model_validate(with_changes(orbit=orbit, propagator="sgp4"))


def test_tle_checksum_is_checked():
    bad = ISS_LINE1[:-1] + "0"
    orbit = {"type": "tle", "line1": bad, "line2": ISS_LINE2}
    with pytest.raises(ValidationError, match="checksum"):
        Scenario.model_validate(with_changes(orbit=orbit, propagator="sgp4"))


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        Scenario.model_validate(with_changes(colour="blue"))


def test_duplicate_station_names_rejected():
    gs = BASE["ground_stations"][0]
    with pytest.raises(ValidationError, match="unique"):
        Scenario.model_validate(with_changes(ground_stations=[gs, gs]))
