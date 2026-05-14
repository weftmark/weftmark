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
