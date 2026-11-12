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
  sc_antenna_gain_dbi: number[];
  sc_antenna_angle_deg: number[];
  gas_loss_db: number[];
  cloud_loss_db: number[];
  rain_loss_db: number[];
  scintillation_db: number[];
  system_noise_temp_k: number[];
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
  /** Spacecraft body axes as Earth-fixed unit vectors, one [x, y, z] per sample. */
  body_x_itrs: number[][];
  body_y_itrs: number[][];
  body_z_itrs: number[][];
}

export interface SimulationResult {
  scenario: ScenarioJson;
  passes: Record<string, Pass[]>;
  link_passes: LinkPass[];
  ephemeris: Ephemeris;
}

export interface ValidationIssue {
  loc: string;
  /** Location as a document path, e.g. ["ground_stations", 0, "latitude_deg"]. */
  path: (string | number)[];
  msg: string;
}

/** A pass plus its identity, for selection across stations. */
export interface PassRef {
  station: string;
  index: number;
  pass: Pass;
}

export interface LifetimeResult {
  start: string;
  start_jd: number;
  days: number[];
  perigee_km: number[];
  apogee_km: number[];
  f107: number[];
  reentered: boolean;
  lifetime_days: number;
  max_years: number;
  reentry_altitude_km: number;
  ballistic_coefficient: number;
  solar_activity: string;
  notes: string[];
}
