"use client";

import { RiskLevel, Zone } from "@/lib/types";

export default function AlertBanner({
  level,
  zone,
  onToast,
}: {
  level: RiskLevel;
  zone: Zone;
  onToast: (msg: string) => void;
}) {
  const show = level === "HIGH" || level === "CRITICAL";
  if (!show) return null;

  function playVoiceAlert() {
    const text = `${level} flood risk detected in ${zone.name}. Move to the designated higher elevation evacuation zone immediately.`;
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        u.rate = 0.95;
        window.speechSynthesis.speak(u);
        onToast("Playing voice alert (browser TTS demo — Polly in production)");
      } catch {
        onToast("Voice playback unavailable in this browser");
      }
    } else {
      onToast("Voice playback unavailable in this browser");
    }
  }

  return (
    <div className="alert-banner show" role="alert">
      <span className="dot" aria-hidden="true" />
      <div className="body">
        <div className="head">
          {level} flood risk — {zone.name}
        </div>
        <div className="msg">
          Move to the designated higher-elevation evacuation zone immediately.
        </div>
      </div>
      <button className="voice-btn" type="button" onClick={playVoiceAlert}>
        Play voice alert
      </button>
    </div>
  );
}
