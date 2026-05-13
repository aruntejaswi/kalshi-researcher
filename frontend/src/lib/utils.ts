import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Price is V2 dollars (0..1). We display in cents for trader readability. */
export function formatPrice(dollars?: number | null): string {
  if (dollars == null || Number.isNaN(dollars)) return "—";
  return `${Math.round(dollars * 100)}¢`;
}

/** Edge in percentage points, signed. */
export function formatEdge(edge?: number | null): string {
  if (edge == null || Number.isNaN(edge)) return "—";
  const pp = edge * 100;
  const sign = pp > 0 ? "+" : "";
  return `${sign}${pp.toFixed(1)}pp`;
}
