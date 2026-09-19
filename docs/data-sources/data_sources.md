# Data Sources

> All datasets used in TerraSentinel-Nepal must be documented here.
> Before adding a dataset, confirm licensing allows use in this project.

---

## Summary Table

| Dataset | Provider | License | Resolution | Update Frequency | Demo Sample | PII Risk |
|---------|----------|---------|------------|-----------------|-------------|---------|
| Sentinel-1 SAR (GRD) | ESA Copernicus | Open – CC BY-SA | 10 m | ~6 days | Yes | None |
| Sentinel-2 L2A | ESA Copernicus | Open – CC BY-SA | 10 m | ~5 days | No (cloud cover) | None |
| ALOS DEM 30 m | JAXA | Free (non-commercial research) | 30 m | Static | Yes | None |
| GPM IMERG Final Run | NASA | Open | 0.1° (~10 km) | Monthly | Yes | None |
| GPM IMERG Late Run | NASA | Open | 0.1° (~10 km) | ~18 h lag | No (live only) | None |
| OSM Road & Infrastructure | OpenStreetMap contributors | ODbL | Variable | Continuous | Yes (extract) | None |
| DHM River Gauge Data | Dept. of Hydrology & Meteorology, Nepal | Requires attribution | Station-level | Daily | Yes (sample) | None |

---

## Detailed Entries

### Sentinel-1 SAR

- **Description:** C-band synthetic aperture radar, VV+VH polarisation, IW mode Ground Range Detected (GRD) product.
- **Use:** Water-change detection, flood extent mapping.
- **Access:** [Copernicus Data Space](https://dataspace.copernicus.eu/) or AWS Open Data (Sentinel-1).
- **Attribution:** Contains modified Copernicus Sentinel data [year], processed by ESA.
- **Limitations:** Affected by layover and shadow in steep terrain. Double-bounce from buildings can mimic water signal.

### ALOS DEM (ALOS World 3D 30 m)

- **Description:** Global 30 m DEM derived from ALOS PRISM stereo imagery.
- **Use:** Slope, flow direction, flow accumulation, impact-corridor delineation.
- **Access:** [JAXA ALOS Research and Application Project](https://www.eorc.jaxa.jp/ALOS/en/aw3d30/).
- **Attribution:** JAXA, METI. Use in publications requires citation of Takaku et al. (2020).
- **Limitations:** 30 m resolution may miss narrow gorges. Hydrological conditioning (pit-filling) required.

### GPM IMERG

- **Description:** Global Precipitation Measurement Integrated Multi-satellitE Retrievals for GPM.
- **Use:** Rainfall accumulation input to risk model.
- **Access:** [NASA GES DISC](https://disc.gsfc.nasa.gov/).
- **Attribution:** Huffman, G.J. et al. (2019). GPM IMERG. NASA/GSFC, Greenbelt, MD, USA.
- **Limitations:** ~10 km spatial resolution. Underestimates orographic rainfall in complex terrain. Late Run has ~18 h latency.

### OpenStreetMap

- **Description:** Community-contributed map data — roads, bridges, buildings, hospitals, schools.
- **Use:** Infrastructure exposure assessment.
- **Access:** [Overpass API](https://overpass-api.de/) or downloaded via Geofabrik.
- **Attribution:** (c) OpenStreetMap contributors. ODbL licence.
- **Limitations:** Coverage is incomplete in rural Nepal. Attributes may be outdated.

### DHM River Gauge Data

- **Description:** River stage and discharge measurements from the Department of Hydrology and Meteorology, Nepal.
- **Use:** Validation of flood extent; Melamchi scenario ground truth.
- **Access:** Via DHM Nepal data-sharing agreement. Contact details in private project wiki.
- **Attribution:** Department of Hydrology and Meteorology, Government of Nepal.
- **Limitations:** Station coverage is sparse in remote catchments. Real-time access requires DHM partnership.

> **Open Question:** Does our intended use of DHM data for a public demonstration comply with DHM's data-sharing terms? This must be confirmed before any DHM data is included in a public release.

---

## Prohibited Data Sources

The following must NOT be used without explicit legal review and team lead approval:

- Commercial satellite providers without a confirmed license for demonstration use.
- Any dataset containing personally identifiable information about citizens.
- Restricted government datasets without a data-sharing agreement in place.
