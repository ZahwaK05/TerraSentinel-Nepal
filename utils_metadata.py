"""
Shared helper: every data-fetch/processing script calls log_metadata(...)
once it finishes, so metadata.csv stays a complete, consistent record of
where every dataset came from and what was done to it — per project rule
"record source info for every dataset".
"""
import csv
from datetime import datetime, timezone
from config import METADATA_CSV

FIELDS = ["dataset", "source", "date", "resolution", "crs", "processing", "notes"]


def log_metadata(dataset, source, resolution, crs, processing, notes=""):
    """Append one row to metadata.csv. `date` is recorded automatically as
    the processing run date (UTC) — put the data's own acquisition date in
    `notes` if it differs, since that's often a range (e.g. a composite)."""
    new_file = not METADATA_CSV.exists()
    with open(METADATA_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({
            "dataset": dataset,
            "source": source,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "resolution": resolution,
            "crs": crs,
            "processing": processing,
            "notes": notes,
        })


def log_skipped(dataset, reason):
    """Use this instead of fabricating a column: record why a dataset/
    feature was dropped rather than silently omitting it."""
    log_metadata(
        dataset=dataset,
        source="N/A",
        resolution="N/A",
        crs="N/A",
        processing="SKIPPED",
        notes=f"Not included in feature table — {reason}",
    )
