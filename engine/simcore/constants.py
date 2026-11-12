"""Physical constants. Units: km, s, rad unless noted."""

# Earth gravitational parameter (EGM2008 / WGS84), km^3/s^2
MU_EARTH = 398600.4418

# WGS84 ellipsoid
R_EARTH = 6378.137  # equatorial radius, km
WGS84_F = 1.0 / 298.257223563  # flattening
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)  # first eccentricity squared

# Second zonal harmonic (unnormalized, EGM2008)
J2 = 1.08262668e-3

# Mean Earth rotation rate, rad/s
OMEGA_EARTH = 7.292115e-5

SECONDS_PER_DAY = 86400.0
