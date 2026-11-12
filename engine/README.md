# simcore

The Python simulation engine for the CubeSat simulator: orbit propagation,
reference frames, ground-station visibility and (soon) link budgets.

## Setup

```bash
python -m venv ../.venv
../.venv/bin/pip install -e '.[dev]'      # Windows: ..\.venv\Scripts\pip
```

## Usage

```bash
simcore run ../scenarios/sso_3u_demo.yaml
simcore run ../scenarios/sso_3u_demo.yaml --json ../out/demo.json --ephemeris
```

## Tests

```bash
pytest
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
