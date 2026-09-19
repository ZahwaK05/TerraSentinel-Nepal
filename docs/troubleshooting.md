# Troubleshooting Guide

> Record recurring setup problems here so team members do not repeat the same debugging steps.
> Format: **Problem → Cause → Resolution**

---

## Table of Contents

- [Environment Setup](#environment-setup)
- [Geospatial Processing](#geospatial-processing)
- [ML / Risk Scoring](#ml--risk-scoring)
- [Frontend / Dashboard](#frontend--dashboard)
- [AWS / Infrastructure](#aws--infrastructure)
- [Open Questions](#open-questions)

---

## Environment Setup

### `GDAL not found` when installing `rasterio` or `gdal`

**Cause:** GDAL system library is not installed or not on PATH.

**Resolution (Ubuntu/Debian):**
```bash
sudo apt-get update && sudo apt-get install -y gdal-bin libgdal-dev
export CPLUS_INCLUDE_PATH=/usr/include/gdal
export C_INCLUDE_PATH=/usr/include/gdal
pip install gdal==$(gdal-config --version)
```

**Resolution (macOS with Homebrew):**
```bash
brew install gdal
pip install gdal
```

---

### `proj` errors on coordinate transformations

**Cause:** `PROJ_LIB` environment variable not set or mismatched proj version.

**Resolution:** Ensure `PROJ_LIB` is set in `.env` and matches the installed proj version:
```bash
proj --version
# Set PROJ_LIB=/path/to/share/proj in .env
```

---

## Geospatial Processing

### SAR image shows all zeros after preprocessing

**Cause:** Incorrect band selection or dB conversion applied twice.

**Resolution:** Check `geospatial/sar/preprocess.py` — ensure `to_db=True` is only set once in the pipeline config. Verify band index matches the GRD product (VV=0, VH=1 for Sentinel-1).

---

### NDWI threshold produces too many false positives

**Cause:** Threshold is too low for the specific scene (shadows, ice).

**Resolution:** Adjust `FLOOD_THRESHOLD_NDWI` in `.env`. Current recommended range: 0.25–0.35 for Melamchi scenario. Document threshold decisions as open questions; do not treat them as settled.

---

## ML / Risk Scoring

### SageMaker endpoint returns 500 in dev

**Cause:** IAM role missing `sagemaker:InvokeEndpoint` permission, or endpoint not deployed.

**Resolution:**
```bash
# Check endpoint status
aws sagemaker describe-endpoint --endpoint-name terrasentinel-risk-dev

# Run locally instead
python services/risk-scorer/run_local.py --scenario melamchi --mode demo
```

---

### Risk scores are all identical (no variation across grid cells)

**Cause:** Feature normalization producing constant output, or model loaded wrong version.

**Resolution:** Check `RISK_MODEL_VERSION` in `.env`. Verify feature matrix shape before inference. Add `--debug` flag to `run_local.py` to print feature statistics.

---

## Frontend / Dashboard

### Map tiles not loading (blank map)

**Cause:** `NEXT_PUBLIC_MAPBOX_TOKEN` is not set or expired.

**Resolution:** Copy a valid public token from Mapbox dashboard to `.env`. For CI, add to GitHub Secrets as `MAPBOX_TOKEN_CI`.

---

### Timeline slider does not update map layers

**Cause:** Event listener detached after hot-reload during development.

**Resolution:** Hard-refresh the browser (`Ctrl+Shift+R`). If the issue persists in production, check the `useEffect` cleanup in `frontend/src/components/TimelineSlider.tsx`.

---

## AWS / Infrastructure

### Terraform `apply` fails with `AccessDenied`

**Cause:** IAM user/role missing required permissions for the resources being created.

**Resolution:** Ensure the deploying identity has the permissions listed in `infrastructure/terraform/iam-policy-example.json`. Contact the team lead to update permissions.

---

### Lambda cold-start timeout on first invocation

**Cause:** Lambda with large dependencies (e.g., rasterio) takes > 15 s to initialize.

**Resolution:** Enable Lambda SnapStart (Java) or use a Lambda container image with pre-warmed layers. See `infrastructure/terraform/modules/lambda/` for the container image option.

---

## Open Questions

> Decisions listed here require team review and must not be treated as settled assumptions.

| # | Question | Context | Owner | Status |
|---|---------|---------|-------|--------|
| 1 | What NDWI threshold is appropriate for GLOFs vs. riverine floods? | Current value 0.3 is estimated. | Geospatial lead | Open |
| 2 | What is the acceptable model accuracy (F1) before demo? | No benchmark defined yet. | ML lead | Open |
| 3 | How fresh must rainfall data be to trigger a live alert? | Staleness window not agreed. | Backend lead | Open |
| 4 | Who owns the demonstration dataset licensing for DHM gauge data? | Requires attribution; public use terms unclear. | Data lead | Open |
| 5 | Under what conditions should `ALERT_MODE` switch from `mock` to `live`? | Must have explicit sign-off process. | Team lead | Open |
