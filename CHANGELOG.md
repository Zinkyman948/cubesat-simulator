# Changelog

## Unreleased

- Spacecraft attitude: nadir, ground-station tracking, Sun-pointing,
  inertial and spinning modes. The body axes are drawn on the globe.
- Antenna patterns for the spacecraft: patch (cosine), turnstile, dipole and
  dish, mounted along any body axis. Link budgets now use the actual gain
  toward the ground station at every moment of a pass.
- The second pass chart can show spacecraft antenna gain, off-boresight
  angle, received power, Eb/N0, path loss or Doppler rate.
- Multi-link chart readouts now show a value for every link.
- The demo scenario uses realistic antennas (turnstile, patch, monopole).

## 0.2.1 - 2026-11-12

- First update delivered through the in-app updater.
- Automated end-to-end tests: every change is now checked in a real browser
  against the engine (scenario loading, globe and charts, live form
  validation, editing and running scenarios, drafts, TLE scenarios).

## 0.2.0 - 2026-11-12

First public release.

- Desktop app for Windows with a 3D globe: orbit, ground track, ground stations
  and live contact lines.
- Scenario editor with a form and a YAML view of the same scenario, live
  validation, a sun-synchronous inclination helper, and link templates.
- Orbit propagation: two-body, numerical J2, and SGP4 from TLEs.
- Pass prediction for any number of ground stations.
- RF link budgets per pass: Doppler, path loss, noise, Eb/N0, BER, margin and
  data volume, with charts for elevation, range, Doppler and margin.
- Automatic updates: the app offers new versions when they are released.
