import { useMemo, useState } from "react";
import { load, save } from "../storage";
import { seriesColor, useThemeVersion } from "../theme";
import type { LinkPass, PassRef, SimulationResult } from "../types";
import LineChart, { type Series } from "./LineChart";

// Choices for the second chart. "range" is pass geometry (one line); the
// others are per link.
const METRICS = {
  range: { label: "Slant range", unit: "km", decimals: 0, pick: null },
  gain: {
    label: "Spacecraft antenna gain",
    unit: "dBi",
    decimals: 1,
    pick: (lp: LinkPass) => lp.series.sc_antenna_gain_dbi,
  },
  angle: {
    label: "Off-boresight angle",
    unit: "°",
    decimals: 1,
    pick: (lp: LinkPass) => lp.series.sc_antenna_angle_deg,
  },
  power: {
    label: "Received power",
    unit: "dBm",
    decimals: 1,
    pick: (lp: LinkPass) => lp.series.received_power_dbm,
  },
  ebn0: { label: "Eb/N0", unit: "dB", decimals: 1, pick: (lp: LinkPass) => lp.series.ebn0_db },
  atmosphere: {
    label: "Atmospheric loss",
    unit: "dB",
    decimals: 2,
    pick: (lp: LinkPass) => lp.series.atmospheric_loss_db,
  },
  rain: { label: "Rain attenuation", unit: "dB", decimals: 2, pick: (lp: LinkPass) => lp.series.rain_loss_db },
  noise: {
    label: "System noise temperature",
    unit: "K",
    decimals: 0,
    pick: (lp: LinkPass) => lp.series.system_noise_temp_k,
  },
  pathLoss: {
    label: "Free-space path loss",
    unit: "dB",
    decimals: 1,
    pick: (lp: LinkPass) => lp.series.path_loss_db,
  },
  dopplerRate: {
    label: "Doppler rate",
    unit: "Hz/s",
    decimals: 1,
    pick: (lp: LinkPass) => lp.series.doppler_rate_hz_s,
  },
} as const;
type Metric = keyof typeof METRICS;

interface Props {
  result: SimulationResult;
  selected: PassRef | null;
}

export default function PassCharts({ result, selected }: Props) {
  const themeVersion = useThemeVersion();
  const [metric, setMetric] = useState<Metric>(() => {
    const stored = load("chart-metric");
    return stored && stored in METRICS ? (stored as Metric) : "range";
  });
  const chooseMetric = (m: Metric) => {
    setMetric(m);
    save("chart-metric", m);
  };

  const data = useMemo(() => {
    if (!selected) return null;
    const links = result.scenario.links;
    const linkPasses = result.link_passes.filter(
      (lp) => lp.station === selected.station && lp.pass_index === selected.index,
    );
    if (linkPasses.length === 0) return { x: [], geometry: null, doppler: [], margin: [], second: [] };

    // All links share one pass geometry; use the first for the time axis.
    const base = linkPasses[0].series;
    const x = base.utc.map((t) => Date.parse(t) / 1000);
    const perLink = (pick: (lp: (typeof linkPasses)[number]) => number[]): Series[] =>
      linkPasses.map((lp) => ({
        label: lp.link,
        values: pick(lp),
        color: seriesColor(links.findIndex((l) => l.name === lp.link)),
      }));
    const single = (label: string, values: number[]): Series[] => [
      { label, values, color: seriesColor(0) },
    ];

    const pick = METRICS[metric].pick;
    return {
      x,
      geometry: { elevation: single("Elevation", base.elevation_deg) },
      second: pick ? perLink(pick) : single("Range", base.range_km),
      doppler: perLink((lp) => lp.series.doppler_hz.map((d) => d / 1000)),
      margin: perLink((lp) => lp.series.margin_db),
    };
    // themeVersion is a dependency so series colors are re-read after a theme switch.
  }, [result, selected, metric, themeVersion]);

  if (!selected || !data) {
    return <div className="charts"><p className="empty">Select a pass to see its link performance.</p></div>;
  }
  const p = selected.pass;
  const header = (
    <div className="charts-header">
      <h2>
        {selected.station} - pass {selected.index + 1}
      </h2>
      <span className="hint">
        {p.aos.slice(0, 19).replace("T", " ")} UTC · {(p.duration_s / 60).toFixed(1)} min · max
        elevation {p.max_elevation_deg.toFixed(1)}°
      </span>
    </div>
  );

  if (!data.geometry) {
    return (
      <div className="charts">
        {header}
        <p className="empty">No links are defined for this station. Add a links: section to the scenario.</p>
      </div>
    );
  }

  const key = `${selected.station}-${selected.index}`;
  return (
    <div className="charts">
      {header}
      <div className="chart-grid">
        <LineChart title="Elevation" unit="°" decimals={1} x={data.x} series={data.geometry.elevation} syncKey={key} />
        <LineChart
          title={
            <select
              className="chart-select"
              value={metric}
              onChange={(e) => chooseMetric(e.target.value as Metric)}
              aria-label="Second chart"
            >
              {Object.entries(METRICS).map(([k, m]) => (
                <option key={k} value={k}>
                  {m.label}
                </option>
              ))}
            </select>
          }
          unit={METRICS[metric].unit}
          decimals={METRICS[metric].decimals}
          x={data.x}
          series={data.second}
          syncKey={key}
        />
        <LineChart title="Doppler shift" unit="kHz" decimals={2} x={data.x} series={data.doppler} syncKey={key} />
        <LineChart title="Link margin" unit="dB" decimals={1} x={data.x} series={data.margin} threshold={0} syncKey={key} />
      </div>
    </div>
  );
}
