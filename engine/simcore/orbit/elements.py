"""Classical orbital elements and conversions to/from Cartesian state.

Elliptical orbits only (0 <= e < 1). Distances in km, velocities in km/s,
angles in radians. Functions accept scalar or array anomalies; Cartesian
vectors are shaped (3,) or (3, N).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simcore.constants import MU_EARTH

TWO_PI = 2.0 * np.pi
_SMALL = 1e-11


@dataclass(frozen=True)
class KeplerianElements:
    """Osculating classical elements."""

    a: float  # semi-major axis, km
    e: float  # eccentricity
    i: float  # inclination, rad
    raan: float  # right ascension of ascending node, rad
    argp: float  # argument of perigee, rad
    nu: float  # true anomaly, rad

    def period(self, mu: float = MU_EARTH) -> float:
        return TWO_PI * np.sqrt(self.a**3 / mu)


def eccentric_from_mean(M, e: float, tol: float = 1e-13, max_iter: int = 50):
    """Solve Kepler's equation M = E - e sin E by Newton iteration."""
    M = np.mod(np.asarray(M, dtype=float), TWO_PI)
    E = M + e * np.sin(M) if e < 0.8 else np.full_like(M, np.pi)
    for _ in range(max_iter):
        dE = (E - e * np.sin(E) - M) / (1.0 - e * np.cos(E))
        E = E - dE
        if np.all(np.abs(dE) < tol):
            break
    return E


def mean_from_eccentric(E, e: float):
    return E - e * np.sin(E)


def true_from_eccentric(E, e: float):
    return 2.0 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))


def eccentric_from_true(nu, e: float):
    return 2.0 * np.arctan2(np.sqrt(1 - e) * np.sin(nu / 2), np.sqrt(1 + e) * np.cos(nu / 2))


def perifocal_to_inertial(i: float, raan: float, argp: float) -> np.ndarray:
    """Rotation matrix R3(-raan) R1(-i) R3(-argp) from perifocal to inertial."""
    cO, sO = np.cos(raan), np.sin(raan)
    ci, si = np.cos(i), np.sin(i)
    cw, sw = np.cos(argp), np.sin(argp)
    return np.array(
        [
            [cO * cw - sO * sw * ci, -cO * sw - sO * cw * ci, sO * si],
            [sO * cw + cO * sw * ci, -sO * sw + cO * cw * ci, -cO * si],
            [sw * si, cw * si, ci],
        ]
    )


def keplerian_to_cartesian(el: KeplerianElements, nu=None, mu: float = MU_EARTH):
    """Position and velocity for the given elements.

    `nu` overrides `el.nu` and may be an array, giving (3, N) outputs.
    """
    nu = el.nu if nu is None else np.asarray(nu, dtype=float)
    p = el.a * (1.0 - el.e**2)
    r = p / (1.0 + el.e * np.cos(nu))
    zeros = np.zeros_like(nu)
    r_pf = np.array([r * np.cos(nu), r * np.sin(nu), zeros])
    v_pf = np.sqrt(mu / p) * np.array([-np.sin(nu), el.e + np.cos(nu), zeros])
    Q = perifocal_to_inertial(el.i, el.raan, el.argp)
    return Q @ r_pf, Q @ v_pf


def cartesian_to_keplerian(r, v, mu: float = MU_EARTH) -> KeplerianElements:
    """Osculating elements from a single (3,) position/velocity pair.

    For circular orbits the argument of perigee is set to 0 and the true
    anomaly is measured from the ascending node; for equatorial orbits the
    node is taken along +x.
    """
    r = np.asarray(r, dtype=float)
    v = np.asarray(v, dtype=float)
    r_mag = np.linalg.norm(r)
    v_mag = np.linalg.norm(v)

    h = np.cross(r, v)
    h_mag = np.linalg.norm(h)
    h_hat = h / h_mag
    n = np.cross([0.0, 0.0, 1.0], h)
    n_mag = np.linalg.norm(n)
    e_vec = ((v_mag**2 - mu / r_mag) * r - np.dot(r, v) * v) / mu
    e = np.linalg.norm(e_vec)

    energy = v_mag**2 / 2.0 - mu / r_mag
    a = -mu / (2.0 * energy)
    i = np.arccos(np.clip(h[2] / h_mag, -1.0, 1.0))

    node_hat = n / n_mag if n_mag > _SMALL else np.array([1.0, 0.0, 0.0])
    raan = np.arctan2(node_hat[1], node_hat[0]) % TWO_PI if n_mag > _SMALL else 0.0
    peri_hat = e_vec / e if e > _SMALL else node_hat

    argp = np.arctan2(np.dot(np.cross(node_hat, peri_hat), h_hat), np.dot(node_hat, peri_hat))
    nu = np.arctan2(np.dot(np.cross(peri_hat, r), h_hat), np.dot(peri_hat, r))
    return KeplerianElements(a=a, e=e, i=i, raan=raan, argp=argp % TWO_PI, nu=nu % TWO_PI)
