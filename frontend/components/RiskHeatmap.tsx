"use client";

import { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";
import { fetchRiskGrid, RiskGridGeoJSON } from "@/lib/api";

const YEARS = ["2021", "2026"];

export default function RiskHeatmap() {
  const mapDivRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const heatLayerRef = useRef<any>(null);

  const [year, setYear] = useState("2026");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [pointCount, setPointCount] = useState(0);

  // Initialize the map once.
  useEffect(() => {
    let cancelled = false;

    async function init() {
      if (!mapDivRef.current || mapRef.current) return;
      const L = await import("leaflet");
      // leaflet.heat attaches L.heatLayer as a side effect on window.L
      await import("leaflet.heat");

      if (cancelled) return;

      const map = L.map(mapDivRef.current, {
        center: [27.98, 85.55],
        zoom: 11,
        zoomControl: true,
      });

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 17,
      }).addTo(map);

      mapRef.current = map;
      loadYear(year);
    }

    init();

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadYear(y: string) {
    setStatus("loading");
    const data: RiskGridGeoJSON | null = await fetchRiskGrid(y);
    if (!data) {
      setStatus("error");
      return;
    }

    const L = await import("leaflet");
    await import("leaflet.heat");

    const points: [number, number, number][] = data.features.map((f) => [
      f.geometry.coordinates[1], // lat
      f.geometry.coordinates[0], // lon
      f.properties.risk_score / 100, // weight 0-1
    ]);

    if (heatLayerRef.current && mapRef.current) {
      mapRef.current.removeLayer(heatLayerRef.current);
    }

    if (mapRef.current) {
      const heat = L.heatLayer(points, {
        radius: 14,
        blur: 18,
        maxZoom: 14,
        gradient: { 0.3: "#4C9A6B", 0.55: "#D9A441", 0.7: "#D9822F", 0.85: "#D6483A" },
      });
      heat.addTo(mapRef.current);
      heatLayerRef.current = heat;
    }

    setPointCount(data.features.length);
    setStatus("ready");
  }

  function handleYearChange(y: string) {
    setYear(y);
    if (mapRef.current) loadYear(y);
  }

  return (
    <div className="panel map-panel" style={{ padding: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 8px 10px" }}>
        <h2 style={{ margin: 0 }}>Full basin risk grid — {pointCount ? pointCount.toLocaleString() : "…"} cells</h2>
        <div style={{ display: "flex", gap: 6 }}>
          {YEARS.map((y) => (
            <button
              key={y}
              type="button"
              onClick={() => handleYearChange(y)}
              className="play-btn"
              style={{
                borderColor: y === year ? "var(--accent)" : "var(--border)",
                color: y === year ? "var(--accent)" : "var(--ink)",
              }}
            >
              {y}
            </button>
          ))}
        </div>
      </div>
      <div
        ref={mapDivRef}
        style={{ width: "100%", height: 420, borderRadius: 4, overflow: "hidden" }}
      />
      {status === "error" && (
        <div style={{ padding: "10px 8px 0", fontSize: 12, color: "var(--ink-mute)" }}>
          Couldn&apos;t load the risk grid for {year}. Check NEXT_PUBLIC_API_URL, or that
          public/data/melamchi_{year}_risk_points.geojson exists locally.
        </div>
      )}
    </div>
  );
}
