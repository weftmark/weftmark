export type LengthUnit = "cm" | "in";

const CM_PER_IN = 2.54;

export function measurementSystemToUnit(system: string): LengthUnit {
  return system === "imperial" ? "in" : "cm";
}

export function convertLength(value: number, from: LengthUnit, to: LengthUnit): number {
  if (from === to) return value;
  return from === "cm" ? value / CM_PER_IN : value * CM_PER_IN;
}

export function formatLength(value: number, unit: LengthUnit, decimals = 1): string {
  return `${value.toFixed(decimals)} ${unit}`;
}

export function displayLength(
  value: number | string | null | undefined,
  storedUnit: string,
  displayUnit: LengthUnit,
): string | null {
  if (value == null || value === "") return null;
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return null;
  const converted = convertLength(num, storedUnit as LengthUnit, displayUnit);
  return formatLength(converted, displayUnit);
}

/** Format an approximate yarn/warp length stored in cm.
 *  Automatically picks a human-readable unit:
 *  metric  — rounds to nearest 10 cm; ≥1000 cm shown in metres (e.g. "12.5m", "80cm")
 *  imperial — rounds to nearest 6 in;  ≥100 in shown in yards  (e.g. "3.5 yd", "72 in")
 */
export function formatApproxLength(cm: number, unit: LengthUnit): string {
  if (unit === "cm") {
    const rounded = Math.round(cm / 10) * 10;
    if (rounded >= 1000) {
      const m = rounded / 100;
      return m % 1 === 0 ? `${m}m` : `${m.toFixed(1)}m`;
    }
    return `${rounded}cm`;
  } else {
    const inches = cm / CM_PER_IN;
    const rounded = Math.round(inches / 6) * 6;
    if (rounded >= 100) {
      const yd = rounded / 36;
      return yd % 1 === 0 ? `${yd} yd` : `${yd.toFixed(1)} yd`;
    }
    return `${rounded} in`;
  }
}
