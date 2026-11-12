import type { SimulationResult } from "../types";

function fmtBytes(bits: number): string {
  let size = bits / 8;
  for (const unit of ["B", "kB", "MB", "GB"]) {
    if (size < 1000 || unit === "GB") return `${size.toFixed(1)} ${unit}`;
    size /= 1000;
  }
  return "";
}

export default function Summary({ result }: { result: SimulationResult }) {
  const hours = result.scenario.simulation.duration_hours;
  return (
    <>
      <div className="section">
        <h2>Contact over {hours} h</h2>
        <table className="summary">
          <thead>
            <tr>
              <th>Station</th>
              <th>Passes</th>
              <th>Contact</th>
            </tr>
          </thead>
          <tbody>
            {result.scenario.ground_stations.map((gs) => {
              const passes = result.passes[gs.name] ?? [];
              const minutes = passes.reduce((s, p) => s + p.duration_s, 0) / 60;
              return (
                <tr key={gs.name}>
                  <td>{gs.name}</td>
                  <td>{passes.length}</td>
                  <td>{minutes.toFixed(1)} min</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {result.scenario.links.length > 0 && (
        <div className="section">
          <h2>Data volume</h2>
          <table className="summary">
            <thead>
              <tr>
                <th>Link</th>
                <th>Direction</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {result.scenario.links.map((link) => {
                const bits = result.link_passes
                  .filter((lp) => lp.link === link.name)
                  .reduce((s, lp) => s + lp.data_volume_bits, 0);
                return (
                  <tr key={link.name}>
                    <td>{link.name}</td>
                    <td>{link.direction}</td>
                    <td>{fmtBytes(bits)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
