# Building Heights & Footprints Pipeline

Builds `data/buildings/building_heights.csv` and `data/buildings/building_footprints.geojson` across all 34 adult CDCR institutions (`2,033` standing structures and shade canopies; LiDAR collections 2014–2023, visually verified against 2024 NAIP imagery).

## Modules

- `common.py` — Shared workspace paths, HTTP/EPT/LAZ point-cloud loaders, NAIP canvas renderer, and ground-ring-calibrated USGS 3DEP LiDAR roof percentile extraction (`p10`–`p98`).
- `fetch_sources.py` — Queries FEMA USA Structures polygons within CDCR RAPT boundaries (+300 m buffer), downloads/mosaics 2024 NAIP 4-band GeoTIFFs to `sources/imagery/naip_2024/`, extracts raw EPT LiDAR roof heights, and renders facility boundary QA overlays.
- `reconcile_footprints.py` — Reconciles missing standing footprints from Overture Maps (`*_ovt-*`) and LiDAR+NAIP NDVI residuals (`*_lid-*`), and triages zero-roof polygons against 2024 NAIP signatures and `triage_overrides.json`.
- `classify_stories.py` — Classifies building categories, housing prototypes, sub-tier height modes, and story counts using `housing_overrides.json` and read-only SPI structure cross-checks.
- `build_building_heights.py` — Main entry point and exporter. Filters inside RAPT boundaries to standing structures and shade canopies, strips internal QA columns, and writes `data/buildings/building_heights.csv` and `data/buildings/building_footprints.geojson`.

## Dependencies & Running

Requires `laspy[lazrs]`, `rasterio`, `shapely`, `pyproj`, `numpy`, `pillow`, and `overturemaps`. With cached intermediates in `notes/building_heights_pilot/all_34/`:

```bash
python3 scrapers/building_heights/build_building_heights.py
```

Pass `--fetch`, `--reconcile`, `--triage`, or `--qa-png` to `build_building_heights.py` to re-run upstream source downloads, footprint reconciliation, zero-roof triage, or QA overlay rendering before exporting.

## Imagery & Visual QA Overlays

Raw 4-band NAIP 2024 GeoTIFFs downloaded by `fetch_sources.py` live under `sources/imagery/naip_2024/` (currently gitignored at `~250 MB` lossless Deflate; ~21 MB as RGB JPEG-compressed tiles if tracked later). Annotated QA overlay PNGs are written under `notes/building_heights_pilot/all_34/` (gitignored).
