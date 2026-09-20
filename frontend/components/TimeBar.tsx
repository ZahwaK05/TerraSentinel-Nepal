"use client";

import { useEffect, useRef, useState } from "react";
import { DAY_LABELS } from "@/lib/mockData";

export default function TimeBar({
  day,
  onChange,
}: {
  day: number;
  onChange: (day: number) => void;
}) {
  const [playing, setPlaying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  function togglePlay() {
    if (playing) {
      if (timerRef.current) clearInterval(timerRef.current);
      setPlaying(false);
      return;
    }
    const start = day >= DAY_LABELS.length - 1 ? 0 : day;
    onChange(start);
    setPlaying(true);
    let current = start;
    timerRef.current = setInterval(() => {
      current += 1;
      if (current >= DAY_LABELS.length - 1) {
        current = DAY_LABELS.length - 1;
        onChange(current);
        if (timerRef.current) clearInterval(timerRef.current);
        setPlaying(false);
        return;
      }
      onChange(current);
    }, 1400);
  }

  return (
    <div className="timebar">
      <div className="timebar-top">
        <div className="timebar-title">
          Historical replay — <b>2021 Melamchi flood</b>
        </div>
        <button className="play-btn" type="button" onClick={togglePlay}>
          {playing ? "❙❙ Pause" : "▶ Play sequence"}
        </button>
      </div>
      <input
        type="range"
        min={0}
        max={DAY_LABELS.length - 1}
        step={1}
        value={day}
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
        aria-label="Timeline day"
      />
      <div className="day-labels">
        {DAY_LABELS.map((label, i) => (
          <span key={label} className={i === day ? "active" : ""}>
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
