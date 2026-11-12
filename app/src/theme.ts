import { useEffect, useState } from "react";

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const SERIES_SLOTS = 8;

/**
 * Categorical color for the i-th link in the scenario: fixed per link, never
 * by rank. Links past the eighth share the last slot (they still have legend
 * and end-label identity).
 */
export function seriesColor(index: number): string {
  return cssVar(`--series-${Math.min(index, SERIES_SLOTS - 1) + 1}`);
}

/** Bumps whenever the OS light/dark setting changes, so canvases can repaint. */
export function useThemeVersion(): number {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setVersion((v) => v + 1);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return version;
}
