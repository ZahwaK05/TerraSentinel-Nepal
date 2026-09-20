"use client";

import { useEffect, useState } from "react";
import { RiskLevel } from "@/lib/types";
import { LEVEL_COLOR_VAR } from "@/lib/risk";

function useClock() {
  const [time, setTime] = useState("");
  useEffect(() => {
    const tick = () => {
      const d = new Date();
      const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);
      setTime(`${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} local`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return time;
}

export default function Header({
  systemLevel,
}: {
  systemLevel: RiskLevel;
}) {
  const time = useClock();
  const nominal = systemLevel === "LOW";

  return (
    <header className="top">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <h1>TerraSentinel-Nepal</h1>
        <span className="sub">/ command dashboard</span>
      </div>
      <div className="top-right">
        <span className="clock" aria-live="off">
          {time}
        </span>
        <div
          className="status-pill"
          style={{
            borderColor: nominal ? "var(--border)" : `${LEVEL_COLOR_VAR[systemLevel]}55`,
          }}
        >
          <span
            className="status-dot"
            style={{ background: LEVEL_COLOR_VAR[systemLevel] }}
          />
          <span style={{ color: nominal ? "var(--ink-dim)" : LEVEL_COLOR_VAR[systemLevel] }}>
            {nominal ? "SYSTEM NOMINAL" : `SYSTEM STATUS: ${systemLevel}`}
          </span>
        </div>
      </div>
    </header>
  );
}
