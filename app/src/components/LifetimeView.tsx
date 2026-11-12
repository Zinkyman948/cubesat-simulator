import { useMemo, useState } from "react";
import { ScenarioError, estimateLifetime } from "../api";
import { seriesColor, useThemeVersion } from "../theme";
import type { LifetimeResult } from "../types";
import LineChart, { type Series } from "./LineChart";

const ACTIVITY_LABELS: Record<string, string> = {
  low: "Low (F10.7 70)",
  moderate: "Moderate (F10.7 150)",
  high: "High (F10.7 250)",
  cycle: "Solar-cycle model",
  custom: "Custom",
};

interface Props {
  yaml: string;
  disabled: boolean;
}

function fmtDate(date: Date) {
  return date.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
}

export default function LifetimeView({ yaml, disabled }: Props) {
  const [result, setResult] = useState<{ yaml: string; data: LifetimeResult } | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const themeVersion = useThemeVersion();

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setResult({ yaml, data: await estimateLifetime(yaml) });
    } catch (e) {
      setError(
        e instanceof ScenarioError
          ? "The scenario has problems; fix them in the editor first."
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setRunning(false);
    }
  };

  const charts = useMemo(() => {
    if (!result) return null;
    const d = result.data;
    const start = Date.parse(d.start) / 1000;
    const x = d.days.map((day) => start + day * 86400);
    const circular = d.days.every((_, i) => d.apogee_km[i] - d.perigee_km[i] < 2);
    const altitude: Series[] = circular
      ? [{ label: "Altitude", values: d.perigee_km.map((p, i) => (p + d.apogee_km[i]) / 2), color: seriesColor(0) }]
      : [
          { label: "Apogee", values: d.apogee_km, color: seriesColor(0) },
          { label: "Perigee", values: d.perigee_km, color: seriesColor(1) },
        ];
    return { x, altitude, flux: [{ label: "F10.7", values: d.f107, color: seriesColor(0) }] };
    // themeVersion: re-read series colors after a theme switch.
  }, [result, themeVersion]);

  const stale = result !== null && result.yaml !== yaml;
  const button = (
    <button type="button" className="primary" onClick={run} disabled={disabled || running}>
      {running ? "Estimating…" : result ? "Re-estimate" : "Estimate lifetime"}
    </button>
  );

  if (!result || !charts) {
    return (
      <div className="lifetime empty-state">
        <p>
          Follows the orbit's decay under atmospheric drag until re-entry, using the scenario's spacecraft
          (mass, drag area, Cd) and solar activity setting. Takes a few seconds.
        </p>
        {button}
        {error && <p className="field-error">{error}</p>}
      </div>
    );
  }

  const d = result.data;
  const start = new Date(d.start);
  const years = d.lifetime_days / 365.25;
  const reentry = new Date(start.getTime() + d.lifetime_days * 86400e3);

  return (
    <div className="lifetime">
      <div className="lifetime-summary">
        <div className="hero">
          <span className="hero-label">{d.reentered ? "Estimated re-entry" : "Still in orbit after"}</span>
          <span className="hero-value">{d.reentered ? fmtDate(reentry) : `${d.max_years} years`}</span>
          {d.reentered && (
            <span className="hero-sub">
              {years >= 1 ? `${years.toFixed(1)} years` : `${Math.round(d.lifetime_days)} days`} after{" "}
              {fmtDate(start)}
            </span>
          )}
        </div>
        <dl className="stat-tiles">
          <div>
            <dt>Start altitude</dt>
            <dd>{((d.perigee_km[0] + d.apogee_km[0]) / 2).toFixed(0)} km</dd>
          </div>
          <div>
            <dt>Ballistic coefficient</dt>
            <dd>{d.ballistic_coefficient.toFixed(4)} m²/kg</dd>
          </div>
          <div>
            <dt>Solar activity</dt>
            <dd>{ACTIVITY_LABELS[d.solar_activity] ?? d.solar_activity}</dd>
          </div>
        </dl>
        <div className="lifetime-actions">
          {stale && <span className="hint">Scenario changed since this estimate.</span>}
          {button}
        </div>
      </div>
      {error && <p className="field-error">{error}</p>}
      <div className="lifetime-charts">
        <LineChart
          title="Altitude"
          unit="km"
          decimals={1}
          x={charts.x}
          series={charts.altitude}
          threshold={d.reentry_altitude_km}
          syncKey="lifetime"
          timeScale="date"
        />
        <LineChart
          title="Solar flux F10.7"
          unit="sfu"
          decimals={0}
          x={charts.x}
          series={charts.flux}
          syncKey="lifetime"
          timeScale="date"
        />
      </div>
    </div>
  );
}
