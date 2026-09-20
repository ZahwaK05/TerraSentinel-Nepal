"use client";

import { useState } from "react";
import { RescueCase } from "@/lib/types";
import { LEVEL_COLOR_VAR, probLevel } from "@/lib/risk";

function SignalRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="signal-row">
      <div className="srow-top">
        <span>{label}</span>
        <span style={{ fontFamily: "var(--mono)" }}>{value.toFixed(2)}</span>
      </div>
      <div className="signal-bar">
        <div className="signal-fill" style={{ width: `${value * 100}%` }} />
      </div>
    </div>
  );
}

function RescueCard({ c, index, onToast }: { c: RescueCase; index: number; onToast: (m: string) => void }) {
  const [deployed, setDeployed] = useState(false);
  const prob = (c.thermal + c.acoustic + c.rf) / 3;
  const band = probLevel(prob);

  return (
    <div className="rescue-card">
      <div className="rescue-top">
        <div>
          <div className="rescue-priority">PRIORITY #{index + 1}</div>
          <div className="rescue-zone">{c.zone}</div>
        </div>
        <div
          className="prob-badge"
          style={{
            background: `${LEVEL_COLOR_VAR[band]}22`,
            color: LEVEL_COLOR_VAR[band],
            border: `1px solid ${LEVEL_COLOR_VAR[band]}55`,
          }}
        >
          {band}
        </div>
      </div>
      <SignalRow label="Thermal" value={c.thermal} />
      <SignalRow label="Acoustic" value={c.acoustic} />
      <SignalRow label="RF" value={c.rf} />
      <div className="rescue-meta">
        <span>Est. debris depth</span>
        <span style={{ fontFamily: "var(--mono)", color: "var(--ink)" }}>
          {c.depth.toFixed(1)} m
        </span>
      </div>
      <button
        className={`deploy-btn${deployed ? " done" : ""}`}
        type="button"
        disabled={deployed}
        onClick={() => {
          setDeployed(true);
          onToast(`Rescue team dispatched to ${c.zone}`);
        }}
      >
        {deployed ? "Team dispatched" : "Deploy rescue team"}
      </button>
    </div>
  );
}

export default function RescueGrid({
  cases,
  onToast,
}: {
  cases: RescueCase[];
  onToast: (msg: string) => void;
}) {
  return (
    <>
      <div className="section-title">
        <h2>Post-disaster rescue priority</h2>
        <span className="note">Simulated drone/ground sensor fusion — thermal, acoustic, RF</span>
      </div>
      <div className="rescue-grid">
        {cases.map((c, i) => (
          <RescueCard key={c.zone} c={c} index={i} onToast={onToast} />
        ))}
      </div>
    </>
  );
}
