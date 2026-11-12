import numpy as np
import pytest

from simcore.attitude import AttitudeModel, frame_from, station_positions_gcrs
from simcore.environment.sun import sun_position_km
from simcore.orbit.elements import KeplerianElements
from simcore.orbit.propagators import TwoBodyPropagator
from simcore.scenario.models import Attitude
from simcore.timeutil import offset, timescale
from simcore.visibility.groundstation import GroundStation

TS = timescale()
EPOCH = TS.utc(2026, 11, 11)
SSO = KeplerianElements(a=6878.137, e=0.001, i=np.radians(97.4), raan=0.8, argp=0.3, nu=0.0)
TIMES = offset(EPOCH, np.linspace(0, 6000, 61))


def states():
    return TwoBodyPropagator(SSO, EPOCH).state(TIMES)


def assert_rotation(A):
    for n in range(A.shape[2]):
        m = A[:, :, n]
        assert np.allclose(m.T @ m, np.eye(3), atol=1e-12)
        assert np.linalg.det(m) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "config",
    [
        Attitude(mode="nadir"),
        Attitude(mode="sun"),
        Attitude(mode="inertial", pointing=(0, 0, 1)),  # +Z along GCRS +X fallback case
        Attitude(mode="inertial", pointing=(1, 0, 0)),
        Attitude(mode="spin", spin_axis=(0.3, -0.2, 0.9), spin_rate_deg_s=5),
        Attitude(mode="target"),
    ],
)
def test_frames_are_proper_rotations(config):
    stations = [GroundStation("Svalbard", 78.23, 15.41, 450, 5)]
    r, v = states()
    assert_rotation(AttitudeModel(config, stations, EPOCH).axes(TIMES, r, v))


def test_nadir_frame_is_lvlh():
    r, v = states()
    A = AttitudeModel(Attitude(), [], EPOCH).axes(TIMES, r, v)
    assert np.allclose(A[:, 2, :], -r / np.linalg.norm(r, axis=0))
    # +X within a fraction of a degree of the velocity for a near-circular orbit.
    cos = np.sum(A[:, 0, :] * v / np.linalg.norm(v, axis=0), axis=0)
    assert np.all(cos > np.cos(np.radians(0.1)))


def test_sun_frame_points_at_the_sun():
    r, v = states()
    A = AttitudeModel(Attitude(mode="sun"), [], EPOCH).axes(TIMES, r, v)
    to_sun = sun_position_km(TIMES) - r
    assert np.allclose(A[:, 2, :], to_sun / np.linalg.norm(to_sun, axis=0))


def test_spin_rotates_at_the_requested_rate():
    r, v = states()
    # 0.5 deg/s over 100 s samples: 50 deg steps, well below the 180 deg alias limit.
    model = AttitudeModel(Attitude(mode="spin", spin_axis=(0, 0, 1), spin_rate_deg_s=0.5), [], EPOCH)
    A = model.axes(TIMES, r, v)
    angle = np.degrees(np.unwrap(np.arctan2(A[1, 0, :], A[0, 0, :])))
    assert np.allclose(np.diff(angle), 50.0)  # positive: right-handed about +Z


def test_target_points_at_visible_station_else_nadir():
    station = GroundStation("Svalbard", 78.23, 15.41, 450, 5)
    t = offset(EPOCH, np.arange(0, 86400, 30.0))
    r, v = TwoBodyPropagator(SSO, EPOCH).state(t)
    A = AttitudeModel(Attitude(mode="target"), [station], EPOCH).axes(t, r, v)
    to_station = station_positions_gcrs(t, station) - r
    to_station /= np.linalg.norm(to_station, axis=0)
    on_target = np.isclose(np.sum(A[:, 2, :] * to_station, axis=0), 1.0)
    on_nadir = np.isclose(np.sum(A[:, 2, :] * -r / np.linalg.norm(r, axis=0), axis=0), 1.0)
    assert on_target.any() and on_nadir.any()
    assert np.all(on_target | on_nadir)


def test_frame_from_handles_parallel_hint():
    z = np.array([[1.0], [0.0], [0.0]])
    assert_rotation(frame_from(z, z.copy()))
