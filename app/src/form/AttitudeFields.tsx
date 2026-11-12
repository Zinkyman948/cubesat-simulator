import type { Document } from "yaml";
import { isSeq } from "yaml";
import { getIn, type Path } from "./doc";
import { NumberField, useForm } from "./fields";

const BASE: Path = ["spacecraft", "attitude"];

const MODES = [
  { value: "nadir", label: "Nadir (+Z toward Earth)" },
  { value: "target", label: "Track ground station" },
  { value: "sun", label: "Sun-pointing (+Z toward Sun)" },
  { value: "inertial", label: "Inertial (fixed in space)" },
  { value: "spin", label: "Spinning" },
];

const HINTS: Record<string, string> = {
  nadir: "+X along the velocity, +Y opposite the orbit normal.",
  target: "+Z at the highest visible ground station; nadir otherwise.",
  sun: "+X as close as possible to the orbit normal.",
  inertial: "+Z fixed along a direction in the inertial (GCRS) frame.",
  spin: "+Z fixed along the spin axis, rotating about it.",
};

/** Set a 3-vector as a compact [x, y, z] flow list. */
export function setVector(doc: Document, path: Path, value: number[]) {
  const node = doc.createNode(value);
  if (isSeq(node)) node.flow = true;
  doc.setIn(path, node);
}

export function VectorField({ path, label, hint }: { path: Path; label: string; hint?: string }) {
  return (
    <div className="field wide">
      <span className="label">{label}</span>
      <div className="vector">
        {["x", "y", "z"].map((c, i) => (
          <NumberField key={c} path={[...path, i]} label={c} />
        ))}
      </div>
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  );
}

export default function AttitudeFields() {
  const { data, edit } = useForm();
  const mode = (getIn(data, [...BASE, "mode"]) as string | undefined) ?? "nadir";

  const setMode = (next: string) =>
    edit((doc) => {
      doc.setIn([...BASE, "mode"], next);
      for (const key of ["pointing", "spin_axis", "spin_rate_deg_s"]) {
        const keep =
          (next === "inertial" && key === "pointing") || (next === "spin" && key !== "pointing");
        if (!keep) doc.deleteIn([...BASE, key]);
      }
      if (next === "inertial" && !doc.hasIn([...BASE, "pointing"])) setVector(doc, [...BASE, "pointing"], [1, 0, 0]);
      if (next === "spin") {
        if (!doc.hasIn([...BASE, "spin_axis"])) setVector(doc, [...BASE, "spin_axis"], [0, 0, 1]);
        if (!doc.hasIn([...BASE, "spin_rate_deg_s"])) doc.setIn([...BASE, "spin_rate_deg_s"], 2);
      }
    });

  return (
    <>
      <div className="field wide">
        <label htmlFor="attitude-mode">Attitude</label>
        <div className="control">
          <select id="attitude-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <span className="field-hint">{HINTS[mode]}</span>
      </div>
      {mode === "inertial" && (
        <VectorField path={[...BASE, "pointing"]} label="+Z direction (GCRS)" />
      )}
      {mode === "spin" && (
        <>
          <VectorField path={[...BASE, "spin_axis"]} label="Spin axis (GCRS)" />
          <NumberField path={[...BASE, "spin_rate_deg_s"]} label="Spin rate" unit="°/s" hint="Lower the link sample step for fast spins" />
        </>
      )}
    </>
  );
}

