# simcore

The Python simulation engine for the CubeSat simulator: orbit propagation,
reference frames, ground-station visibility and RF link budgets.

Setup instructions (Windows and Linux) are in the [top-level README](../README.md).

## Commands

```bash
simcore run scenario.yaml                       # passes + per-pass link summary
simcore run scenario.yaml --json out/r.json     # also write full results (incl. link time series)
simcore run scenario.yaml --json out/r.json --ephemeris   # ... plus the sampled orbit
simcore budget scenario.yaml                    # classic link budget at mask elevation and zenith
```

## Conventions

| Quantity | Convention |
|---|---|
| Inertial frame | GCRS (IAU, aligned with J2000/ICRS) |
| Earth-fixed frame | ITRS via skyfield's IAU 2000A model (no polar motion yet) |
| Geodetic | WGS84 |
| Units | km, km/s, seconds internally; degrees in scenario files |
| Time | Scenario times in UTC; integration in TT seconds |
| Keplerian elements | Osculating, referenced to GCRS |
| Elevation | Geometric (no atmospheric refraction) |

## Propagators

- `two_body`: analytic Kepler motion
- `j2`: numerical (DOP853) point mass + J2, with the oblateness term aligned
  to the Earth's true spin axis at epoch; optionally atmospheric drag
- `sgp4`: SGP4/SDP4 from a TLE (via skyfield); drag comes from the TLE's B*

## Drag and orbit lifetime

With `drag.enabled: true`, the numerical propagator adds
`a = -1/2 rho (Cd A / m) |v_rel| v_rel`, with `v_rel` relative to an
atmosphere co-rotating with the Earth and density `rho` from NRLMSIS 2.1
(pymsis). Density is sampled every 30 s along the trajectory and the orbit
re-integrated until it converges (end position within 1 km), which avoids
calling NRLMSIS at every integrator step; validated against calling it at
every step.

`drag.solar_activity` drives the density: `low`/`moderate`/`high`
(F10.7 = 70/150/250, Ap = 4/15/40), `custom` (`f107`, `ap`), or `cycle`, an
approximate 11-year solar cycle (F10.7 70-180, minimum 2019.9) for long runs.

The drag area defaults to the tumbling average of the form factor (surface
area / 4, e.g. 0.039 m^2 for a bare 3U); `drag_coefficient` defaults to 2.2.

`simcore lifetime scenario.yaml` (and `/api/lifetime`) estimates time to
re-entry (perigee below 120 km) with orbit-averaged decay: Gauss's equations
for along-track drag averaged over 72 points per orbit with NRLMSIS density
at each, J2 precession, and adaptive steps (at most 0.5 km of decay or one
day). It starts from the mean orbital radius over the first orbit, which
matters: under J2 the satellite flies several km above a circular orbit of
its averaged semi-major axis. Agrees with full numerical integration within
5 % over 10 days at 350 km. Solar activity is by far the largest uncertainty.

## Link budget model

Per link and per pass, sampled every `link_step_seconds`:

```
EIRP      = P_tx - L_tx_line + G_tx
C         = EIRP - FSPL - L_atm - L_pol - L_point + G_rx
C/N0      = C - k - 10 log10(T_sys)
Eb/N0     = C/N0 - 10 log10(R_b) - L_impl
margin    = Eb/N0 - (Eb/N0_required,uncoded(BER) - coding gain)
```

- **FSPL**: Friis free-space loss from the actual slant range.
- **T_sys**: given directly, or computed as `T_ant + T0 (L - 1) + L T_LNA`,
  referred to the antenna terminals.
- **Atmosphere**: ITU-R models at each ground station (see below), plus an
  optional per-link `atmospheric_zenith_db` extra loss (e.g. a radome) scaled
  by slant path through an 8 km spherical shell.
- **Modulations**: BPSK, QPSK, 8PSK, coherent and non-coherent BFSK, and GMSK
  (BT = 0.25 approximation), using uncoded AWGN BER curves.
- **Coding**: a fixed coding gain plus a code rate; the coded BER is
  approximated as the uncoded curve shifted by the gain.
- **Doppler**: first-order `-f * rdot / c`; the Doppler rate is the numerical
  derivative of the sampled Doppler.
- **Data volume**: data rate multiplied by the time with margin >= 0,
  interpolating the crossings.
- Spacecraft antenna gain comes from the antenna pattern and the attitude
  (see below); ground antennas are assumed to track and use their peak gain.

## Atmosphere (ITU-R)

`atmosphere.model: itu-r` (the default) computes tropospheric losses with
ITU-Rpy for each station and link, not exceeded for `availability_percent`
of an average year (default 99 %):

- gaseous absorption (P.676), cloud (P.840), rain (P.837/P.838/P.839) and
  scintillation, combined per P.618: `A_gas + sqrt((A_rain + A_cloud)^2 + A_scint^2)`
- local climate (rain rate, water vapour, temperature, cloud water) from the
  ITU digital maps
- scintillation uses the ground antenna's aperture: the dish diameter, or the
  equivalent diameter `(lambda/pi) sqrt(G/0.5)` for other antennas
- rain and cloud raise a ground receiver's noise temperature by
  `275 K (1 - 10^(-(A_rain + A_cloud)/10))` (downlinks only)

Losses are computed on an elevation grid once per station and link, then
interpolated. The ITU-R models cover 1-55 GHz and elevations of 5 deg or more;
below 1 GHz (UHF/VHF) the values are tiny, and below 5 deg they are
extrapolated. `model: none` gives free-space propagation.

## Attitude and antenna patterns

`spacecraft.attitude.mode` sets the body frame (default `nadir`):

| Mode | +Z | +X |
|---|---|---|
| `nadir` | toward Earth's center | along the velocity (LVLH) |
| `target` | at the highest visible ground station; nadir otherwise | toward the velocity |
| `sun` | toward the Sun | toward the orbit normal |
| `inertial` | fixed `pointing` direction (GCRS) | toward GCRS +X |
| `spin` | fixed `spin_axis` (GCRS), rotating at `spin_rate_deg_s` | rotates about +Z |

Spacecraft antennas have a `pattern` mounted along a body `axis` (default `[0, 0, 1]`):

| Pattern | Gain |
|---|---|
| `isotropic` | `gain_dbi` everywhere (the default when only `gain_dbi` is given) |
| `cosine` | patch: `gain_dbi` peak, G0 cos^n(theta) with G0 = 2(n + 1); -10 dBi back lobe |
| `turnstile` | crossed dipoles: 1.76 dBi on the axis, -1.25 dBi broadside |
| `dipole` | half-wave dipole with its element along the axis: 2.15 dBi broadside, -20 dBi nulls |
| `dish` | uniform circular aperture, [2 J1(x)/x]^2, peak from diameter and efficiency |

At every link sample the line of sight to the station is expressed in the
body frame, and the pattern gives the gain at that off-boresight angle. The
Sun direction uses the Astronomical Almanac's low-precision formula (~0.01 deg).
