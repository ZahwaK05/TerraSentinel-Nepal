/**
 * Thin wrapper around Manas's API Gateway routes
 * (see terrasentinel-backend/src/api/app.py for the handler).
 *
 * Nothing in app/page.tsx calls these yet - the dashboard runs on
 * lib/mockData.ts so the UI works before the backend exists. Once
 * NEXT_PUBLIC_API_URL is set (the `ApiUrl` output from `sam deploy`),
 * swap the mock imports in app/page.tsx for these functions - the
 * component tree doesn't need to change, only where the arrays come
 * from.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL;

async function getJSON<T>(path: string): Promise<T | null> {
  if (!API_URL) return null;
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export interface RiskEventDTO {
  event_id: string;
  timestamp: string;
  zone: string;
  risk_score: number;
  risk_level: string;
  features: Record<string, number>;
}

export interface InfrastructureDTO {
  asset_id: string;
  type: string;
  name: string;
  zone: string;
  population_estimate?: number;
}

export interface AlertDTO {
  alert_id: string;
  zone: string;
  risk_level: string;
  message: string;
  created_at: string;
}

export async function fetchRiskEvents() {
  const data = await getJSON<{ risk_events: RiskEventDTO[] }>("/risk");
  return data?.risk_events ?? null;
}

export async function fetchRiskForZone(zone: string) {
  const data = await getJSON<{ zone: string; risk_events: RiskEventDTO[] }>(
    `/risk/${encodeURIComponent(zone)}`
  );
  return data?.risk_events ?? null;
}

export async function fetchInfrastructure() {
  const data = await getJSON<{ infrastructure: InfrastructureDTO[] }>(
    "/infrastructure"
  );
  return data?.infrastructure ?? null;
}

export async function fetchAlerts() {
  const data = await getJSON<{ alerts: AlertDTO[] }>("/alerts");
  return data?.alerts ?? null;
}

export async function simulateEvent(body?: { key?: string; zone?: string }) {
  if (!API_URL) return null;
  try {
    const res = await fetch(`${API_URL}/simulate-event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export interface RiskGridFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    id: string;
    risk_score: number;
    rainfall_score: number;
    terrain_score: number;
    lake_proximity_score: number;
  };
}

export interface RiskGridGeoJSON {
  type: "FeatureCollection";
  features: RiskGridFeature[];
}

/**
 * Fetches the full per-cell risk grid for a given year (as delivered by
 * the geospatial/ML teammate and converted with
 * scripts/convert_risk_grid.py in the backend repo).
 *
 * - With NEXT_PUBLIC_API_URL set: asks GET /risk-map/{year}, which
 *   returns a short-lived presigned S3 URL, then fetches the actual
 *   GeoJSON from that URL.
 * - Without it: falls back to the static copy in public/data/, so the
 *   heatmap works in local dev before the backend is deployed.
 */
export async function fetchRiskGrid(year: string): Promise<RiskGridGeoJSON | null> {
  if (API_URL) {
    const pointer = await getJSON<{ url: string }>(`/risk-map/${year}`);
    if (pointer?.url) {
      try {
        const res = await fetch(pointer.url);
        if (res.ok) return (await res.json()) as RiskGridGeoJSON;
      } catch {
        /* fall through to local fallback below */
      }
    }
  }
  try {
    const res = await fetch(`/data/melamchi_${year}_risk_points.geojson`);
    if (!res.ok) return null;
    return (await res.json()) as RiskGridGeoJSON;
  } catch {
    return null;
  }
}
