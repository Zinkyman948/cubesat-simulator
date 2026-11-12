# Changelog

## Unreleased

- Atmospheric drag in the numerical propagator, with density from NRLMSIS 2.1
  and selectable solar activity (low, moderate, high, a solar-cycle model, or
  custom F10.7/Ap).
- Orbit lifetime: a new "Orbit lifetime" view (and `simcore lifetime`)
  estimates the re-entry date and charts the altitude decay and solar flux.
- Spacecraft drag area (default: tumbling average of the form factor) and
  drag coefficient in the form.
- The demo scenario has drag enabled with the solar-cycle model.

## 0.3.0 - 2026-11-12

- Spacecraft attitude: nadir, ground-station tracking, Sun-pointing,
  inertial and spinning modes. The body axes are drawn on the globe.
- Antenna patterns for the spacecraft: patch (cosine), turnstile, dipole and
  dish, mounted along any body axis. Link budgets now use the actual gain
  toward the ground station at every moment of a pass.
- The second pass chart can show spacecraft antenna gain, off-boresight
  angle, received power, Eb/N0, path loss or Doppler rate.
- Multi-link chart readouts now show a value for every link.
- The demo scenario uses realistic antennas (turnstile, patch, monopole).
- ITU-R atmosphere: gas, cloud, rain and scintillation losses at each ground
  station from the ITU climate maps, for a chosen link availability (99 % by
  default). Rain and cloud also raise downlink receiver noise.
- New pass charts: atmospheric loss, rain attenuation and system noise
  temperature. An X-band link template and demo link show rain fade.
- The engine is now installed as a folder alongside the app, so it starts
  faster despite the larger ITU-R data.
- When a built-in example has been updated since you edited it, the editor
  says so and offers to load the new version or keep your edits.
- Chart axes and readouts keep meaningful digits for very small values
  (e.g. 0.00014 dB of rain at S-band) instead of showing 0.

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
