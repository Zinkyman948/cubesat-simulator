import numpy as np
import pytest
from skyfield.api import wgs84

from simcore.constants import R_EARTH
from simcore.orbit.propagators import SGP4Propagator
from simcore.timeutil import from_datetime, offset
from simcore.visibility.groundstation import GroundStation
from simcore.visibility.passes import find_passes, look_angles

from conftest import ISS_LINE1, ISS_LINE2


def test_look_angles_directly_overhead():
    gs = GroundStation("Equator", 0.0, 0.0, 0.0)
    la = gs.look_angles(np.array([R_EARTH + 500.0, 0.0, 0.0]), np.array([0.0, 7.6, 0.0]))
    assert np.degrees(la.elevation) == pytest.approx(90.0)
    assert la.range_km == pytest.approx(500.0)
    assert la.range_rate_km_s == pytest.approx(0.0)


def test_look_angles_azimuth_convention():
    gs = GroundStation("Equator", 0.0, 0.0, 0.0)
    north = gs.look_angles(np.array([R_EARTH, 0.0, 1000.0]), np.zeros(3))
    east = gs.look_angles(np.array([R_EARTH, 1000.0, 0.0]), np.zeros(3))
    assert np.degrees(north.azimuth) == pytest.approx(0.0, abs=1e-9)
    assert np.degrees(east.azimuth) == pytest.approx(90.0)


@pytest.fixture(scope="module")
def iss_passes():
    prop = SGP4Propagator(ISS_LINE1, ISS_LINE2)
    station = GroundStation("Bluffton", 40.8939, -83.8917, 0.0, 10.0)
    start = prop.epoch
    end = offset(start, 2 * 86400)
    return prop, station, start, end, find_passes(prop, station, start, end, step_s=30)


def test_aos_and_los_sit_on_the_mask(iss_passes):
    prop, station, _, _, passes = iss_passes
    assert passes
    for p in passes:
        el = look_angles(prop, station, from_datetime(p.aos)).elevation
        assert np.degrees(el) == pytest.approx(10.0, abs=1e-3)
        assert p.max_elevation_deg > 10.0


def test_passes_match_skyfield_find_events(iss_passes):
    """Independent validation against skyfield's own event finder."""
    prop, station, start, end, passes = iss_passes
    topos = wgs84.latlon(station.latitude_deg, station.longitude_deg)
    times, events = prop.satellite.find_events(topos, start, end, altitude_degrees=10.0)

    rises = [t.utc_datetime() for t, e in zip(times, events) if e == 0]
    sets = [t.utc_datetime() for t, e in zip(times, events) if e == 2]
    peaks = [t for t, e in zip(times, events) if e == 1]
    full = [p for p in passes if not (p.truncated_start or p.truncated_end)]
    assert len(full) == len(rises) == len(sets) == len(peaks)

    for p, rise, set_, peak in zip(full, rises, sets, peaks):
        assert abs((p.aos - rise).total_seconds()) < 1.0
        assert abs((p.los - set_).total_seconds()) < 1.0
        alt, _, _ = (prop.satellite - topos).at(peak).altaz()
        assert p.max_elevation_deg == pytest.approx(alt.degrees, abs=0.05)


def test_truncated_pass_at_window_edges(iss_passes):
    prop, station, _, _, passes = iss_passes
    first = passes[0]
    # Start the window in the middle of the first pass.
    mid = from_datetime(first.tca)
    clipped = find_passes(prop, station, mid, offset(mid, 60.0), step_s=10)
    assert len(clipped) == 1
    assert clipped[0].truncated_start and clipped[0].truncated_end
