import { useEffect, useState } from "react";
import { checkForUpdate, type AvailableUpdate } from "../updater";

type State =
  | { kind: "idle" }
  | { kind: "available"; update: AvailableUpdate }
  | { kind: "installing"; update: AvailableUpdate; progress: number | null }
  | { kind: "failed"; message: string };

export default function UpdateBanner() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Quietly ignore failures (offline, GitHub unreachable): updates are optional.
    checkForUpdate()
      .then((update) => update && setState({ kind: "available", update }))
      .catch(() => {});
  }, []);

  if (dismissed || state.kind === "idle") return null;

  if (state.kind === "failed") {
    return (
      <div className="update-banner failed" role="alert">
        Update failed: {state.message}
        <button type="button" className="link-button" onClick={() => setDismissed(true)}>
          Dismiss
        </button>
      </div>
    );
  }

  const { update } = state;
  const install = async () => {
    setState({ kind: "installing", update, progress: 0 });
    try {
      await update.install((progress) => setState({ kind: "installing", update, progress }));
    } catch (e) {
      setState({ kind: "failed", message: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <div className="update-banner" role="status">
      <span>
        <strong>Version {update.version}</strong> is available.
      </span>
      {update.notes && (
        <details className="update-notes">
          <summary>What's new</summary>
          <pre>{update.notes}</pre>
        </details>
      )}
      {state.kind === "installing" ? (
        <span className="hint">
          {state.progress === null || state.progress < 1
            ? `Downloading${state.progress !== null ? ` ${Math.round(state.progress * 100)}%` : "…"}`
            : "Installing…"}
        </span>
      ) : (
        <>
          <button type="button" className="primary" onClick={install}>
            Install and restart
          </button>
          <button type="button" className="link-button" onClick={() => setDismissed(true)}>
            Later
          </button>
        </>
      )}
    </div>
  );
}
