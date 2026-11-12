# Desktop app

Tauri 2 shell + React/TypeScript frontend. The frontend talks to the Python
engine (`simcore serve`) over a local HTTP API:

```
Tauri (Rust) ──spawns──▶ engine/simcore-server (PyInstaller folder build, bundled as a resource)
     │                        ▲  random localhost port + per-launch token
     └─ webview: React UI ────┘  Cesium globe, pass table, uPlot charts
```

- `src/` - React UI (`api.ts` finds the engine; `components/` holds the globe, charts and tables)
- `src-tauri/` - Rust shell (`src/lib.rs` starts and supervises the engine)
- `src-tauri/engine/` - the packaged engine, built by `scripts/build_engine.py` (not committed)

## Just want to run it?

Download the installer from the
[latest release](https://github.com/Zinkyman948/cubesat-simulator/releases/latest).
No developer tools are needed. Every CI run also uploads an unsigned test
installer as the **CubeSat-Simulator-Windows-installer** artifact.

## Option A: browser mode (Python + Node only)

Fastest way to work on the UI; no Rust needed. Two terminals, from the repo root:

```powershell
.venv\Scripts\simcore serve            # engine on http://127.0.0.1:8765
```

```powershell
cd app
npm install
npm run dev                            # open http://localhost:1420
```

## Option B: full desktop app

Prerequisites (Windows): [Rust](https://rustup.rs),
[Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
("Desktop development with C++"), Node.js 22, and the Python 3.13 venv from the
top-level README. WebView2 is preinstalled on Windows 10/11.

```powershell
# Package the engine (rerun after engine changes). Use a separate, clean
# environment: test tools like pytest in the dev venv break astropy's
# PyInstaller hook.
py -V:3.13 -m venv build\buildenv
build\buildenv\Scripts\pip install .\engine pyinstaller
build\buildenv\Scripts\python scripts\build_engine.py
cd app
npm install
npx tauri dev                                    # dev window with hot reload
npx tauri build                                  # installer in src-tauri\target\release\bundle\nsis
```

To skip rebuilding the engine while iterating on engine code in a debug build,
run `simcore serve` yourself and start the app with `$env:SIMCORE_DEV_PORT=8765`.

## End-to-end tests

Browser tests in `e2e/` drive the built frontend (served with the app's
Content Security Policy) against a real engine. CI runs them on every push.

```powershell
.venv\Scripts\Activate.ps1          # so `simcore` is on PATH
cd app
npx playwright install chromium     # once
npm run build
npm run test:e2e
```

## Releasing a new version

```powershell
.venv\Scripts\python scripts\release.py bump 0.3.0   # app, Rust crate and engine versions
# add a "## 0.3.0 - <date>" section to CHANGELOG.md (it becomes the release notes)
git commit -am "Release 0.3.0"
git tag v0.3.0
git push; git push origin v0.3.0
```

The **Release** workflow checks that the tag, versions and changelog agree, runs
the engine tests, builds and smoke-tests the engine sidecar, then builds the
installer, signs the update with the `TAURI_SIGNING_PRIVATE_KEY` /
`TAURI_SIGNING_PRIVATE_KEY_PASSWORD` repository secrets, and publishes a GitHub
Release including `latest.json`. Installed apps read that file at startup and
offer the update; before installing, the app stops the engine so the installer
can replace it (the engine also exits by itself whenever the app does).

The signing key lives outside the repository. **If it is lost, installed copies
can no longer be updated** (users would have to reinstall manually), so keep a
backup.

## Security

- The engine listens only on `127.0.0.1`, on a random port, and rejects any
  request without the random token generated at each launch.
- The frontend has no shell or filesystem access: the engine sidecar is
  started and stopped from Rust.
- Content Security Policy (`src-tauri/tauri.conf.json`): scripts load only from
  the app itself (no remote or inline scripts), and network access is limited
  to the app and the local engine. `'unsafe-eval'` is required because Cesium's
  widgets use Knockout.js, which evaluates code from strings when Cesium is
  imported. `vite preview` serves the build with the same policy, so violations
  show up when testing in a browser.
- Updates are signed: the app installs an update only if its signature matches
  the public key in `tauri.conf.json`.
