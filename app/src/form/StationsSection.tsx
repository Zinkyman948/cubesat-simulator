import { isSeq, type Document } from "yaml";
import type { GroundStationConfig, LinkConfig } from "../types";
import { NumberField, Section, TextField, useForm } from "./fields";

/** Apply `fn` to every link's explicit station list. */
function forEachLinkStations(doc: Document, links: LinkConfig[], fn: (names: string[]) => string[]) {
  links.forEach((link, i) => {
    if (!Array.isArray(link.stations)) return;
    const node = doc.getIn(["links", i, "stations"]);
    const next = fn(link.stations);
    const created = doc.createNode(next);
    // Keep the list's original style (e.g. [A, B] on one line).
    if (isSeq(node) && isSeq(created)) created.flow = node.flow;
    doc.setIn(["links", i, "stations"], created);
  });
}

export default function StationsSection() {
  const { data, edit } = useForm();
  const stations = (Array.isArray(data.ground_stations) ? data.ground_stations : []) as GroundStationConfig[];
  const links = (Array.isArray(data.links) ? data.links : []) as LinkConfig[];

  const rename = (index: number) => (from: string, to: string) =>
    edit((doc) => {
      doc.setIn(["ground_stations", index, "name"], to);
      // Links refer to stations by name; keep those references pointing here.
      forEachLinkStations(doc, links, (names) => names.map((n) => (n === from ? to : n)));
    });

  const remove = (index: number) =>
    edit((doc) => {
      const name = stations[index]?.name;
      doc.deleteIn(["ground_stations", index]);
      forEachLinkStations(doc, links, (names) => names.filter((n) => n !== name));
    });

  const add = () =>
    edit((doc) => {
      let n = stations.length + 1;
      const names = new Set(stations.map((s) => s.name));
      while (names.has(`Station ${n}`)) n++;
      const station = {
        name: `Station ${n}`,
        latitude_deg: 0,
        longitude_deg: 0,
        altitude_m: 0,
        min_elevation_deg: 10,
      };
      if (doc.hasIn(["ground_stations"])) doc.addIn(["ground_stations"], station);
      else doc.setIn(["ground_stations"], [station]);
    });

  return (
    <Section title={`Ground stations (${stations.length})`}>
      {stations.map((s, i) => (
        <div className="item-card wide" key={i}>
          <div className="item-card-head">
            <TextField path={["ground_stations", i, "name"]} label="Name" wide onRename={rename(i)} />
            <button
              type="button"
              className="icon-button"
              onClick={() => remove(i)}
              disabled={stations.length <= 1}
              title={stations.length <= 1 ? "A scenario needs at least one ground station" : `Remove ${s.name}`}
              aria-label={`Remove ${s.name}`}
            >
              ×
            </button>
          </div>
          <div className="form-grid">
            <NumberField path={["ground_stations", i, "latitude_deg"]} label="Latitude" unit="°" />
            <NumberField path={["ground_stations", i, "longitude_deg"]} label="Longitude" unit="°" />
            <NumberField path={["ground_stations", i, "altitude_m"]} label="Altitude" unit="m" />
            <NumberField path={["ground_stations", i, "min_elevation_deg"]} label="Min. elevation" unit="°" />
          </div>
        </div>
      ))}
      <button type="button" className="add-button wide" onClick={add}>
        + Add ground station
      </button>
    </Section>
  );
}
