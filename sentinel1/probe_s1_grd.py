"""
Sentinel-1 GRD availability check for every pre/post window in config.EVENTS.
Downloads NOTHING. Slow on purpose: the Copernicus server rate-limits (HTTP 429),
so this pauses between searches and retries with growing waits.

Run from the project root:
    python sentinel1/probe_s1_grd.py

What it does:
- searches ONLY the 'sentinel-1-grd' collection, one window at a time
- keeps IW scenes that have VV+VH and fully cover the bbox
- groups scenes by (relative orbit, ascending/descending)
- suggests the pre/post pair with the SAME orbit + direction and the smallest
  gap between them (different geometry looks like "change" but is not)
- saves every candidate to data/raw/sentinel1/grd_candidates.csv
"""
import csv
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_RAW, EVENTS, MELAMCHI_BBOX, RASUWA_BBOX  # noqa: E402

STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"
COLLECTION = "sentinel-1-grd"
BBOX_BY_REGION = {"melamchi": MELAMCHI_BBOX, "rasuwa": RASUWA_BBOX}
PAUSE_S = 15                          # wait between searches
RETRY_WAITS = [30, 60, 120, 240, 480]  # seconds, used only after a 429


def covers(item, bbox):
    """True if the scene footprint fully contains the bbox."""
    try:
        from shapely.geometry import box, shape
        return bool(shape(item.geometry).contains(box(*bbox)))
    except Exception:
        b = item.bbox
        return b[0] <= bbox[0] and b[1] <= bbox[1] and b[2] >= bbox[2] and b[3] >= bbox[3]


def search_window(cat, bbox, start, end):
    """Return list of items, or None if the search failed."""
    rng = f"{start}T00:00:00Z/{end}T23:59:59Z"
    for wait in [0] + RETRY_WAITS:
        if wait:
            print(f"    rate limited - waiting {wait}s ...")
            time.sleep(wait)
        try:
            return list(cat.search(collections=[COLLECTION], bbox=bbox,
                                   datetime=rng, limit=50, max_items=200).items())
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "429" in msg or "Rate limit" in msg:
                continue
            print("    search failed:", repr(e)[:200])
            return None
    print("    gave up after repeated rate limiting - rerun later")
    return None


def to_row(item, event_id, window, bbox):
    p = item.properties
    return {
        "event_id": event_id,
        "window": window,
        "id": item.id,
        "date": str(p.get("datetime", ""))[:10],
        "platform": p.get("platform", "?"),
        "orbit": p.get("sat:relative_orbit", "?"),
        "state": p.get("sat:orbit_state", "?"),
        "mode": p.get("sar:instrument_mode", "?"),
        "pols": ",".join(p.get("sar:polarizations") or []) or "?",
        "covers_bbox": covers(item, bbox),
    }


def usable(row):
    """IW + VV/VH + full coverage. Unknown ('?') properties are kept but flagged."""
    if row["mode"] not in ("IW", "?"):
        return False
    if row["pols"] != "?" and not {"VV", "VH"} <= set(row["pols"].split(",")):
        return False
    return bool(row["covers_bbox"])


def pick_pairs(pre, post):
    """Pairs sharing orbit+direction, sorted by smallest days between the scenes."""
    key = lambda r: (r["orbit"], r["state"])  # noqa: E731
    common = {key(r) for r in pre} & {key(r) for r in post}
    out = []
    for k in common:
        a = max((r for r in pre if key(r) == k), key=lambda r: r["date"])    # latest pre
        b = min((r for r in post if key(r) == k), key=lambda r: r["date"])   # earliest post
        gap = (dt.date.fromisoformat(b["date"]) - dt.date.fromisoformat(a["date"])).days
        out.append((gap, k, a, b))
    return sorted(out, key=lambda x: x[0])


def main():
    from pystac_client import Client

    today = dt.date.today()
    cat = Client.open(STAC_URL)
    all_rows, summary = [], []
    first_item_shown = False

    for event_id, cfg in EVENTS.items():
        bbox = BBOX_BY_REGION[cfg["region"]]
        found = {}
        for w in ("pre", "post"):
            span = cfg.get(f"{w}_window")
            if not span:
                continue
            start, end = span
            if dt.date.fromisoformat(start) > today:
                print(f"{event_id} {w}: window has not started yet - skipped")
                continue
            if dt.date.fromisoformat(end) > today:
                print(f"{event_id} {w}: window still open, searching up to {today}")
                end = today.isoformat()
            print(f"{event_id} {w} ({start} -> {end}) ...")
            items = search_window(cat, bbox, start, end)
            time.sleep(PAUSE_S)
            if items is None:
                found[w] = None
                continue
            if items and not first_item_shown:
                print("    (property names on first scene:", sorted(items[0].properties)[:40], ")")
                first_item_shown = True
            rows = [to_row(i, event_id, w, bbox) for i in items]
            good = [r for r in rows if usable(r)]
            print(f"    {len(rows)} scenes found, {len(good)} usable (IW, VV+VH, cover the bbox)")
            groups = {}
            for r in good:
                groups.setdefault((r["orbit"], r["state"]), []).append(r["date"])
            for k, ds in sorted(groups.items(), key=lambda kv: str(kv[0])):
                print(f"      orbit {k[0]} {k[1]}: {len(ds)} scene(s), {min(ds)} .. {max(ds)}")
            all_rows.extend(good)
            found[w] = good

        if found.get("pre") and found.get("post"):
            pairs = pick_pairs(found["pre"], found["post"])
            if pairs:
                gap, k, a, b = pairs[0]
                print(f"  BEST PAIR for {event_id}: orbit {k[0]} {k[1]}")
                print(f"    pre : {a['date']}  {a['id']}")
                print(f"    post: {b['date']}  {b['id']}   (gap {gap} days)")
                summary.append((event_id, "pair found", gap))
            else:
                print(f"  {event_id}: NO pre/post pair with the same orbit + direction")
                summary.append((event_id, "no same-orbit pair", None))
        else:
            summary.append((event_id, "missing a window / search failed", None))

    out_dir = DATA_RAW / "sentinel1"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "grd_candidates.csv"
    if all_rows:
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0]))
            w.writeheader()
            w.writerows(all_rows)
        print(f"\nSaved {len(all_rows)} candidate scenes to {out}")

    print("\nSUMMARY")
    for ev, status, gap in summary:
        print(f"  {ev}: {status}" + (f" (gap {gap} days)" if gap is not None else ""))
    print("Nothing was downloaded.")


if __name__ == "__main__":
    main()
