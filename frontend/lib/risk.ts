import { RiskLevel } from "./types";

/**
 * Matches the backend's risk_level_from_score() in
 * terrasentinel-backend/src/common/utils.py - keep these in sync.
 */
export function riskLevel(score: number): RiskLevel {
  if (score >= 80) return "CRITICAL";
  if (score >= 60) return "HIGH";
  if (score >= 35) return "MODERATE";
  return "LOW";
}

/** Same bands, used for the rescue module's fused signal probability (0-1). */
export function probLevel(p: number): RiskLevel {
  if (p >= 0.65) return "HIGH";
  if (p >= 0.35) return "MODERATE";
  return "LOW";
}

export const LEVEL_COLOR_VAR: Record<RiskLevel, string> = {
  LOW: "var(--low)",
  MODERATE: "var(--moderate)",
  HIGH: "var(--high)",
  CRITICAL: "var(--critical)",
};

export const LEVEL_COLOR_HEX: Record<RiskLevel, string> = {
  LOW: "#4C9A6B",
  MODERATE: "#D9A441",
  HIGH: "#D9822F",
  CRITICAL: "#D6483A",
};

const LEVEL_ORDER: Record<RiskLevel, number> = {
  LOW: 0,
  MODERATE: 1,
  HIGH: 2,
  CRITICAL: 3,
};

export function higherLevel(a: RiskLevel, b: RiskLevel): RiskLevel {
  return LEVEL_ORDER[a] >= LEVEL_ORDER[b] ? a : b;
}
