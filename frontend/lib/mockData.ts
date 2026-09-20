import { RescueCase, Zone } from "./types";

export const DAY_LABELS = ["Jun 11", "Jun 12", "Jun 13", "Jun 14", "Jun 15"];

/**
 * Mock zones for the 2021 Melamchi flood historical replay.
 * Shape matches what GET /risk and GET /risk/{zone} should eventually
 * return once Manas's backend + Member 1's model are live - see
 * terrasentinel-backend/src/run_risk_model/app.py for the real
 * {risk_score, risk_level} contract this stands in for.
 */
export const ZONES: Zone[] = [
  {
    id: "melamchi-bazar",
    name: "Melamchi Bazar",
    cx: 230,
    cy: 150,
    r: 22,
    population: 4281,
    roads: 5,
    bridges: 2,
    schools: 2,
    power: 1,
    corridor:
      "Debris flow path follows the Melamchi Khola through the bazar core toward Talamarang.",
    scores: [18, 32, 58, 79, 91],
    rainfall: [62, 88, 124, 156, 182],
    lakeChange: [2, 5, 9, 14, 19],
    displacement: [0.04, 0.07, 0.11, 0.16, 0.22],
  },
  {
    id: "talamarang",
    name: "Talamarang",
    cx: 280,
    cy: 290,
    r: 18,
    population: 2150,
    roads: 4,
    bridges: 1,
    schools: 1,
    power: 0,
    corridor:
      "Confluence point - upstream debris flow gains volume before reaching Ambathan.",
    scores: [12, 22, 44, 68, 85],
    rainfall: [54, 74, 102, 138, 168],
    lakeChange: [1, 3, 7, 11, 16],
    displacement: [0.03, 0.05, 0.09, 0.13, 0.18],
  },
  {
    id: "ambathan",
    name: "Ambathan",
    cx: 240,
    cy: 430,
    r: 17,
    population: 1560,
    roads: 3,
    bridges: 1,
    schools: 1,
    power: 0,
    corridor:
      "Narrow gorge section - flow velocity increases before the valley floor.",
    scores: [10, 16, 30, 52, 74],
    rainfall: [48, 66, 90, 120, 150],
    lakeChange: [1, 2, 5, 9, 13],
    displacement: [0.02, 0.04, 0.07, 0.1, 0.15],
  },
  {
    id: "sindhu-confluence",
    name: "Sindhu confluence",
    cx: 300,
    cy: 560,
    r: 24,
    population: 4849,
    roads: 6,
    bridges: 3,
    schools: 3,
    power: 1,
    corridor:
      "Valley widens at the Sindhu confluence - primary settlement exposure zone.",
    scores: [8, 12, 20, 38, 60],
    rainfall: [40, 54, 74, 98, 128],
    lakeChange: [0, 1, 3, 6, 10],
    displacement: [0.01, 0.02, 0.04, 0.07, 0.11],
  },
];

/**
 * Mock rescue cases matching Mathew's post-disaster fusion module
 * ({thermal_anomaly, acoustic_signal, rf_signal} -> survivor probability).
 */
export const RESCUE_CASES: RescueCase[] = [
  { zone: "Melamchi Bazar", thermal: 0.81, acoustic: 0.72, rf: 0.64, depth: 3.2 },
  { zone: "Talamarang", thermal: 0.55, acoustic: 0.4, rf: 0.3, depth: 1.8 },
  { zone: "Ambathan", thermal: 0.22, acoustic: 0.18, rf: 0.1, depth: 0.9 },
];
