// Small orbit helpers for the form's derived values. These mirror the
// engine's constants (engine/simcore/constants.py).

export const MU_EARTH = 398600.4418; // km^3/s^2
export const R_EARTH = 6378.137; // km
const J2 = 1.08262668e-3;
// Rate the orbit plane must precess to follow the Sun: 360 deg per tropical year.
const SUN_SYNC_RATE = (2 * Math.PI) / (365.2422 * 86400); // rad/s

export function periodMinutes(a: number): number {
  return (2 * Math.PI * Math.sqrt(a ** 3 / MU_EARTH)) / 60;
}

/**
 * Inclination (deg) at which J2 nodal regression matches the Sun's apparent
 * motion, or null if no such orbit exists at this size (above ~5,970 km
 * altitude for circular orbits).
 */
export function sunSynchronousInclination(a: number, e: number): number | null {
  const n = Math.sqrt(MU_EARTH / a ** 3);
  const p = a * (1 - e * e);
  const cosI = -SUN_SYNC_RATE / (1.5 * n * J2 * (R_EARTH / p) ** 2);
  if (cosI < -1) return null;
  return (Math.acos(cosI) * 180) / Math.PI;
}
