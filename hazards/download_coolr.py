"""
Download NASA COOLR landslide points for the Melamchi area and save them as
data/raw/hazards/historical_landslides.csv, ready for fetch_landslide_data.py.

Queries NASA's public ArcGIS layer (COOLR_Reports_Points) with a bounding box:
the Melamchi bbox from config, padded so landslides just outside the watershed
still count towards the 5 km density. Standard library plus pandas only.

Two ways to get the data:

  A) From a file downloaded from NASA (recommended - NASA's live query service
     returned HTTP 404 in testing, so the direct download below usually fails):
       1. Open https://maps.nccs.nasa.gov/arcgis/apps/MapAndAppGallery/index.html?appid=574f26408683485799d02e857e5d9521
          (or landslides.nasa.gov -> Landslide Viewer -> "Download Landslide Catalog")
       2. Download the COOLR / Global Landslide Catalog as CSV (or shapefile).
       3. python hazards\\download_coolr.py --from-file path\\to\\that_file.csv
     The script keeps only points inside the Melamchi bounding box (plus padding).

  B) Direct query of NASA's ArcGIS layer (works only if the service is up):
       python hazards\\download_coolr.py

Options:
    --from-file F    convert a downloaded .csv / .shp / .geojson / .gpkg
    --from-json F    convert a saved ArcGIS query result (.json)
    --layer URL      use a different ArcGIS layer (URL ending .../FeatureServer/0)
    --pad DEG        bbox padding in degrees (default 0.1, about 11 km)
    --force          overwrite an existing historical_landslides.csv

Cite COOLR: Juang, Stanley & Kirschbaum (2019) PLOS ONE 14(7) e0218657, and for
GLC records Kirschbaum et al. (2015) Geomorphology 249, 4-15.
"""
import argparse
import json
import urllib.parse
import urllib.request

import pandas as pd

from config import DATA_RAW, MELAMCHI_BBOX, EVENTS

DEFAULT_LAYER = ("https://gis.earthdata.nasa.gov/gis05/rest/services/Landslides/"
                 "COOLR_Reports_Points/FeatureServer/0")
# Layer facts (from the layer's own description page): date field, id field, max page size.
KNOWN_DATE_FIELD, KNOWN_OID_FIELD, KNOWN_MAX_RECORDS = "event_date", "objectid", 2000
DOWNLOAD_PAGE = ("https://maps.nccs.nasa.gov/arcgis/apps/MapAndAppGallery/index.html"
                 "?appid=574f26408683485799d02e857e5d9521")
OUT_PATH = DATA_RAW / "hazards" / "historical_landslides.csv"
DATE_NAME_HINTS = ("event_date", "landslide_date", "date")
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) terrasentinel-nepal/1.0"


class RequestFailed(Exception):
    pass


def _get_json(url: str, params: dict, timeout: int = 60) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": BROWSER_UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # network, DNS, proxy, HTTP error, bad JSON
        raise RequestFailed(str(e))
    if "error" in data:
        raise RequestFailed(f"server error: {data['error']}")
    return data


def _query_params(env: dict, offset: int, page_size: int, oid: str | None) -> dict:
    p = {"f": "json", "where": "1=1", "outFields": "*", "returnGeometry": "true",
         "geometry": json.dumps(env), "geometryType": "esriGeometryEnvelope",
         "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
         "resultOffset": offset, "resultRecordCount": page_size}
    if oid:
        p["orderByFields"] = oid
    return p


def _envelope(pad: float) -> dict:
    minx, miny, maxx, maxy = MELAMCHI_BBOX
    return {"xmin": minx - pad, "ymin": miny - pad, "xmax": maxx + pad, "ymax": maxy + pad,
            "spatialReference": {"wkid": 4326}}


def _pick_date_field(fields: list[dict]) -> str:
    date_fields = [f["name"] for f in fields if f.get("type") == "esriFieldTypeDate"]
    for hint in DATE_NAME_HINTS:
        for name in date_fields:
            if name.lower() == hint:
                return name
    if date_fields:
        return date_fields[0]
    for f in fields:
        if "date" in f["name"].lower():
            return f["name"]
    raise SystemExit(f"Could not find a date field. Fields: {[f['name'] for f in fields]}")


def _parse_dates(raw: pd.Series) -> pd.Series:
    """Parse dates to UTC timestamps. Numbers are epoch milliseconds (ArcGIS); text may mix formats."""
    if pd.api.types.is_numeric_dtype(raw):
        return pd.to_datetime(raw, unit="ms", utc=True, errors="coerce")
    try:  # pandas >= 2: parse each value on its own instead of guessing one format from the first
        return pd.to_datetime(raw, format="mixed", errors="coerce", utc=True)
    except (TypeError, ValueError):
        return pd.to_datetime(raw, errors="coerce", utc=True)


def _features_to_df(features: list[dict], date_field: str | None = None) -> pd.DataFrame:
    """Accepts ArcGIS JSON features (geometry x/y) or GeoJSON features (coordinates)."""
    rows = []
    for ft in features:
        attrs = ft.get("attributes") or ft.get("properties") or {}
        g = ft.get("geometry") or {}
        if "x" in g and "y" in g:
            lon, lat = g["x"], g["y"]
        elif g.get("type") == "Point":
            lon, lat = g["coordinates"][:2]
        else:  # geometry missing: fall back to the layer's own latitude/longitude attributes
            lat, lon = attrs.get("latitude"), attrs.get("longitude")
        if lat is None or lon is None:
            continue
        rows.append({"lat": lat, "lon": lon, **attrs})
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("No landslide points found in the result.")
    if date_field is None:
        date_field = next((c for c in df.columns if c.lower() in DATE_NAME_HINTS), None)
        if date_field is None:
            raise SystemExit(f"No date column found. Columns: {list(df.columns)}")
    df["event_date"] = _parse_dates(df[date_field]).dt.strftime("%Y-%m-%d")
    print(f"Using '{date_field}' as the landslide date.")
    return df


def download(layer_url: str, pad: float, page_size: int = 1000) -> pd.DataFrame:
    date_field, oid = KNOWN_DATE_FIELD, KNOWN_OID_FIELD
    try:  # the layer description is nice to have, not required
        meta = _get_json(layer_url, {"f": "json"})
        fields = meta.get("fields", [])
        print(f"Layer: {meta.get('name', layer_url)}")
        if fields:
            date_field = _pick_date_field(fields)
            oid = next((f["name"] for f in fields if f.get("type") == "esriFieldTypeOID"), oid)
        page_size = min(page_size, int(meta.get("maxRecordCount", page_size)))
    except RequestFailed as e:
        print(f"(Layer description unavailable: {e}. Using the known field names and continuing.)")
        page_size = min(page_size, KNOWN_MAX_RECORDS)

    env = _envelope(pad)
    features, offset = [], 0
    while True:
        params = _query_params(env, offset, page_size, oid)
        try:
            data = _get_json(f"{layer_url}/query", params)
        except RequestFailed as e:
            first = f"{layer_url}/query?{urllib.parse.urlencode(_query_params(env, 0, KNOWN_MAX_RECORDS, oid))}"
            raise SystemExit(
                f"The direct download failed: {e}\n\n"
                f"NASA's query service is probably unavailable. Use the manual route:\n"
                f"  1. Open {DOWNLOAD_PAGE}\n"
                f"  2. Download the COOLR / Global Landslide Catalog as CSV (or shapefile).\n"
                f"  3. Run: python hazards\\download_coolr.py --from-file <the downloaded file>\n"
                f"(If you can open this link in a browser and see data, save it and use --from-json instead:\n{first})\n"
            )
        feats = data.get("features", [])
        features.extend(feats)
        offset += len(feats)
        if not feats or (len(feats) < page_size and not data.get("exceededTransferLimit")):
            break
    return _features_to_df(features, date_field)


def from_json(path: str) -> pd.DataFrame:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("exceededTransferLimit"):
        print("WARNING: the saved result hit the server's record limit, so it may be incomplete. "
              "Tell me and I will change the query to fetch in pages.")
    return _features_to_df(data.get("features", []))


def _read_csv_any_encoding(path: str) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"Could not read {path} as text.")


def from_file(path: str, pad: float) -> pd.DataFrame:
    """Read a downloaded COOLR file (csv / shp / geojson / gpkg) and keep the Melamchi area."""
    if path.lower().endswith(".csv"):
        df = _read_csv_any_encoding(path)
        lat = next((c for c in df.columns if c.lower() in ("latitude", "lat")), None)
        lon = next((c for c in df.columns if c.lower() in ("longitude", "lon", "lng")), None)
        if not lat or not lon:
            raise SystemExit(f"No latitude/longitude columns in {path}. Columns: {list(df.columns)}")
        df = df.rename(columns={lat: "lat", lon: "lon"})
    else:
        import geopandas as gpd
        g = gpd.read_file(path)
        if g.crs is not None:
            g = g.to_crs(4326)
        if not (g.geometry.geom_type == "Point").all():
            g = g.assign(geometry=g.to_crs(32645).geometry.representative_point().to_crs(4326)
                         if g.crs is not None else g.geometry.representative_point())
        df = pd.DataFrame(g.drop(columns="geometry"))
        df["lon"], df["lat"] = g.geometry.x.to_numpy(), g.geometry.y.to_numpy()
    print(f"Read {len(df)} records from {path}.")

    df = df.dropna(subset=["lat", "lon"])
    minx, miny, maxx, maxy = MELAMCHI_BBOX
    keep = df["lat"].between(miny - pad, maxy + pad) & df["lon"].between(minx - pad, maxx + pad)
    df = df[keep].reset_index(drop=True)
    print(f"{len(df)} of them fall inside the Melamchi bounding box (+{pad} deg).")
    if df.empty:
        raise SystemExit("No landslides inside the Melamchi area in this file.")

    date_col = next((c for c in df.columns if c.lower() in DATE_NAME_HINTS), None)
    if date_col is None:
        raise SystemExit(f"No date column found. Columns: {list(df.columns)}")
    raw = df[date_col]
    df["event_date"] = _parse_dates(raw).dt.strftime("%Y-%m-%d")
    n_lost = int(raw.notna().sum() - df["event_date"].notna().sum())
    if n_lost:
        print(f"WARNING: {n_lost} date value(s) could not be read and were left empty.")
    print(f"Using '{date_col}' as the landslide date. Check a few (raw -> parsed):")
    for r, p_ in list(zip(raw, df["event_date"]))[:3]:
        print(f"    {r}  ->  {p_}")
    return df


def summarize(df: pd.DataFrame) -> None:
    d = pd.to_datetime(df["event_date"], errors="coerce")
    print(f"\n{len(df)} landslide point(s); {int(d.isna().sum())} without a usable date.")
    if d.notna().any():
        print(f"Dates span {d.min().date()} to {d.max().date()}.")
        print("Records per year (2015 onwards):")
        print(d[d.dt.year >= 2015].dt.year.value_counts().sort_index().to_string())
    print("\nWhat this means for each event (history = up to end of pre window; "
          "label = after it, up to end of post window):")
    for name, cfg in EVENTS.items():
        if cfg.get("region") != "melamchi":
            continue
        pre_end, post_end = pd.Timestamp(cfg["pre_window"][1]), pd.Timestamp(cfg["post_window"][1])
        print(f"  {name}: history {int((d <= pre_end).sum())}, "
              f"label {int(((d > pre_end) & (d <= post_end)).sum())}")
    for c in df.columns:
        if "accu" in c.lower() or c.lower().startswith("location_a"):
            print(f"\n'{c}' (location accuracy):\n{df[c].value_counts(dropna=False).to_string()}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Download COOLR landslide points for Melamchi.")
    ap.add_argument("--layer", default=DEFAULT_LAYER)
    ap.add_argument("--pad", type=float, default=0.1)
    ap.add_argument("--from-json", dest="from_json")
    ap.add_argument("--from-file", dest="from_file")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if OUT_PATH.exists() and not args.force:
        raise SystemExit(f"{OUT_PATH} already exists. Re-run with --force to overwrite it.")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if args.from_file:
        df = from_file(args.from_file, args.pad)
    elif args.from_json:
        df = from_json(args.from_json)
    else:
        df = download(args.layer, args.pad)
    front = ["lat", "lon", "event_date"]
    df = df[front + [c for c in df.columns if c not in front]]
    df.to_csv(OUT_PATH, index=False, encoding="utf-8")
    print(f"Saved {len(df)} rows to {OUT_PATH}")
    summarize(df)


if __name__ == "__main__":
    main()
