import { useRef } from "react";
import { getIn } from "./doc";
import { DateTimeField, NumberField, Section, Segmented, SelectField, TextField, useForm } from "./fields";
import { R_EARTH, periodMinutes, sunSynchronousInclination } from "./physics";

type OrbitType = "keplerian" | "tle";
type SizeMode = "altitude" | "sma";

const DEFAULT_KEPLERIAN = {
  type: "keplerian",
  altitude_km: 500,
  eccentricity: 0.001,
  inclination_deg: 97.4,
  raan_deg: 0,
  arg_perigee_deg: 0,
  true_anomaly_deg: 0,
};

const DEFAULT_TLE = {
  type: "tle",
  line1: "1 25544U 98067A   14020.93268519  .00009878  00000-0  18200-3 0  5082",
  line2: "2 25544  51.6498 109.4756 0003572  55.9686 274.8005 15.49815350868473",
};

function DerivedOrbit() {
  const { data, set } = useForm();
  const orbit = (data.orbit ?? {}) as Record<string, unknown>;
  const e = typeof orbit.eccentricity === "number" ? orbit.eccentricity : 0;
  const a =
    typeof orbit.semi_major_axis_km === "number"
      ? orbit.semi_major_axis_km
      : typeof orbit.altitude_km === "number"
        ? R_EARTH + orbit.altitude_km
        : null;
  if (a === null || !(a > 0) || e < 0 || e >= 1) return null;
  const sso = sunSynchronousInclination(a, e);

  return (
    <div className="derived wide">
      <dl>
        <dt>Period</dt>
        <dd>{periodMinutes(a).toFixed(1)} min</dd>
        <dt>Perigee</dt>
        <dd>{(a * (1 - e) - R_EARTH).toFixed(1)} km</dd>
        <dt>Apogee</dt>
        <dd>{(a * (1 + e) - R_EARTH).toFixed(1)} km</dd>
      </dl>
      <button
        type="button"
        disabled={sso === null}
        title={sso === null ? "No sun-synchronous inclination exists at this altitude" : undefined}
        onClick={() => sso !== null && set(["orbit", "inclination_deg"], Math.round(sso * 100) / 100)}
      >
        Sun-synchronous{sso !== null ? `: ${sso.toFixed(2)}°` : ""}
      </button>
    </div>
  );
}

export default function OrbitSection() {
  const { data, edit } = useForm();
  const orbit = (data.orbit ?? {}) as Record<string, unknown>;
  const type: OrbitType = orbit.type === "tle" ? "tle" : "keplerian";
  const sizeMode: SizeMode = typeof orbit.semi_major_axis_km === "number" ? "sma" : "altitude";
  // Remember the other orbit kind so toggling back and forth doesn't lose it.
  const stash = useRef<Record<OrbitType, unknown>>({ keplerian: DEFAULT_KEPLERIAN, tle: DEFAULT_TLE });

  const switchType = (next: OrbitType) => {
    if (next === type) return;
    stash.current[type] = orbit;
    edit((doc) => {
      doc.setIn(["orbit"], doc.createNode(stash.current[next]));
      const propagator = getIn(data, ["propagator"]);
      if (next === "tle") doc.setIn(["propagator"], "sgp4");
      else if (propagator === "sgp4") doc.setIn(["propagator"], "j2");
    });
  };

  const switchSize = (next: SizeMode) => {
    if (next === sizeMode) return;
    edit((doc) => {
      if (next === "sma") {
        const alt = typeof orbit.altitude_km === "number" ? orbit.altitude_km : 500;
        doc.deleteIn(["orbit", "altitude_km"]);
        doc.setIn(["orbit", "semi_major_axis_km"], Math.round((R_EARTH + alt) * 1000) / 1000);
      } else {
        const a = typeof orbit.semi_major_axis_km === "number" ? orbit.semi_major_axis_km : R_EARTH + 500;
        doc.deleteIn(["orbit", "semi_major_axis_km"]);
        doc.setIn(["orbit", "altitude_km"], Math.round((a - R_EARTH) * 1000) / 1000);
      }
    });
  };

  return (
    <Section title="Orbit">
      <Segmented
        label="Defined by"
        value={type}
        options={[
          { value: "keplerian", label: "Orbital elements" },
          { value: "tle", label: "TLE" },
        ]}
        onChange={switchType}
      />

      {type === "tle" ? (
        <>
          <TextField path={["orbit", "line1"]} label="TLE line 1" wide mono />
          <TextField path={["orbit", "line2"]} label="TLE line 2" wide mono hint="Propagated with SGP4." />
        </>
      ) : (
        <>
          <SelectField
            path={["propagator"]}
            label="Propagator"
            options={[
              { value: "j2", label: "Numerical, J2" },
              { value: "two_body", label: "Two-body (Kepler)" },
            ]}
          />
          <Segmented
            label="Orbit size"
            value={sizeMode}
            options={[
              { value: "altitude", label: "Altitude" },
              { value: "sma", label: "Semi-major axis" },
            ]}
            onChange={switchSize}
          />
          {sizeMode === "altitude" ? (
            <NumberField path={["orbit", "altitude_km"]} label="Altitude" unit="km" hint="Above the equatorial radius" />
          ) : (
            <NumberField path={["orbit", "semi_major_axis_km"]} label="Semi-major axis" unit="km" />
          )}
          <NumberField path={["orbit", "eccentricity"]} label="Eccentricity" />
          <NumberField path={["orbit", "inclination_deg"]} label="Inclination" unit="°" />
          <NumberField path={["orbit", "raan_deg"]} label="RAAN" unit="°" />
          <NumberField path={["orbit", "arg_perigee_deg"]} label="Arg. of perigee" unit="°" />
          <NumberField path={["orbit", "true_anomaly_deg"]} label="True anomaly" unit="°" />
          <DateTimeField
            path={["orbit", "epoch"]}
            label="Epoch"
            optional
            hint="Blank: the simulation start"
          />
          <DerivedOrbit />
        </>
      )}
    </Section>
  );
}
