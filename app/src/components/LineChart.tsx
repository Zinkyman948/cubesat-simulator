import { useEffect, useRef, type ReactNode } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { cssVar, useThemeVersion } from "../theme";

export interface Series {
  label: string;
  values: number[];
  color: string;
}

interface Props {
  title: ReactNode;
  unit: string;
  decimals: number;
  x: number[]; // unix seconds
  series: Series[];
  /** Horizontal reference line, e.g. 0 dB margin. */
  threshold?: number;
  syncKey: string;
}

function fmtUtc(ts: number, withSeconds = true) {
  return new Date(ts * 1000).toISOString().slice(11, withSeconds ? 19 : 16);
}

export default function LineChart({ title, unit, decimals, x, series, threshold, syncKey }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const themeVersion = useThemeVersion();

  useEffect(() => {
    const el = host.current;
    if (!el) return;

    const muted = cssVar("--text-muted");
    const grid = cssVar("--grid");
    const axisFont = "11px system-ui, sans-serif";
    const axis: uPlot.Axis = {
      stroke: muted,
      font: axisFont,
      grid: { stroke: grid, width: 1 },
      ticks: { stroke: grid, width: 1, size: 4 },
    };

    // Direct end-labels in text ink (never the series color), skipped when
    // they would collide with one already drawn.
    const drawEndLabels = (u: uPlot) => {
      if (series.length < 2) return;
      const ctx = u.ctx;
      const placed: number[] = [];
      ctx.save();
      ctx.font = `${11 * devicePixelRatio}px system-ui, sans-serif`;
      ctx.fillStyle = cssVar("--text-secondary");
      ctx.textAlign = "right";
      ctx.textBaseline = "bottom";
      series.forEach((s, i) => {
        const last = s.values[s.values.length - 1];
        if (last == null) return;
        const yPos = u.valToPos(last, "y", true) - 4 * devicePixelRatio;
        if (placed.some((p) => Math.abs(p - yPos) < 14 * devicePixelRatio)) return;
        placed.push(yPos);
        ctx.fillText(series[i].label, u.bbox.left + u.bbox.width - 2, yPos);
      });
      ctx.restore();
    };

    const drawThreshold = (u: uPlot) => {
      if (threshold == null) return;
      const y = u.valToPos(threshold, "y", true);
      if (y < u.bbox.top || y > u.bbox.top + u.bbox.height) return;
      const ctx = u.ctx;
      ctx.save();
      ctx.strokeStyle = cssVar("--axis");
      ctx.lineWidth = devicePixelRatio;
      ctx.beginPath();
      ctx.moveTo(u.bbox.left, y);
      ctx.lineTo(u.bbox.left + u.bbox.width, y);
      ctx.stroke();
      ctx.restore();
    };

    const opts: uPlot.Options = {
      width: el.clientWidth,
      height: 100, // resized to fit once the readout's height is known
      scales: { x: { time: true } },
      tzDate: (ts) => uPlot.tzDate(new Date(ts * 1000), "Etc/UTC"),
      cursor: {
        sync: { key: syncKey },
        y: false,
        points: { size: 8, width: 2, stroke: cssVar("--surface") },
      },
      legend: { live: true },
      axes: [
        { ...axis, values: (_u, splits) => splits.map((ts) => fmtUtc(ts, false)) },
        { ...axis, size: 48, space: 22 },
      ],
      series: [
        { label: "UTC", value: (_u, v) => (v == null ? "--" : fmtUtc(v)) },
        ...series.map<uPlot.Series>((s) => ({
          label: s.label,
          stroke: s.color,
          width: 2,
          points: { show: false },
          value: (_u, v) => (v == null ? "--" : `${v.toFixed(decimals)} ${unit}`),
        })),
      ],
      hooks: { draw: [drawThreshold, drawEndLabels] },
    };

    const plot = new uPlot(opts, [x, ...series.map((s) => s.values)], el);
    // The live readout (uPlot's legend) sits under the plot and can wrap,
    // so size the canvas to whatever space it leaves.
    const fit = () => {
      const legend = plot.root.querySelector<HTMLElement>(".u-legend");
      const height = Math.max(60, el.clientHeight - (legend?.offsetHeight ?? 0) - 4);
      plot.setSize({ width: el.clientWidth, height });
    };
    fit();
    const resize = new ResizeObserver(fit);
    resize.observe(el);
    // The readout re-wraps as values change while hovering.
    const legend = plot.root.querySelector(".u-legend");
    if (legend) resize.observe(legend);
    return () => {
      resize.disconnect();
      plot.destroy();
    };
  }, [x, series, unit, decimals, threshold, syncKey, themeVersion]);

  return (
    <div className={series.length > 1 ? "chart multi" : "chart"}>
      <h3>{title}</h3>
      <div className="plot" ref={host} />
    </div>
  );
}
