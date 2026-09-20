export type RiskLevel = "LOW" | "MODERATE" | "HIGH" | "CRITICAL";

export interface Zone {
  id: string;
  name: string;
  /** Position on the schematic map (SVG viewBox 0 0 520 640) */
  cx: number;
  cy: number;
  r: number;
  population: number;
  roads: number;
  bridges: number;
  schools: number;
  power: number;
  corridor: string;
  /** One entry per day in DAY_LABELS */
  scores: number[];
  rainfall: number[];
  lakeChange: number[];
  displacement: number[];
}

export interface RescueCase {
  zone: string;
  thermal: number;
  acoustic: number;
  rf: number;
  depth: number;
}
