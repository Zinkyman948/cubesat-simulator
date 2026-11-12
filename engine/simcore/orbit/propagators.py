"""Orbit propagators.

Every propagator exposes `epoch` and `state(t)`, returning GCRS position
(km) and velocity (km/s) shaped (3,) for a scalar Time or (3, N) for a
Time array. GCRS is the IAU geocentric inertial frame (aligned with
J2000/ICRS to within milliarcseconds).
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from scipy.integrate import solve_ivp
from skyfield.framelib import itrs
from skyfield.sgp4lib import EarthSatellite
from skyfield.timelib import Time

from simcore.constants import J2, MU_EARTH, R_EARTH
from simcore.orbit.elements import (
    KeplerianElements,
    eccentric_from_mean,
    eccentric_from_true,
    keplerian_to_cartesian,
    mean_from_eccentric,
    true_from_eccentric,
)
from simcore.timeutil import seconds_between, timescale


class Propagator(Protocol):
    epoch: Time

    def state(self, t: Time) -> tuple[np.ndarray, np.ndarray]: ...


class TwoBodyPropagator:
    """Analytic Keplerian (point-mass) motion."""

    def __init__(self, elements: KeplerianElements, epoch: Time, mu: float = MU_EARTH):
        self.elements = elements
        self.epoch = epoch
        self.mu = mu
        self._mean_motion = np.sqrt(mu / elements.a**3)
        self._M0 = mean_from_eccentric(eccentric_from_true(elements.nu, elements.e), elements.e)

    def state(self, t: Time):
        M = self._M0 + self._mean_motion * seconds_between(self.epoch, t)
        nu = true_from_eccentric(eccentric_from_mean(M, self.elements.e), self.elements.e)
        return keplerian_to_cartesian(self.elements, nu=nu, mu=self.mu)


def j2_acceleration(r: np.ndarray, pole: np.ndarray, mu: float = MU_EARTH) -> np.ndarray:
    """Point-mass plus J2 acceleration for a (3,) position.

    `pole` is Earth's spin axis expressed in the integration frame, so the
    oblateness term stays aligned with the true equator rather than the
    J2000 one (they differ by ~0.15 deg today due to precession).
    """
    r_mag = np.linalg.norm(r)
    z = np.dot(r, pole)
    k = 1.5 * J2 * mu * R_EARTH**2 / r_mag**5
    return -mu * r / r_mag**3 - k * ((1.0 - 5.0 * z**2 / r_mag**2) * r + 2.0 * z * pole)


class J2Propagator:
    """Numerical propagation with point-mass gravity plus J2.

    Integrates with DOP853 and keeps a dense-output interpolant covering
    [t_start, t_end] (extended to include the epoch), so `state` can be
    queried at any time in that span without re-integrating.
    """

    def __init__(
        self,
        r0: np.ndarray,
        v0: np.ndarray,
        epoch: Time,
        t_start: Time,
        t_end: Time,
        mu: float = MU_EARTH,
        pole: np.ndarray | None = None,
        rtol: float = 1e-11,
        atol: float = 1e-9,
    ):
        self.epoch = epoch
        self.mu = mu
        # Third row of the GCRS->ITRS rotation is the ITRS z-axis in GCRS.
        # Precession over a multi-day scenario is negligible, so fix it at epoch.
        self.pole = itrs.rotation_at(epoch)[2] if pole is None else np.asarray(pole, dtype=float)

        y0 = np.concatenate([r0, v0])
        self._lo = min(0.0, float(seconds_between(epoch, t_start)))
        self._hi = max(0.0, float(seconds_between(epoch, t_end)))
        # Always integrate a short forward arc so a forward solution exists.
        self._forward = self._integrate(y0, max(self._hi, 1.0), rtol, atol)
        self._backward = self._integrate(y0, self._lo, rtol, atol) if self._lo < 0 else None

    def _derivatives(self, _s: float, y: np.ndarray) -> np.ndarray:
        return np.concatenate([y[3:], j2_acceleration(y[:3], self.pole, self.mu)])

    def _integrate(self, y0, s_end, rtol, atol):
        sol = solve_ivp(
            self._derivatives, (0.0, s_end), y0, method="DOP853",
            rtol=rtol, atol=atol, dense_output=True,
        )
        if not sol.success:
            raise RuntimeError(f"J2 integration failed: {sol.message}")
        return sol.sol

    def state(self, t: Time):
        s = np.asarray(seconds_between(self.epoch, t), dtype=float)
        if np.any(s < self._lo - 1e-6) or np.any(s > self._hi + 1e-6):
            raise ValueError("Requested time is outside the propagated span")
        s_flat = np.atleast_1d(s)
        y = np.empty((6, s_flat.size))
        fwd = s_flat >= 0
        if fwd.any():
            y[:, fwd] = self._forward(s_flat[fwd])
        if (~fwd).any():
            y[:, ~fwd] = self._backward(s_flat[~fwd])
        if s.ndim == 0:
            y = y[:, 0]
        return y[:3], y[3:]


class SGP4Propagator:
    """SGP4/SDP4 from a two-line element set (via skyfield/sgp4)."""

    def __init__(self, line1: str, line2: str, name: str = "SAT"):
        self.satellite = EarthSatellite(line1, line2, name, timescale())
        self.epoch = self.satellite.epoch

    def state(self, t: Time):
        geocentric = self.satellite.at(t)
        return geocentric.position.km, geocentric.velocity.km_per_s
