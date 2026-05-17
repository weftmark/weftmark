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
