// In-app updates (desktop only). Releases are published on GitHub with a
// signed latest.json; the Tauri updater verifies the signature against the
// public key in tauri.conf.json before installing anything.

export const isDesktop = "__TAURI_INTERNALS__" in window;

export interface AvailableUpdate {
  version: string;
  notes: string;
  /** Download, stop the engine, install and restart. Reports 0-1 download progress. */
  install: (onProgress: (fraction: number | null) => void) => Promise<void>;
}

export async function appVersion(): Promise<string | null> {
  if (!isDesktop) return null;
  const { getVersion } = await import("@tauri-apps/api/app");
  return getVersion();
}

export async function checkForUpdate(): Promise<AvailableUpdate | null> {
  if (!isDesktop) return null;
  const { check } = await import("@tauri-apps/plugin-updater");
  const update = await check();
  if (!update) return null;

  return {
    version: update.version,
    notes: update.body ?? "",
    install: async (onProgress) => {
      const { invoke } = await import("@tauri-apps/api/core");
      const { relaunch } = await import("@tauri-apps/plugin-process");
      let total = 0;
      let received = 0;
      await update.download((event) => {
        if (event.event === "Started") total = event.data.contentLength ?? 0;
        else if (event.event === "Progress") {
          received += event.data.chunkLength;
          onProgress(total ? received / total : null);
        }
      });
      // The installer replaces the engine executable, so stop it first.
      await invoke("stop_engine");
      // On Windows this launches the installer and exits the app.
      await update.install();
      await relaunch();
    },
  };
}
