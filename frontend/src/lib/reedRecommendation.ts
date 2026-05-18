const COMMON_DENTS = [5, 6, 8, 10, 12, 15, 20] as const;
const MAX_THREADS_PER_DENT = 6;

export interface ReedMatch {
  dents: number;
  threadsPerDent: number;
}

export interface ReedRecommendation {
  matches: ReedMatch[];
  nearest: [number, number] | null; // [lower clean EPI, upper clean EPI], null if matches exist
}

function cleanSetts(dents: number): number[] {
  const setts: number[] = [];
  for (let t = 1; t <= MAX_THREADS_PER_DENT; t++) {
    setts.push(dents * t);
  }
  return setts;
}

export function getReedRecommendation(epi: number): ReedRecommendation {
  const matches: ReedMatch[] = [];

  for (const dents of COMMON_DENTS) {
    if (epi % dents === 0) {
      const threadsPerDent = epi / dents;
      if (threadsPerDent <= MAX_THREADS_PER_DENT) {
        matches.push({ dents, threadsPerDent });
      }
    }
  }

  matches.sort((a, b) => a.threadsPerDent - b.threadsPerDent);

  if (matches.length > 0) {
    return { matches, nearest: null };
  }

  // No exact match — find nearest clean EPIs below and above
  const allCleanEpis = Array.from(
    new Set(COMMON_DENTS.flatMap(cleanSetts))
  ).sort((a, b) => a - b);

  const lower = [...allCleanEpis].reverse().find((s) => s < epi) ?? null;
  const upper = allCleanEpis.find((s) => s > epi) ?? null;

  return {
    matches: [],
    nearest: lower != null && upper != null ? [lower, upper] : null,
  };
}

/**
 * Bresenham distribution — spreads `epiInt` threads across `dents` dents as
 * evenly as possible. Returns an array of length `dents` where each element
 * is the thread count for that dent. Sums to `epiInt`.
 */
export function buildDentPattern(epi: number, dents: number): number[] {
  const epiInt = Math.round(epi);
  const pattern: number[] = [];
  for (let i = 0; i < dents; i++) {
    pattern.push(Math.floor(((i + 1) * epiInt) / dents) - Math.floor((i * epiInt) / dents));
  }
  return pattern;
}

/**
 * Finds the nearest common-dent reed that gives a clean multiple for `epi`,
 * searching within `allDents` (loom reeds + common dents). Returns the dent
 * count, or null if none found.
 */
export function nearestCleanDent(epi: number, allDents: number[]): number | null {
  const epiInt = Math.round(epi);
  const sorted = [...allDents].sort((a, b) => {
    const aClean = epiInt % a === 0;
    const bClean = epiInt % b === 0;
    if (aClean && !bClean) return -1;
    if (!aClean && bClean) return 1;
    return a - b;
  });
  const clean = sorted.find((d) => epiInt % d === 0);
  return clean ?? null;
}
