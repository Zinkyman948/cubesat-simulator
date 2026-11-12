import { useMemo } from "react";
import type { PassRef, SimulationResult } from "../types";

interface Props {
  result: SimulationResult;
  selected: PassRef | null;
  onSelect: (pass: PassRef) => void;
}

const fmtTime = (iso: string) => iso.slice(5, 19).replace("T", " ");

export default function PassTable({ result, selected, onSelect }: Props) {
  const rows = useMemo(() => {
    const all: PassRef[] = [];
    for (const [station, passes] of Object.entries(result.passes)) {
      passes.forEach((pass, index) => all.push({ station, index, pass }));
    }
    return all.sort((a, b) => a.pass.aos.localeCompare(b.pass.aos));
  }, [result]);

  return (
    <div className="passes">
      <div className="section">
        <h2>Passes ({rows.length})</h2>
      </div>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Station</th>
              <th>AOS (UTC)</th>
              <th>Duration</th>
              <th>Max el.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const isSelected = selected?.station === r.station && selected.index === r.index;
              return (
                <tr
                  key={`${r.station}-${r.index}`}
                  className={isSelected ? "selected" : undefined}
                  onClick={() => onSelect(r)}
                >
                  <td>{r.station}</td>
                  <td>
                    {fmtTime(r.pass.aos)}
                    {r.pass.truncated_start || r.pass.truncated_end ? " *" : ""}
                  </td>
                  <td>{(r.pass.duration_s / 60).toFixed(1)} min</td>
                  <td>{r.pass.max_elevation_deg.toFixed(1)}°</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
