//! Desktop shell: starts the Python simulation engine (bundled as a resource
//! folder, see scripts/build_engine.py) and tells the frontend where to reach it.
//!
//! The engine binds a free localhost port and prints `SIMCORE_READY port=<n>`.
//! Every request must carry the random per-launch token we pass it in the
//! SIMCORE_TOKEN environment variable, so other local processes can't use it.

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Mutex,
};
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Manager, RunEvent, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

/// How much of the engine's stderr to keep for error reports.
const STDERR_TAIL_CHARS: usize = 4000;

#[derive(Clone, Serialize)]
struct EngineInfo {
    port: u16,
    token: String,
}

#[derive(Default)]
struct EngineState {
    info: Mutex<Option<EngineInfo>>,
    error: Mutex<Option<String>>,
    /// The running engine. It also exits by itself when this app's process
    /// ends (it watches its parent), so it never outlives the app.
    child: Mutex<Option<CommandChild>>,
    terminated: AtomicBool,
}

/// `Ok(None)` while the engine is still starting.
#[tauri::command]
fn engine_info(state: State<EngineState>) -> Result<Option<EngineInfo>, String> {
    if let Some(err) = state.error.lock().unwrap().clone() {
        return Err(err);
    }
    Ok(state.info.lock().unwrap().clone())
}

/// Stop the engine and wait (up to 5 s) for it to exit, so an update can
/// replace its files. The engine is a single process holding no state worth
/// saving, so terminating it is clean.
#[tauri::command]
async fn stop_engine(state: State<'_, EngineState>) -> Result<(), String> {
    let Some(child) = state.child.lock().unwrap().take() else {
        return Ok(());
    };
    child.kill().map_err(|e| e.to_string())?;
    for _ in 0..100 {
        if state.terminated.load(Ordering::SeqCst) {
            break;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    Ok(())
}

fn start_engine(app: &AppHandle) -> Result<(), String> {
    // Development shortcut: point the app at an already running `simcore serve`.
    #[cfg(debug_assertions)]
    if let Ok(port) = std::env::var("SIMCORE_DEV_PORT") {
        let port = port.parse().map_err(|_| format!("bad SIMCORE_DEV_PORT: {port}"))?;
        *app.state::<EngineState>().info.lock().unwrap() =
            Some(EngineInfo { port, token: String::new() });
        return Ok(());
    }

    let token = uuid::Uuid::new_v4().simple().to_string();
    let exe = app
        .path()
        .resource_dir()
        .map_err(|e| e.to_string())?
        .join("engine")
        .join(if cfg!(windows) { "simcore-server.exe" } else { "simcore-server" });
    if !exe.exists() {
        return Err(format!("engine not found at {}", exe.display()));
    }
    let (mut events, child) = app
        .shell()
        .command(exe)
        .args(["serve", "--port", "0", "--exit-with-parent"])
        .env("SIMCORE_TOKEN", &token)
        .spawn()
        .map_err(|e| e.to_string())?;
    *app.state::<EngineState>().child.lock().unwrap() = Some(child);

    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut stderr_tail = String::new();
        while let Some(event) = events.recv().await {
            let state = app.state::<EngineState>();
            match event {
                CommandEvent::Stdout(bytes) => {
                    let line = String::from_utf8_lossy(&bytes);
                    if let Some(port) = line.trim().strip_prefix("SIMCORE_READY port=") {
                        if let Ok(port) = port.parse() {
                            *state.info.lock().unwrap() =
                                Some(EngineInfo { port, token: token.clone() });
                        }
                    }
                }
                CommandEvent::Stderr(bytes) => {
                    stderr_tail.push_str(&String::from_utf8_lossy(&bytes));
                    stderr_tail.push('\n');
                    if stderr_tail.len() > STDERR_TAIL_CHARS {
                        let cut = stderr_tail.len() - STDERR_TAIL_CHARS;
                        let cut = (cut..stderr_tail.len())
                            .find(|&i| stderr_tail.is_char_boundary(i))
                            .unwrap_or(stderr_tail.len());
                        stderr_tail.drain(..cut);
                    }
                }
                CommandEvent::Terminated(status) => {
                    state.terminated.store(true, Ordering::SeqCst);
                    *state.info.lock().unwrap() = None;
                    *state.error.lock().unwrap() = Some(format!(
                        "The simulation engine stopped unexpectedly (exit code {:?}).\n{}",
                        status.code,
                        stderr_tail.trim()
                    ));
                }
                _ => {}
            }
        }
    });
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .manage(EngineState::default())
        .invoke_handler(tauri::generate_handler![engine_info, stop_engine])
        .setup(|app| {
            if let Err(e) = start_engine(app.handle()) {
                *app.state::<EngineState>().error.lock().unwrap() =
                    Some(format!("Could not start the simulation engine: {e}"));
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(child) = app.state::<EngineState>().child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
