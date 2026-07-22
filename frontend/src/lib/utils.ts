import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d} day${d !== 1 ? "s" : ""}`);
  if (h > 0) parts.push(`${h} hour${h !== 1 ? "s" : ""}`);
  parts.push(`${m} minute${m !== 1 ? "s" : ""}`);
  return parts.join(", ");
}

export function groupByYear<T>(items: T[], getDate: (item: T) => string | null): Array<{ year: number; items: T[] }> {
  const map = new Map<number, T[]>();
  for (const item of items) {
    const d = getDate(item);
    const year = d ? new Date(d).getFullYear() : new Date().getFullYear();
    if (!map.has(year)) map.set(year, []);
    map.get(year)!.push(item);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => b - a)
    .map(([year, items]) => ({ year, items }));
}
