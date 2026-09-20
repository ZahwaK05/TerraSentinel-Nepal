"""
Order terrain-corrected (RTC) Sentinel-1 products for the 4 Melamchi pre/post
scenes from ASF HyP3 (free "HyP3 Basic" credits), then download them.

Why RTC: plain GRD is not terrain-corrected. In 800-5,800 m terrain, pixels are
displaced by up to kilometres, so a pre/post difference would land on the wrong
100 m cells. HyP3 RTC uses the Copernicus 30 m DEM and delivers UTM GeoTIFFs.

Scenes (same relative orbit + direction within each event, from probe_s1_grd.py):
  MELAMCHI_2021  orbit 121 descending   pre 2021-06-03   post 2021-06-27
  MELAMCHI_2026  orbit 19  descending   pre 2026-06-25   post 2026-07-07   (Sentinel-1D)

Usage (run from the project root, env with hyp3_sdk + asf_search installed):
  python sentinel1\\hyp3_rtc_melamchi.py check                # look scenes up in ASF, show credits. Submits NOTHING.
  python sentinel1\\hyp3_rtc_melamchi.py submit               # submit all 4 (skips ones already submitted)
  python sentinel1\\hyp3_rtc_melamchi.py submit --only mel2026_pre   # or a single one
  python sentinel1\\hyp3_rtc_melamchi.py status
  python sentinel1\\hyp3_rtc_melamchi.py download             # products expire after ~14 days: download promptly

Needs EARTHDATA_USERNAME / EARTHDATA_PASSWORD in .env, and the ASF EULA accepted
on your Earthdata profile. Job names are publicly visible on HyP3: they contain
no personal information.

Unverified: whether ASF/HyP3 has and accepts the Sentinel-1D scenes for RTC.
`check` tells you whether ASF can see them; `status` shows if the jobs fail.
"""
import argparse
import os
import zipfile
from datetime import datetime, timedelta

from dotenv import load_dotenv

from config import DATA_RAW, MELAMCHI_BBOX

load_dotenv()

OUT_DIR = DATA_RAW / "sentinel1" / "rtc"

# key, event, window, scene start time (UTC) taken from the probe's scene ids
TARGETS = [
    ("mel2021_pre",  "MELAMCHI_2021", "pre",  "20210603T001132"),
    ("mel2021_post", "MELAMCHI_2021", "post", "20210627T001134"),
    ("mel2026_pre",  "MELAMCHI_2026", "pre",  "20260625T001841"),
    ("mel2026_post", "MELAMCHI_2026", "post", "20260707T001841"),
]
JOB_PREFIX = "terrasentinel-"

_cx = (MELAMCHI_BBOX[0] + MELAMCHI_BBOX[2]) / 2
_cy = (MELAMCHI_BBOX[1] + MELAMCHI_BBOX[3]) / 2
STUDY_POINT_WKT = f"POINT({_cx} {_cy})"


def _login():
    import hyp3_sdk as sdk
    user, pw = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if not user or not pw:
        raise SystemExit("EARTHDATA_USERNAME / EARTHDATA_PASSWORD not found in .env")
    try:
        return sdk.HyP3(username=user, password=pw)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            f"HyP3 login failed: {e}\nCheck the credentials, and that the ASF EULA is accepted "
            f"on your Earthdata profile (https://urs.earthdata.nasa.gov)."
        )


def _find_scene(key, ts):
    """Look the scene up in ASF by acquisition time; return its scene name (what HyP3 needs)."""
    import asf_search as asf
    t0 = datetime.strptime(ts, "%Y%m%dT%H%M%S")
    res = asf.search(
        platform=asf.PLATFORM.SENTINEL1,
        processingLevel=asf.PRODUCT_TYPE.GRD_HD,
        beamMode="IW",
        start=(t0 - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        end=(t0 + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        intersectsWith=STUDY_POINT_WKT,
    )
    hits = [r for r in res if ts in str(r.properties.get("sceneName", ""))]
    if not hits:
        return None, None
    p = hits[0].properties
    info = (f"{p.get('platform')} {p.get('flightDirection')} path/orbit {p.get('pathNumber')} "
            f"start {p.get('startTime')}")
    return p["sceneName"], info


def _select(only):
    t = [x for x in TARGETS if only is None or x[0] == only]
    if not t:
        raise SystemExit(f"--only must be one of {[x[0] for x in TARGETS]}")
    return t


def cmd_check(args):
    print("Looking the scenes up in ASF (nothing is submitted)...")
    missing = []
    for key, ev, win, ts in _select(args.only):
        scene, info = _find_scene(key, ts)
        if scene:
            print(f"  FOUND   {key:13s} {scene}\n          {info}")
        else:
            print(f"  MISSING {key:13s} no Sentinel-1 IW GRD-H scene at {ts} UTC over the study area in ASF")
            missing.append(key)
    hyp3 = _login()
    print(f"\nHyP3 credits remaining: {hyp3.check_credits()}")
    try:
        costs = hyp3.costs()
        print("RTC cost entry from HyP3:", costs.get("RTC_GAMMA", "(no RTC_GAMMA key; keys: %s)" % list(costs)[:8]))
    except Exception as e:  # noqa: BLE001
        print(f"(could not read the cost table: {e})")
    if missing:
        print(f"\nASF cannot see: {missing}. If these are the Sentinel-1D scenes, RTC via ASF may not be "
              f"possible for them - tell me and we will use another same-orbit pair or report the gap.")


def cmd_submit(args):
    hyp3 = _login()
    print(f"Credits before: {hyp3.check_credits()}")
    for key, ev, win, ts in _select(args.only):
        name = JOB_PREFIX + key
        existing = [j for j in hyp3.find_jobs(name=name) if j.status_code != "FAILED"]
        if existing:
            print(f"  {key}: already submitted ({existing[0].job_id}, {existing[0].status_code}) - skipping")
            continue
        scene, info = _find_scene(key, ts)
        if not scene:
            print(f"  {key}: scene not found in ASF - NOT submitted")
            continue
        batch = hyp3.submit_rtc_job(scene, name=name, resolution=30, scale="power",
                                    radiometry="gamma0", speckle_filter=False)
        print(f"  {key}: submitted {scene} -> job {batch[0].job_id}")
    print(f"Credits after: {hyp3.check_credits()}")
    print("Run 'status' to follow progress. RTC jobs usually take from minutes to an hour or so.")


def cmd_status(args):
    hyp3 = _login()
    for key, *_ in _select(args.only):
        jobs = hyp3.find_jobs(name=JOB_PREFIX + key)
        if not len(jobs):
            print(f"  {key}: not submitted")
        for j in jobs:
            extra = f" - {j.status_code}"
            if j.failed():
                extra += f" (reason: {getattr(j, 'processing_times', '')} {getattr(j, 'job_parameters', '')})"
            print(f"  {key}: {j.job_id}{extra}")


def cmd_download(args):
    hyp3 = _login()
    for key, *_ in _select(args.only):
        jobs = hyp3.find_jobs(name=JOB_PREFIX + key, status_code="SUCCEEDED")
        if not len(jobs):
            print(f"  {key}: no succeeded job yet - run 'status'")
            continue
        dest = OUT_DIR / key
        files = jobs.download_files(dest)
        for f in files:
            if str(f).lower().endswith(".zip"):
                with zipfile.ZipFile(f) as z:
                    z.extractall(dest)
        tifs = sorted(p.name for p in dest.rglob("*.tif"))
        print(f"  {key}: {len(tifs)} tif(s) in {dest}")
        for t in tifs:
            print(f"      {t}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "submit", "status", "download"])
    ap.add_argument("--only", help="one of: " + ", ".join(t[0] for t in TARGETS))
    args = ap.parse_args()
    {"check": cmd_check, "submit": cmd_submit, "status": cmd_status, "download": cmd_download}[args.command](args)


if __name__ == "__main__":
    main()
