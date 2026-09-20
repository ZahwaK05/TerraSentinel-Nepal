"use client";

import { Zone } from "@/lib/types";
import { LEVEL_COLOR_VAR, riskLevel } from "@/lib/risk";

export default function ZoneList({
  zones,
  day,
  selected,
  onSelect,
}: {
  zones: Zone[];
  day: number;
  selected: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="panel">
      <h2>Zones</h2>
      <div>
        {zones.map((z) => {
          const score = z.scores[day];
          const lvl = riskLevel(score);
          const active = z.id === selected;
          return (
            <button
              key={z.id}
              type="button"
              className={`zone-item${active ? " active" : ""}`}
              aria-pressed={active}
              onClick={() => onSelect(z.id)}
            >
              <span
                className="swatch"
                style={{ background: LEVEL_COLOR_VAR[lvl] }}
              />
              <span className="name">{z.name}</span>
              <span className="score">{score}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
