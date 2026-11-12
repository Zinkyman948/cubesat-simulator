# CubeSat Simulator

A high-fidelity CubeSat mission simulator: define an orbit, a spacecraft and
a set of ground stations, then model passes and the radio link between them.

**Planned architecture:** a Python physics engine (`engine/`) behind a Tauri
desktop app with a web frontend (CesiumJS globe, charts) and auto-updates
via GitHub Releases.

## Status

| Milestone | Scope | Status |
|---|---|---|
| 1. Engine skeleton | Scenario files, two-body / J2 / SGP4 propagation, frames, pass prediction, CLI | Done |
| 2. Link budget v1 | Path loss, Doppler, noise, Eb/N0, BER, margin, data volume | Done |
| 3. Desktop shell | Tauri app, Cesium globe, charts, Python sidecar | Planned |
| 4. Packaging | Windows installer, updater, release CI | Planned |
| 5. Fidelity | Full force model, ITU-R losses, attitude, antennas, eclipses | Planned |
| 6. Validation & polish | GMAT comparisons, docs, web demo, macOS/Linux | Planned |

## Quick start

Requires Python 3.11 or newer.

**Windows (PowerShell)**, from the repository folder:

```powershell
py -m venv .venv
.venv\Scripts\pip install -e "engine[dev]"
.venv\Scripts\simcore run scenarios\sso_3u_demo.yaml
.venv\Scripts\simcore budget scenarios\sso_3u_demo.yaml
.venv\Scripts\pytest engine
```

**Linux / macOS:**

```bash
python3 -m venv .venv
.venv/bin/pip install -e 'engine[dev]'
.venv/bin/simcore run scenarios/sso_3u_demo.yaml
.venv/bin/simcore budget scenarios/sso_3u_demo.yaml
.venv/bin/pytest engine
```

See [`engine/README.md`](engine/README.md) for conventions and details.

## Layout

```
engine/      Python simulation engine (simcore) and tests
scenarios/   Example scenario files (YAML)
```
