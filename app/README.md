# Desktop app

Tauri 2 shell + React/TypeScript frontend. The frontend talks to the Python
engine (`simcore serve`) over a local HTTP API:

```
Tauri (Rust) ──spawns──▶ simcore-server sidecar (PyInstaller build of the engine)
     │                        ▲  random localhost port + per-launch token
     └─ webview: React UI ────┘  Cesium globe, pass table, uPlot charts
```

- `src/` - React UI (`api.ts` finds the engine; `components/` holds the globe, charts and tables)
- `src-tauri/` - Rust shell (`src/lib.rs` starts and supervises the engine)
- `src-tauri/binaries/` - the engine sidecar, built by `scripts/build_engine.py` (not committed)

## Just want to run it?

Download the Windows installer from the latest successful
[CI run](https://github.com/Zinkyman948/cubesat-simulator/actions) (artifact
**CubeSat-Simulator-Windows-installer**). No developer tools are needed.

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
.venv\Scripts\pip install pyinstaller
.venv\Scripts\python scripts\build_engine.py     # builds the sidecar (rerun after engine changes)
cd app
npm install
npx tauri dev                                    # dev window with hot reload
npx tauri build                                  # installer in src-tauri\target\release\bundle\nsis
```

To skip rebuilding the sidecar while iterating on engine code in a debug build,
run `simcore serve` yourself and start the app with `$env:SIMCORE_DEV_PORT=8765`.
