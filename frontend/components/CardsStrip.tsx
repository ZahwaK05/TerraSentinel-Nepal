"use client";

import { Zone } from "@/lib/types";
import { LEVEL_COLOR_VAR, riskLevel } from "@/lib/risk";

export default function CardsStrip({ zone, day }: { zone: Zone; day: number }) {
  const score = zone.scores[day];
  const lvl = riskLevel(score);
  const lakeChange = zone.lakeChange[day];

  const cards: { label: string; val: string | number; unit: string; highlight?: boolean }[] = [
    { label: "Risk score", val: score, unit: "/ 100", highlight: true },
    { label: "Population exposed", val: zone.population.toLocaleString(), unit: "" },
    {
      label: "Infrastructure",
      val: zone.roads + zone.bridges + zone.schools + zone.power,
      unit: "assets",
    },
    { label: "Rainfall (24h)", val: zone.rainfall[day], unit: "mm" },
    { label: "Lake change", val: `${lakeChange >= 0 ? "+" : ""}${lakeChange}`, unit: "%" },
    { label: "Displacement", val: zone.displacement[day].toFixed(2), unit: "m" },
  ];

  return (
    <div className="cards">
      {cards.map((c) => (
        <div className="card" key={c.label}>
          <div className="clabel">{c.label}</div>
          <div className="cval" style={{ color: c.highlight ? LEVEL_COLOR_VAR[lvl] : "var(--ink)" }}>
            {c.val}
            <span className="cunit">{c.unit}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
