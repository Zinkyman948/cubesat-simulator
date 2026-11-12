"""Spacecraft attitude: the body frame as a function of time.

An attitude is a (3, 3, N) array A whose columns are the body X, Y and Z
axes expressed in GCRS: a body vector b maps to GCRS as A[:, :, n] @ b, and
a GCRS vector w maps to the body frame as A[:, :, n].T @ w.
"""

from __future__ import annotations

import numpy as np
from skyfield.framelib import itrs
from skyfield.timelib import Time

from simcore.environment.sun import sun_position_km
from simcore.frames import gcrs_to_itrs
from simcore.scenario.models import Attitude
from simcore.timeutil import seconds_between
from simcore.visibility.groundstation import GroundStation

_GCRS_X = np.array([1.0, 0.0, 0.0])
_GCRS_Y = np.array([0.0, 1.0, 0.0])


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=0)


def _columns(v, n: int) -> np.ndarray:
    """A direction (3,) or set of directions (3, N) as (3, N)."""
    v = np.asarray(v, dtype=float)
    return np.repeat(v[:, None], n, axis=1) if v.ndim == 1 else v


def frame_from(z: np.ndarray, x_hint: np.ndarray) -> np.ndarray:
    """Right-handed frame with +Z along `z` and +X as close as possible to `x_hint`.

    Both are (3, N); `z` must be unit length. Where `x_hint` is (nearly)
    parallel to `z`, GCRS +X (or +Y) is used instead.
    """
    x = x_hint - np.sum(x_hint * z, axis=0) * z
    norm = np.linalg.norm(x, axis=0)
    bad = norm < 1e-9
    if bad.any():
        fallback = np.where(np.abs(z[0]) < 0.9, _GCRS_X[:, None], _GCRS_Y[:, None])
        alt = fallback - np.sum(fallback * z, axis=0) * z
        x[:, bad] = alt[:, bad]
        norm = np.linalg.norm(x, axis=0)
    x = x / norm
    y = np.cross(z, x, axis=0)
    return np.stack([x, y, z], axis=1)


def station_positions_gcrs(t: Time, station: GroundStation) -> np.ndarray:
    """Station position (km) in GCRS at each time, (3, N)."""
    R = itrs.rotation_at(t)
    if R.ndim == 2:
        R = R[:, :, None]
    return np.einsum("jin,j->in", R, station.ecef)


def gcrs_axes_to_itrs(t: Time, axes: np.ndarray) -> np.ndarray:
    """Rotate attitude axes (3, 3, N) from GCRS into the Earth-fixed frame."""
    R = itrs.rotation_at(t)
    if R.ndim == 2:
        R = R[:, :, None]
    return np.einsum("ijn,jkn->ikn", R, axes)


class AttitudeModel:
    def __init__(self, config: Attitude, stations: list[GroundStation], start: Time):
        self.config = config
        self.stations = stations
        self.start = start

    def axes(self, t: Time, r: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Body axes in GCRS, (3, 3, N), for GCRS state r, v of shape (3,) or (3, N)."""
        r = np.asarray(r, dtype=float).reshape(3, -1)
        v = np.asarray(v, dtype=float).reshape(3, -1)
        n = r.shape[1]
        mode = self.config.mode

        if mode == "nadir":
            return frame_from(_unit(-r), v)
        if mode == "sun":
            sun = sun_position_km(t).reshape(3, -1)
            return frame_from(_unit(sun - r), np.cross(r, v, axis=0))
        if mode == "inertial":
            z = _columns(_unit(np.asarray(self.config.pointing, dtype=float)), n)
            return frame_from(z, _columns(_GCRS_X, n))
        if mode == "spin":
            z = _columns(_unit(np.asarray(self.config.spin_axis, dtype=float)), n)
            x0 = frame_from(z, _columns(_GCRS_X, n))[:, 0, :]
            angle = np.radians(self.config.spin_rate_deg_s) * np.atleast_1d(
                seconds_between(self.start, t)
            )
            x = x0 * np.cos(angle) + np.cross(z, x0, axis=0) * np.sin(angle)
            return np.stack([x, np.cross(z, x, axis=0), z], axis=1)
        return self._target(t, r, v)

    def _target(self, t: Time, r: np.ndarray, v: np.ndarray) -> np.ndarray:
        z = _unit(-r)  # nadir unless a station is visible
        if self.stations:
            r_ecef, v_ecef = gcrs_to_itrs(t, r, v)
            # Elevation above each station's mask; the best visible station wins.
            margins = np.array(
                [
                    np.atleast_1d(gs.look_angles(r_ecef, v_ecef).elevation) - gs.min_elevation
                    for gs in self.stations
                ]
            )
            best = np.argmax(margins, axis=0)
            visible = margins[best, np.arange(r.shape[1])] > 0
            if visible.any():
                targets = np.array([station_positions_gcrs(t, gs).reshape(3, -1) for gs in self.stations])
                chosen = targets[best, :, np.arange(r.shape[1])].T  # (3, N)
                z = np.where(visible, _unit(chosen - r), z)
        return frame_from(z, v)
