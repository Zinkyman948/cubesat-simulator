import numpy as np
import pytest
from skyfield.api import wgs84

from simcore.frames import ecef_to_geodetic, gcrs_to_itrs, geodetic_to_ecef
from simcore.orbit.propagators import SGP4Propagator
from simcore.timeutil import offset

from conftest import ISS_LINE1, ISS_LINE2


@pytest.mark.parametrize("lat_deg", [-89.9, -45.0, 0.0, 30.0, 78.23, 89.9])
@pytest.mark.parametrize("alt_km", [0.0, 1.655, 500.0, 35786.0])
def test_geodetic_round_trip(lat_deg, alt_km):
    lat, lon = np.radians(lat_deg), np.radians(-105.27)
    lat2, lon2, alt2 = ecef_to_geodetic(geodetic_to_ecef(lat, lon, alt_km))
    assert lat2 == pytest.approx(lat, abs=1e-12)
    assert lon2 == pytest.approx(lon, abs=1e-12)
    assert alt2 == pytest.approx(alt_km, abs=1e-8)


def test_station_ecef_matches_skyfield():
    ours = geodetic_to_ecef(np.radians(40.015), np.radians(-105.27), 1.655)
    theirs = wgs84.latlon(40.015, -105.27, elevation_m=1655).itrs_xyz.km
    assert np.allclose(ours, theirs, atol=1e-6)


def test_subsatellite_point_matches_skyfield():
    prop = SGP4Propagator(ISS_LINE1, ISS_LINE2)
    t = offset(prop.epoch, np.linspace(0, 6000, 40))
    r, v = prop.state(t)
    lat, lon, alt = ecef_to_geodetic(gcrs_to_itrs(t, r, v)[0])

    geo = wgs84.geographic_position_of(prop.satellite.at(t))
    assert np.allclose(np.degrees(lat), geo.latitude.degrees, atol=1e-7)
    assert np.allclose(np.degrees(lon), geo.longitude.degrees, atol=1e-7)
    assert np.allclose(alt, geo.elevation.km, atol=1e-5)


def test_earth_fixed_velocity_matches_finite_difference():
    prop = SGP4Propagator(ISS_LINE1, ISS_LINE2)
    h = 0.5
    t = offset(prop.epoch, np.array([1000.0 - h, 1000.0, 1000.0 + h]))
    r, v = prop.state(t)
    r_ecef, v_ecef = gcrs_to_itrs(t, r, v)
    fd = (r_ecef[:, 2] - r_ecef[:, 0]) / (2 * h)
    assert np.allclose(v_ecef[:, 1], fd, atol=1e-5)  # km/s, i.e. 1 cm/s
