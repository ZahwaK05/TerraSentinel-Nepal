"use client";

import { Zone } from "@/lib/types";
import { LEVEL_COLOR_VAR, riskLevel } from "@/lib/risk";

export default function DetailPanel({ zone, day }: { zone: Zone; day: number }) {
  const score = zone.scores[day];
  const lvl = riskLevel(score);

  let actions: string[] = [];
  if (lvl === "MODERATE") actions = ["Monitor rainfall and lake-level trend"];
  if (lvl === "HIGH") actions = ["Prepare evacuation route", "Notify downstream zones"];
  if (lvl === "CRITICAL")
    actions = ["Prepare evacuation", "Restrict road access", "Deploy emergency teams"];

  return (
    <div className="panel">
      <h2>Zone detail</h2>
      <div className="detail-zone-name">{zone.name}</div>
      <div
        className="detail-level"
        style={{
          background: `${LEVEL_COLOR_VAR[lvl]}22`,
          color: LEVEL_COLOR_VAR[lvl],
          border: `1px solid ${LEVEL_COLOR_VAR[lvl]}55`,
        }}
      >
        {lvl} &middot; {score}/100
      </div>
      <div className="detail-row">
        <span className="label">Population</span>
        <span className="val">{zone.population.toLocaleString()}</span>
      </div>
      <div className="detail-row">
        <span className="label">Roads</span>
        <span className="val">{zone.roads}</span>
      </div>
      <div className="detail-row">
        <span className="label">Bridges</span>
        <span className="val">{zone.bridges}</span>
      </div>
      <div className="detail-row">
        <span className="label">Schools</span>
        <span className="val">{zone.schools}</span>
      </div>
      <div className="detail-row">
        <span className="label">Power assets</span>
        <span className="val">{zone.power}</span>
      </div>
      <div className="corridor-text">{zone.corridor}</div>
      {actions.length > 0 && (
        <ul className="action-list">
          {actions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
