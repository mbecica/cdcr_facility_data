# Building Heights & Footprints Pipeline

Builds `data/buildings/building_heights.csv` and `data/buildings/building_footprints.geojson` across all 34 adult CDCR institutions (`2,033` standing structures and canopies; LiDAR collections 2014–2023, visually verified against 2024 NAIP imagery).

## Scripts (Run Order)

1. `step1_extract_lidar_heights.py` — Fetches FEMA USA Structures polygons within CDCR RAPT boundaries, downloads/caches 2024 NAIP GeoTIFFs to `sources/imagery/naip_2024/` and USGS 3DEP EPT `.laz` point clouds to `notes/building_heights_pilot/tmp_ept/`, and computes ground-ring-calibrated building roof percentiles (`p10`–`p98`).
2. `step2a_reconcile_overture.py` — Links Overture Maps building IDs and patches missing footprints (`*_ovt-*`).
3. `step2b_scan_lidar_residuals.py` — Scans cached LiDAR + NAIP NDVI residuals for uncaptured buildings (`*_lid-*`).
4. `step2c_triage_zero_roof.py` — Cross-checks zero-roof polygons against 2024 NAIP imagery using `triage_overrides.json`.
5. `step2d_classify_housing_stories.py` — Classifies building categories, housing prototypes, sub-tier height modes, and story counts using `housing_overrides.json` and read-only SPI structure cross-checks.
6. `step2e_export_building_heights.py` — Filters to standing structures and shade canopies inside RAPT boundaries (excluding `80` non-building source polygons and excluded non-occupied utility aprons), strips internal QA columns, and exports `data/buildings/building_heights.csv` and `data/buildings/building_footprints.geojson`.

## Dependencies & Running

Requires `laspy[lazrs]`, `rasterio`, `shapely`, `pyproj`, `numpy`, `pillow`, and `overturemaps`. With cached intermediates in `notes/building_heights_pilot/all_34/`:

```bash
python3 scrapers/building_heights/step2d_classify_housing_stories.py
python3 scrapers/building_heights/step2e_export_building_heights.py
```
