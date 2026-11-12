import { useMemo } from "react";
import type { Document } from "yaml";
import type { ValidationIssue } from "../types";
import { editScenario, parseScenario, type Path } from "./doc";
import {
  CheckboxField,
  DateTimeField,
  FormContext,
  NumberField,
  Section,
  SelectField,
  TextField,
  type FormApi,
} from "./fields";
import { tumblingDragArea } from "./physics";
import AttitudeFields from "./AttitudeFields";
import LinksSection from "./LinksSection";
import OrbitSection from "./OrbitSection";
import StationsSection from "./StationsSection";

interface Props {
  yaml: string;
  onChange: (yaml: string) => void;
  issues: ValidationIssue[];
}

export default function ScenarioForm({ yaml, onChange, issues }: Props) {
  const parsed = useMemo(() => parseScenario(yaml), [yaml]);

  const api = useMemo<FormApi | null>(() => {
    if (!parsed.data) return null;
    const edit = (fn: (doc: Document) => void) => onChange(editScenario(yaml, fn));
    return {
      data: parsed.data,
      edit,
      set: (path: Path, value: unknown) =>
        edit((doc) => (value === undefined ? doc.deleteIn(path) : doc.setIn(path, value))),
      issues,
    };
  }, [parsed, yaml, onChange, issues]);

  const data = parsed.data ?? {};
  const spacecraft = (data.spacecraft ?? {}) as Record<string, unknown>;
  const defaultArea = tumblingDragArea(String(spacecraft.form_factor ?? "3U"));
  const drag = (data.drag ?? {}) as Record<string, unknown>;
  const numerical = (data.propagator ?? "j2") === "j2";

  if (!api) {
    return (
      <div className="form-blocked">
        <p>The YAML has a syntax error, so the form can't show it. Fix it in the YAML tab:</p>
        <pre>{parsed.error}</pre>
      </div>
    );
  }

  return (
    <FormContext.Provider value={api}>
      <div className="scenario-form">
        {issues.length > 0 && (
          <ul className="errors" aria-label="Problems">
            {issues.map((issue, i) => (
              <li key={i}>
                <span className="loc">{issue.loc}</span>
                <span>{issue.msg}</span>
              </li>
            ))}
          </ul>
        )}

        <Section title="Simulation">
          <TextField path={["name"]} label="Scenario name" wide />
          <DateTimeField path={["simulation", "start"]} label="Start" />
          <NumberField path={["simulation", "duration_hours"]} label="Duration" unit="h" />
          <NumberField
            path={["simulation", "step_seconds"]}
            label="Pass search step"
            unit="s"
            optional
            placeholder="30"
            hint="Passes shorter than this can be missed"
          />
          <NumberField
            path={["simulation", "link_step_seconds"]}
            label="Link sample step"
            unit="s"
            optional
            placeholder="5"
          />
        </Section>

        <Section title="Spacecraft">
          <TextField path={["spacecraft", "name"]} label="Name" wide />
          <SelectField
            path={["spacecraft", "form_factor"]}
            label="Form factor"
            options={["1U", "1.5U", "2U", "3U", "6U", "12U", "16U"].map((v) => ({ value: v, label: v }))}
          />
          <NumberField path={["spacecraft", "mass_kg"]} label="Mass" unit="kg" optional placeholder="4.0" />
          <NumberField
            path={["spacecraft", "drag_area_m2"]}
            label="Drag area"
            unit="m²"
            optional
            placeholder={defaultArea ? defaultArea.toFixed(4) : undefined}
            hint="Blank: tumbling average of the body"
          />
          <NumberField path={["spacecraft", "drag_coefficient"]} label="Drag coefficient" optional placeholder="2.2" />
          <AttitudeFields />
        </Section>

        <Section title="Propagation">
          <SelectField
            path={["atmosphere", "model"]}
            label="Atmosphere"
            options={[
              { value: "itu-r", label: "ITU-R (gas, cloud, rain, scintillation)" },
              { value: "none", label: "None (free space)" },
            ]}
          />
          <NumberField
            path={["atmosphere", "availability_percent"]}
            label="Link availability"
            unit="%"
            optional
            placeholder="99"
            hint="Losses not exceeded for this % of an average year (95-99.999)"
          />
          <CheckboxField
            path={["drag", "enabled"]}
            label="Atmospheric drag (NRLMSIS 2.1)"
            disabled={!numerical}
            hint={
              numerical
                ? "Slows and lowers the orbit; also sets solar activity for lifetime estimates."
                : "Needs the numerical (J2) propagator; SGP4 models drag through the TLE."
            }
          />
          <SelectField
            path={["drag", "solar_activity"]}
            label="Solar activity"
            options={[
              { value: "moderate", label: "Moderate (F10.7 150)" },
              { value: "low", label: "Low (F10.7 70)" },
              { value: "high", label: "High (F10.7 250)" },
              { value: "cycle", label: "Solar-cycle model" },
              { value: "custom", label: "Custom" },
            ]}
          />
          {drag.solar_activity === "custom" && (
            <>
              <NumberField path={["drag", "f107"]} label="F10.7" unit="sfu" />
              <NumberField path={["drag", "ap"]} label="Ap index" />
            </>
          )}
        </Section>

        <OrbitSection />
        <StationsSection />
        <LinksSection />
      </div>
    </FormContext.Provider>
  );
}
