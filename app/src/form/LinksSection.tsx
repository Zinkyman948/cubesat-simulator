import { isSeq } from "yaml";
import type { GroundStationConfig } from "../types";
import { getIn, type Path } from "./doc";
import { setVector } from "./AttitudeFields";
import { NumberField, Section, Segmented, SelectField, TextField, useForm } from "./fields";

const MODULATIONS = [
  { value: "bpsk", label: "BPSK" },
  { value: "qpsk", label: "QPSK" },
  { value: "8psk", label: "8PSK" },
  { value: "gmsk", label: "GMSK" },
  { value: "bfsk_coherent", label: "BFSK (coherent)" },
  { value: "bfsk_noncoherent", label: "BFSK (non-coherent)" },
];

// Starting points matching the demo scenario's links.
const TEMPLATES: Record<string, { label: string; link: Record<string, unknown> }> = {
  uhf: {
    label: "UHF telemetry downlink",
    link: {
      name: "UHF telemetry",
      direction: "downlink",
      frequency_mhz: 437.5,
      data_rate_bps: 9600,
      modulation: "gmsk",
      transmitter: { power_w: 1.0, line_loss_db: 0.5, antenna: { pattern: "turnstile", axis: [0, 0, 1] } },
      receiver: {
        antenna: { gain_dbi: 14.0 },
        antenna_noise_temp_k: 500,
        noise_figure_db: 1.0,
        line_loss_db: 0.5,
      },
      losses: { polarization_db: 3.0, pointing_db: 1.0, implementation_db: 1.5, atmospheric_zenith_db: 0.1 },
    },
  },
  sband: {
    label: "S-band payload downlink",
    link: {
      name: "S-band payload",
      direction: "downlink",
      frequency_mhz: 2245,
      data_rate_bps: 5000000,
      modulation: "qpsk",
      coding: { gain_db: 5.0, rate: 0.5 },
      transmitter: { power_w: 2.0, line_loss_db: 1.0, antenna: { pattern: "cosine", gain_dbi: 6.0, axis: [0, 0, 1] } },
      receiver: {
        antenna: { dish_diameter_m: 3.7, dish_efficiency: 0.55 },
        antenna_noise_temp_k: 80,
        noise_figure_db: 0.8,
        line_loss_db: 0.3,
      },
      losses: { polarization_db: 0.5, pointing_db: 0.5, implementation_db: 2.0, atmospheric_zenith_db: 0.05 },
    },
  },
  vhf: {
    label: "VHF command uplink",
    link: {
      name: "VHF command",
      direction: "uplink",
      frequency_mhz: 145.9,
      data_rate_bps: 1200,
      modulation: "bfsk_noncoherent",
      transmitter: { power_w: 50.0, line_loss_db: 2.0, antenna: { gain_dbi: 12.0 } },
      receiver: {
        antenna: { pattern: "dipole", axis: [0, 1, 0] },
        antenna_noise_temp_k: 1000,
        noise_figure_db: 2.0,
        line_loss_db: 0.5,
      },
      losses: { polarization_db: 3.0, pointing_db: 1.0, implementation_db: 3.0, atmospheric_zenith_db: 0.1 },
    },
  },
};

const PATTERNS = [
  { value: "isotropic", label: "Isotropic" },
  { value: "cosine", label: "Patch (cosine)" },
  { value: "turnstile", label: "Turnstile (crossed dipoles)" },
  { value: "dipole", label: "Dipole / monopole" },
  { value: "dish", label: "Dish" },
];

const AXES: { value: string; label: string; vector: number[] }[] = [
  { value: "+z", label: "+Z (nadir face)", vector: [0, 0, 1] },
  { value: "-z", label: "-Z (zenith face)", vector: [0, 0, -1] },
  { value: "+x", label: "+X (along-track)", vector: [1, 0, 0] },
  { value: "-x", label: "-X", vector: [-1, 0, 0] },
  { value: "+y", label: "+Y", vector: [0, 1, 0] },
  { value: "-y", label: "-Y", vector: [0, -1, 0] },
];

/** Ground antennas track the spacecraft, so only their peak gain matters. */
function GroundAntennaFields({ path, side }: { path: Path; side: string }) {
  const { data, edit } = useForm();
  const isDish = typeof getIn(data, [...path, "dish_diameter_m"]) === "number";
  return (
    <>
      <Segmented
        label={`${side} antenna`}
        value={isDish ? "dish" : "gain"}
        options={[
          { value: "gain", label: "Fixed gain" },
          { value: "dish", label: "Parabolic dish" },
        ]}
        onChange={(mode) =>
          edit((doc) => {
            for (const k of ["pattern", "axis", "gain_dbi", "dish_diameter_m", "dish_efficiency"]) {
              doc.deleteIn([...path, k]);
            }
            if (mode === "dish") {
              doc.setIn([...path, "dish_diameter_m"], 1.0);
              doc.setIn([...path, "dish_efficiency"], 0.55);
            } else {
              doc.setIn([...path, "gain_dbi"], 0.0);
            }
          })
        }
      />
      {isDish ? (
        <>
          <NumberField path={[...path, "dish_diameter_m"]} label="Dish diameter" unit="m" />
          <NumberField path={[...path, "dish_efficiency"]} label="Aperture efficiency" optional placeholder="0.55" />
        </>
      ) : (
        <NumberField path={[...path, "gain_dbi"]} label="Antenna gain" unit="dBi" />
      )}
    </>
  );
}

/** Spacecraft antennas: a radiation pattern mounted along a body axis. */
function SpacecraftAntennaFields({ path }: { path: Path }) {
  const { data, edit } = useForm();
  const antenna = (getIn(data, path) ?? {}) as Record<string, unknown>;
  const pattern =
    typeof antenna.pattern === "string"
      ? antenna.pattern
      : typeof antenna.dish_diameter_m === "number"
        ? "dish"
        : "isotropic";
  const axis = Array.isArray(antenna.axis) ? (antenna.axis as number[]) : [0, 0, 1];
  const axisKey = AXES.find((a) => a.vector.every((c, i) => c === axis[i]))?.value ?? "custom";

  const setPattern = (next: string) =>
    edit((doc) => {
      doc.setIn([...path, "pattern"], next);
      if (next !== "dish") {
        doc.deleteIn([...path, "dish_diameter_m"]);
        doc.deleteIn([...path, "dish_efficiency"]);
      }
      if (next === "isotropic" || next === "cosine") {
        const gain = typeof antenna.gain_dbi === "number" ? antenna.gain_dbi : null;
        if (next === "cosine" && (gain === null || gain < 3.0103)) doc.setIn([...path, "gain_dbi"], 6.0);
        if (next === "isotropic" && gain === null) doc.setIn([...path, "gain_dbi"], 0.0);
      } else {
        doc.deleteIn([...path, "gain_dbi"]);
      }
      if (next === "dish") {
        doc.setIn([...path, "dish_diameter_m"], 0.5);
        doc.setIn([...path, "dish_efficiency"], 0.55);
      }
    });

  return (
    <>
      <div className="field">
        <label htmlFor={`${path.join("-")}-pattern`}>Spacecraft antenna</label>
        <div className="control">
          <select id={`${path.join("-")}-pattern`} value={pattern} onChange={(e) => setPattern(e.target.value)}>
            {PATTERNS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      {pattern !== "isotropic" && (
        <div className="field">
          <label htmlFor={`${path.join("-")}-axis`}>{pattern === "dipole" ? "Element along" : "Boresight"}</label>
          <div className="control">
            <select
              id={`${path.join("-")}-axis`}
              value={axisKey}
              onChange={(e) => {
                const choice = AXES.find((a) => a.value === e.target.value);
                if (choice) edit((doc) => setVector(doc, [...path, "axis"], choice.vector));
              }}
            >
              {AXES.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
              {axisKey === "custom" && (
                <option value="custom" disabled>
                  [{axis.join(", ")}] (from YAML)
                </option>
              )}
            </select>
          </div>
        </div>
      )}
      {(pattern === "isotropic" || pattern === "cosine") && (
        <NumberField
          path={[...path, "gain_dbi"]}
          label={pattern === "cosine" ? "Peak gain" : "Antenna gain"}
          unit="dBi"
          hint={pattern === "cosine" ? "At least 3.01 dBi; sets the beam width" : undefined}
        />
      )}
      {pattern === "dish" && (
        <>
          <NumberField path={[...path, "dish_diameter_m"]} label="Dish diameter" unit="m" />
          <NumberField path={[...path, "dish_efficiency"]} label="Aperture efficiency" optional placeholder="0.55" />
        </>
      )}
      {(pattern === "turnstile" || pattern === "dipole") && (
        <span className="field-hint wide">
          {pattern === "turnstile"
            ? "1.76 dBi along the boresight, -1.25 dBi sideways."
            : "2.15 dBi broadside, nulls along the element."}
        </span>
      )}
    </>
  );
}

function ReceiverNoise({ path }: { path: Path }) {
  const { data, edit } = useForm();
  const direct = typeof getIn(data, [...path, "system_noise_temp_k"]) === "number";
  return (
    <>
      <Segmented
        label="Receiver noise"
        value={direct ? "system" : "chain"}
        options={[
          { value: "chain", label: "Noise figure" },
          { value: "system", label: "System temp." },
        ]}
        onChange={(mode) =>
          edit((doc) => {
            if (mode === "system") {
              for (const k of ["antenna_noise_temp_k", "noise_figure_db", "line_loss_db"]) doc.deleteIn([...path, k]);
              doc.setIn([...path, "system_noise_temp_k"], 500);
            } else {
              doc.deleteIn([...path, "system_noise_temp_k"]);
              doc.setIn([...path, "antenna_noise_temp_k"], 290);
              doc.setIn([...path, "noise_figure_db"], 1.0);
            }
          })
        }
      />
      {direct ? (
        <NumberField
          path={[...path, "system_noise_temp_k"]}
          label="System noise temp."
          unit="K"
          hint="At the antenna terminals, including line losses"
        />
      ) : (
        <>
          <NumberField path={[...path, "antenna_noise_temp_k"]} label="Antenna noise temp." unit="K" />
          <NumberField path={[...path, "noise_figure_db"]} label="LNA noise figure" unit="dB" />
          <NumberField path={[...path, "line_loss_db"]} label="Line loss (before LNA)" unit="dB" optional placeholder="0" />
        </>
      )}
    </>
  );
}

function StationPicker({ index, stations }: { index: number; stations: GroundStationConfig[] }) {
  const { data, edit } = useForm();
  const selected = getIn(data, ["links", index, "stations"]);
  const all = !Array.isArray(selected);
  const chosen = new Set(Array.isArray(selected) ? (selected as string[]) : []);

  const setList = (names: string[] | null) =>
    edit((doc) => {
      if (names === null) doc.deleteIn(["links", index, "stations"]);
      else {
        const node = doc.createNode(names);
        if (isSeq(node)) node.flow = true; // [A, B] on one line
        doc.setIn(["links", index, "stations"], node);
      }
    });

  return (
    <div className="field wide">
      <span className="label">Ground stations</span>
      <div className="checks">
        <label>
          <input
            type="checkbox"
            checked={all}
            onChange={(e) => setList(e.target.checked ? null : stations.map((s) => s.name))}
          />
          All
        </label>
        {stations.map((s) => (
          <label key={s.name}>
            <input
              type="checkbox"
              disabled={all}
              checked={all || chosen.has(s.name)}
              onChange={(e) => {
                const next = new Set(chosen);
                if (e.target.checked) next.add(s.name);
                else next.delete(s.name);
                // Keep the scenario's station order.
                setList(stations.map((st) => st.name).filter((n) => next.has(n)));
              }}
            />
            {s.name}
          </label>
        ))}
      </div>
    </div>
  );
}

function LinkCard({ index, stations }: { index: number; stations: GroundStationConfig[] }) {
  const { data, edit } = useForm();
  const link = (getIn(data, ["links", index]) ?? {}) as Record<string, unknown>;
  const base: Path = ["links", index];
  const downlink = link.direction !== "uplink";
  const [txSide, rxSide] = downlink ? ["Spacecraft", "Ground"] : ["Ground", "Spacecraft"];
  const summary = [link.direction, typeof link.frequency_mhz === "number" ? `${link.frequency_mhz} MHz` : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <details className="item-card link-card wide">
      <summary>
        <span className="link-name">{String(link.name ?? `Link ${index + 1}`)}</span>
        <span className="link-meta">{summary}</span>
      </summary>
      <div className="form-grid">
        <TextField path={[...base, "name"]} label="Name" wide />
        <SelectField
          path={[...base, "direction"]}
          label="Direction"
          options={[
            { value: "downlink", label: "Downlink" },
            { value: "uplink", label: "Uplink" },
          ]}
        />
        <NumberField path={[...base, "frequency_mhz"]} label="Frequency" unit="MHz" />
        <NumberField path={[...base, "data_rate_bps"]} label="Data rate" unit="bit/s" />
        <SelectField path={[...base, "modulation"]} label="Modulation" options={MODULATIONS} />
        <NumberField path={[...base, "coding", "gain_db"]} label="Coding gain" unit="dB" optional placeholder="0" />
        <NumberField path={[...base, "coding", "rate"]} label="Code rate" optional placeholder="1" />
        <NumberField path={[...base, "target_ber"]} label="Target BER" optional placeholder="1e-5" />

        <h4 className="wide">Transmitter ({txSide.toLowerCase()})</h4>
        <NumberField path={[...base, "transmitter", "power_w"]} label="Power" unit="W" />
        <NumberField path={[...base, "transmitter", "line_loss_db"]} label="Line loss" unit="dB" optional placeholder="0" />
        {downlink ? (
          <SpacecraftAntennaFields path={[...base, "transmitter", "antenna"]} />
        ) : (
          <GroundAntennaFields path={[...base, "transmitter", "antenna"]} side={txSide} />
        )}

        <h4 className="wide">Receiver ({rxSide.toLowerCase()})</h4>
        {downlink ? (
          <GroundAntennaFields path={[...base, "receiver", "antenna"]} side={rxSide} />
        ) : (
          <SpacecraftAntennaFields path={[...base, "receiver", "antenna"]} />
        )}
        <ReceiverNoise path={[...base, "receiver"]} />

        <h4 className="wide">Losses</h4>
        <NumberField path={[...base, "losses", "polarization_db"]} label="Polarization" unit="dB" optional placeholder="0" />
        <NumberField path={[...base, "losses", "pointing_db"]} label="Pointing" unit="dB" optional placeholder="0" />
        <NumberField path={[...base, "losses", "implementation_db"]} label="Implementation" unit="dB" optional placeholder="1" />
        <NumberField
          path={[...base, "losses", "atmospheric_zenith_db"]}
          label="Atmosphere at zenith"
          unit="dB"
          optional
          placeholder="0"
        />

        <StationPicker index={index} stations={stations} />

        <button type="button" className="danger-button wide" onClick={() => edit((doc) => doc.deleteIn(["links", index]))}>
          Remove this link
        </button>
      </div>
    </details>
  );
}

export default function LinksSection() {
  const { data, edit } = useForm();
  const links = Array.isArray(data.links) ? data.links : [];
  const stations = (Array.isArray(data.ground_stations) ? data.ground_stations : []) as GroundStationConfig[];

  const addFromTemplate = (key: string) =>
    edit((doc) => {
      const template = structuredClone(TEMPLATES[key].link);
      // Link names must be unique.
      const names = new Set(links.map((l) => (l as { name?: string }).name));
      let name = template.name as string;
      for (let n = 2; names.has(name); n++) name = `${template.name} ${n}`;
      template.name = name;
      if (doc.hasIn(["links"])) doc.addIn(["links"], template);
      else doc.setIn(["links"], [template]);
    });

  return (
    <Section title={`Radio links (${links.length})`}>
      {links.length === 0 && <p className="field-hint wide">No links: only passes are computed.</p>}
      {links.map((_, i) => (
        <LinkCard key={i} index={i} stations={stations} />
      ))}
      <select
        className="add-button wide"
        value=""
        onChange={(e) => e.target.value && addFromTemplate(e.target.value)}
        aria-label="Add a link"
      >
        <option value="">+ Add link from template…</option>
        {Object.entries(TEMPLATES).map(([key, t]) => (
          <option key={key} value={key}>
            {t.label}
          </option>
        ))}
      </select>
    </Section>
  );
}
