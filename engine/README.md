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
  to the Earth's true spin axis at epoch
- `sgp4`: SGP4/SDP4 from a TLE (via skyfield)

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
- **Atmosphere**: zenith loss scaled by slant path through an 8 km spherical
  shell. A placeholder until the ITU-R models (P.676/P.618) are added.
- **Modulations**: BPSK, QPSK, 8PSK, coherent and non-coherent BFSK, and GMSK
  (BT = 0.25 approximation), using uncoded AWGN BER curves.
- **Coding**: a fixed coding gain plus a code rate; the coded BER is
  approximated as the uncoded curve shifted by the gain.
- **Doppler**: first-order `-f * rdot / c`; the Doppler rate is the numerical
  derivative of the sampled Doppler.
- **Data volume**: data rate multiplied by the time with margin >= 0,
  interpolating the crossings.
- Antenna gains are fixed values or computed dish peak gains (no patterns
  or attitude yet).
