// Shapes of the engine API's JSON responses (see engine/simcore/server.py).

export interface ExampleSummary {
  id: string;
  name: string;
  description: string;
}

export interface Pass {
  station: string;
  aos: string;
  tca: string;
  los: string;
  duration_s: number;
  max_elevation_deg: number;
  aos_azimuth_deg: number;
  los_azimuth_deg: number;
  truncated_start: boolean;
  truncated_end: boolean;
}

export interface LinkSeries {
  seconds: number[];
  utc: string[];
  elevation_deg: number[];
  range_km: number[];
  range_rate_km_s: number[];
  delay_ms: number[];
  doppler_hz: number[];
  doppler_rate_hz_s: number[];
  path_loss_db: number[];
  atmospheric_loss_db: number[];
  received_power_dbm: number[];
  cn0_dbhz: number[];
  esn0_db: number[];
  ebn0_db: number[];
  margin_db: number[];
  ber: number[];
}

export interface LinkPass {
  link: string;
  station: string;
  pass_index: number;
  max_abs_doppler_hz: number;
  max_abs_doppler_rate_hz_s: number;
  peak_margin_db: number;
  link_closed_s: number;
  data_volume_bits: number;
  series: LinkSeries;
}

export interface GroundStationConfig {
  name: string;
  latitude_deg: number;
  longitude_deg: number;
  altitude_m: number;
  min_elevation_deg: number;
}

export interface LinkConfig {
  name: string;
  direction: "downlink" | "uplink";
  frequency_mhz: number;
  data_rate_bps: number;
  modulation: string;
  stations: string[] | null;
}

export interface ScenarioJson {
  name: string;
  description: string;
  simulation: { start: string; duration_hours: number; step_seconds: number };
  spacecraft: { name: string; form_factor: string; mass_kg: number };
  propagator: string;
  ground_stations: GroundStationConfig[];
  links: LinkConfig[];
}

export interface Ephemeris {
  seconds: number[];
  utc: string[];
  latitude_deg: number[];
  longitude_deg: number[];
  altitude_km: number[];
}

export interface SimulationResult {
  scenario: ScenarioJson;
  passes: Record<string, Pass[]>;
  link_passes: LinkPass[];
  ephemeris: Ephemeris;
}

export interface ValidationIssue {
  loc: string;
  msg: string;
}

/** A pass plus its identity, for selection across stations. */
export interface PassRef {
  station: string;
  index: number;
  pass: Pass;
}
