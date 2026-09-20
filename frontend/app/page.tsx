"use client";

import { useEffect, useRef, useState } from "react";
import Header from "@/components/Header";
import AlertBanner from "@/components/AlertBanner";
import TimeBar from "@/components/TimeBar";
import ZoneList from "@/components/ZoneList";
import MapPanel from "@/components/MapPanel";
import DetailPanel from "@/components/DetailPanel";
import CardsStrip from "@/components/CardsStrip";
import RescueGrid from "@/components/RescueGrid";
import RiskHeatmap from "@/components/RiskHeatmap";
import Toast from "@/components/Toast";
import { ZONES, RESCUE_CASES } from "@/lib/mockData";
import { riskLevel } from "@/lib/risk";
import { RiskLevel } from "@/lib/types";

export default function Page() {
  const [day, setDay] = useState(0);
  const [selected, setSelected] = useState(ZONES[0].id);
  const [toastMsg, setToastMsg] = useState("");
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function showToast(msg: string) {
    setToastMsg(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastMsg(""), 2600);
  }

  useEffect(() => {
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  const selectedZone = ZONES.find((z) => z.id === selected) ?? ZONES[0];

  // Highest risk level across all zones on the current day - drives the
  // header status pill, the alert banner, and the map's corridor overlay.
  const order: Record<RiskLevel, number> = { LOW: 0, MODERATE: 1, HIGH: 2, CRITICAL: 3 };
  let systemLevel: RiskLevel = "LOW";
  let systemZone = ZONES[0];
  for (const z of ZONES) {
    const lvl = riskLevel(z.scores[day]);
    if (order[lvl] > order[systemLevel]) {
      systemLevel = lvl;
      systemZone = z;
    }
  }

  const corridorLevel =
    systemLevel === "HIGH" || systemLevel === "CRITICAL" ? systemLevel : null;

  return (
    <div className="wrap">
      <Header systemLevel={systemLevel} />

      <AlertBanner level={systemLevel} zone={systemZone} onToast={showToast} />

      <TimeBar day={day} onChange={setDay} />

      <div className="main-grid">
        <ZoneList zones={ZONES} day={day} selected={selected} onSelect={setSelected} />
        <MapPanel
          zones={ZONES}
          day={day}
          selected={selected}
          onSelect={setSelected}
          corridorLevel={corridorLevel}
        />
        <DetailPanel zone={selectedZone} day={day} />
      </div>

      <CardsStrip zone={selectedZone} day={day} />

      <div className="section-title">
        <h2>Basin-wide risk grid</h2>
        <span className="note">Real per-cell data from the geospatial/ML pipeline — 32,000+ cells</span>
      </div>
      <RiskHeatmap />

      <RescueGrid cases={RESCUE_CASES} onToast={showToast} />

      <footer className="page-footer">
        Mock data shown throughout — wires up to the live API Gateway endpoint
        (GET /risk, /infrastructure, /alerts, /rescue) once deployed. Risk index
        is a relative score, not a calibrated probability.
      </footer>

      <Toast message={toastMsg} />
    </div>
  );
}
