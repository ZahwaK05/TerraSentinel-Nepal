"use client";

import { Zone } from "@/lib/types";
import { LEVEL_COLOR_HEX, riskLevel } from "@/lib/risk";

export default function MapPanel({
  zones,
  day,
  selected,
  onSelect,
  corridorLevel,
}: {
  zones: Zone[];
  day: number;
  selected: string;
  onSelect: (id: string) => void;
  corridorLevel: "HIGH" | "CRITICAL" | null;
}) {
  const corridorOpacity = corridorLevel
    ? corridorLevel === "CRITICAL"
      ? 0.22
      : 0.14
    : 0;
  const corridorColor = corridorLevel ? LEVEL_COLOR_HEX[corridorLevel] : "transparent";

  const riverD =
    "M260,20 C245,70 235,110 230,150 C250,190 275,240 280,290 C270,330 235,380 240,430 C260,470 290,510 300,560 C295,585 285,605 280,620";

  return (
    <div className="panel map-panel">
      <h2>Melamchi valley — risk overlay</h2>
      <svg
        className="mapsvg"
        viewBox="0 0 520 640"
        role="img"
        aria-label="Schematic map of the Melamchi valley showing four monitored zones along the river"
      >
        <g stroke="var(--border-soft)" strokeWidth={1} fill="none" opacity={0.7}>
          <path d="M40,60 Q160,40 280,65 T500,55" />
          <path d="M30,95 Q160,75 290,98 T495,90" />
        </g>
        <path
          d={riverD}
          fill="none"
          stroke="var(--accent-dim)"
          strokeWidth={5}
          strokeLinecap="round"
        />
        <path
          d={riverD}
          fill="none"
          stroke={corridorColor}
          strokeWidth={22}
          strokeLinecap="round"
          style={{ opacity: corridorOpacity, transition: "opacity 0.5s" }}
        />
        <g>
          {zones.map((z) => {
            const score = z.scores[day];
            const lvl = riskLevel(score);
            const isSelected = z.id === selected;
            const labelX = z.cx + z.r + 10;

            function select() {
              onSelect(z.id);
            }

            return (
              <g
                key={z.id}
                style={{ cursor: "pointer" }}
                tabIndex={0}
                role="button"
                aria-label={`${z.name}, risk score ${score}`}
                onClick={select}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    select();
                  }
                }}
              >
                {isSelected && (
                  <circle
                    cx={z.cx}
                    cy={z.cy}
                    r={z.r + 6}
                    fill="none"
                    stroke={LEVEL_COLOR_HEX[lvl]}
                    strokeWidth={1}
                    opacity={0.5}
                  />
                )}
                <circle
                  cx={z.cx}
                  cy={z.cy}
                  r={z.r}
                  fill={LEVEL_COLOR_HEX[lvl]}
                  fillOpacity={0.85}
                  stroke="var(--bg)"
                  strokeWidth={2}
                />
                <text
                  x={z.cx}
                  y={z.cy}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontFamily="var(--mono)"
                  fontSize={11}
                  fontWeight={600}
                  fill="#0A0F12"
                >
                  {score}
                </text>
                <text x={labelX} y={z.cy} dominantBaseline="central" className="zone-label">
                  {z.name}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
