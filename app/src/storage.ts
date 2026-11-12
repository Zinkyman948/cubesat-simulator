// Per-user conveniences kept in the webview's localStorage: scenario drafts
// and UI preferences. Every access is guarded: storage can be unavailable
// (private mode, cleared data), and the app must work without it.

const PREFIX = "cubesat-sim:";

export function load(key: string): string | null {
  try {
    return localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export function save(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(PREFIX + key);
    else localStorage.setItem(PREFIX + key, value);
  } catch {
    // Not persisting is fine.
  }
}
