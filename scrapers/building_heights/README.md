# Building Heights & Footprints Pipeline

Builds `data/buildings/building_heights.csv` and `data/buildings/building_footprints.geojson` across all 34 adult CDCR institutions (`2,011` standing structures and shade canopies; LiDAR collections 2014–2023, visually verified against 2024 NAIP imagery).

## Modules

- [`common.py`](common.py) — Shared workspace paths, HTTP/EPT/LAZ point-cloud loaders, NAIP canvas renderer, and ground-ring-calibrated USGS 3DEP LiDAR roof percentile extraction (`p10`–`p98`).
- [`fetch_sources.py`](fetch_sources.py) — Queries FEMA USA Structures polygons within CDCR RAPT boundaries (+300 m buffer), downloads/mosaics 4-band 2024 NAIP GeoTIFFs to `sources/imagery/naip_2024/`, extracts raw EPT LiDAR roof heights, and renders facility boundary QA overlays.
- [`reconcile_footprints.py`](reconcile_footprints.py) — Reconciles missing standing footprints from Overture Maps (`*_ovt-*`) and LiDAR+NAIP NDVI residuals (`*_lid-*`), and triages zero-roof polygons against 2024 NAIP signatures and [`triage_overrides.json`](triage_overrides.json).
- [`classify_stories.py`](classify_stories.py) — Classifies building categories, housing prototypes, sub-tier height modes, and story counts using [`housing_overrides.json`](housing_overrides.json) and read-only SPI structure cross-checks.
- [`build_building_heights.py`](build_building_heights.py) — Main entry point and exporter. Filters inside RAPT boundaries to standing structures and shade canopies, strips internal QA columns, and writes `data/buildings/building_heights.csv` and `data/buildings/building_footprints.geojson`.
- [`footprint_merges.json`](footprint_merges.json) — LiDAR patches folded into a main footprint: `merge` unions the outlines and recomputes the roof heights; `sliver` drops a strip of the same roof. `build_building_heights.py` applies it on every run.
- [`footprint_redraws.geojson`](footprint_redraws.geojson) — Outlines traced from LiDAR roof edges that replace source outlines not matching the standing buildings (`drop` lists the replaced IDs). `build_building_heights.py` applies it on every run.
- [`build_footprint_places.py`](build_footprint_places.py) — Links footprints to places by OpenStreetMap building name (`data/buildings/locations/footprint_places.csv`, one row per place) and place sets to their candidate footprints by equal counts (`footprint_sets.csv`, one row per set).

## Dependencies & Running

Requires `laspy[lazrs]`, `rasterio`, `shapely`, `pyproj`, `numpy`, `pillow`, and `overturemaps`. With cached intermediates in `notes/building_heights_pilot/all_34/`:

```bash
python3 scrapers/building_heights/build_building_heights.py
```

Pass `--fetch`, `--reconcile`, `--triage`, or `--qa-png` to `build_building_heights.py` to re-run upstream source downloads, footprint reconciliation, zero-roof triage, or QA overlay rendering before exporting.

## Imagery & Visual QA Overlays

- **Annotated QA overlays (`qa_images/`):** 34 WebP images (`~12.9 MB` total) showing final housing units color-coded by verified story count (`Cyan=1s`, `Gold=2s`, `Magenta=3s`, `Red=4-5s`, `Green=non-housing`), labels (`H:{id} [stories p50/p90]`), and canopies (`Teal`) overlaid on 2024 NAIP imagery.
- **Compressed NAIP 2024 base imagery (`sources/imagery/naip_2024_rgb/`):** 34 JPEG-compressed RGB GeoTIFF tiles (`~22.2 MB` total, retaining full `CRS`/georeferencing and NAIP item metadata tags). Raw 4-band RGB+NIR Deflate GeoTIFFs used for NDVI residual scans (`sources/imagery/naip_2024/`, `~250 MB`) are gitignored and can be re-fetched via `fetch_sources.py --force-naip`.

| Code | Institution | QA Overlay | Compressed NAIP RGB GeoTIFF |
| :--- | :--- | :--- | :--- |
| ASP | Avenal State Prison | [ASP_housing_qa.webp](qa_images/ASP_housing_qa.webp) | [ASP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/ASP_naip_2024_rgb.tif) |
| CAC | California City Correctional Center | [CAC_housing_qa.webp](qa_images/CAC_housing_qa.webp) | [CAC_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CAC_naip_2024_rgb.tif) |
| CAL | Calipatria State Prison | [CAL_housing_qa.webp](qa_images/CAL_housing_qa.webp) | [CAL_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CAL_naip_2024_rgb.tif) |
| CCI | California Correctional Institution | [CCI_housing_qa.webp](qa_images/CCI_housing_qa.webp) | [CCI_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CCI_naip_2024_rgb.tif) |
| CCWF | Central California Women's Facility | [CCWF_housing_qa.webp](qa_images/CCWF_housing_qa.webp) | [CCWF_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CCWF_naip_2024_rgb.tif) |
| CEN | Centinela State Prison | [CEN_housing_qa.webp](qa_images/CEN_housing_qa.webp) | [CEN_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CEN_naip_2024_rgb.tif) |
| CHCF | California Health Care Facility - Stockton | [CHCF_housing_qa.webp](qa_images/CHCF_housing_qa.webp) | [CHCF_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CHCF_naip_2024_rgb.tif) |
| CIM | California Institution for Men | [CIM_housing_qa.webp](qa_images/CIM_housing_qa.webp) | [CIM_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CIM_naip_2024_rgb.tif) |
| CIW | California Institution for Women | [CIW_housing_qa.webp](qa_images/CIW_housing_qa.webp) | [CIW_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CIW_naip_2024_rgb.tif) |
| CMC | California Men's Colony | [CMC_housing_qa.webp](qa_images/CMC_housing_qa.webp) | [CMC_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CMC_naip_2024_rgb.tif) |
| CMF | California Medical Facility | [CMF_housing_qa.webp](qa_images/CMF_housing_qa.webp) | [CMF_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CMF_naip_2024_rgb.tif) |
| COR | California State Prison, Corcoran | [COR_housing_qa.webp](qa_images/COR_housing_qa.webp) | [COR_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/COR_naip_2024_rgb.tif) |
| CRC | California Rehabilitation Center | [CRC_housing_qa.webp](qa_images/CRC_housing_qa.webp) | [CRC_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CRC_naip_2024_rgb.tif) |
| CTF | Correctional Training Facility | [CTF_housing_qa.webp](qa_images/CTF_housing_qa.webp) | [CTF_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CTF_naip_2024_rgb.tif) |
| CVSP | Chuckawalla Valley State Prison | [CVSP_housing_qa.webp](qa_images/CVSP_housing_qa.webp) | [CVSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/CVSP_naip_2024_rgb.tif) |
| FOL | Folsom State Prison | [FOL_housing_qa.webp](qa_images/FOL_housing_qa.webp) | [FOL_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/FOL_naip_2024_rgb.tif) |
| FWF | Folsom Women's Facility | [FWF_housing_qa.webp](qa_images/FWF_housing_qa.webp) | [FWF_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/FWF_naip_2024_rgb.tif) |
| HDSP | High Desert State Prison | [HDSP_housing_qa.webp](qa_images/HDSP_housing_qa.webp) | [HDSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/HDSP_naip_2024_rgb.tif) |
| ISP | Ironwood State Prison | [ISP_housing_qa.webp](qa_images/ISP_housing_qa.webp) | [ISP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/ISP_naip_2024_rgb.tif) |
| KVSP | Kern Valley State Prison | [KVSP_housing_qa.webp](qa_images/KVSP_housing_qa.webp) | [KVSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/KVSP_naip_2024_rgb.tif) |
| LAC | California State Prison, Los Angeles County | [LAC_housing_qa.webp](qa_images/LAC_housing_qa.webp) | [LAC_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/LAC_naip_2024_rgb.tif) |
| MCSP | Mule Creek State Prison | [MCSP_housing_qa.webp](qa_images/MCSP_housing_qa.webp) | [MCSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/MCSP_naip_2024_rgb.tif) |
| NKSP | North Kern State Prison | [NKSP_housing_qa.webp](qa_images/NKSP_housing_qa.webp) | [NKSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/NKSP_naip_2024_rgb.tif) |
| PBSP | Pelican Bay State Prison | [PBSP_housing_qa.webp](qa_images/PBSP_housing_qa.webp) | [PBSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/PBSP_naip_2024_rgb.tif) |
| PVSP | Pleasant Valley State Prison | [PVSP_housing_qa.webp](qa_images/PVSP_housing_qa.webp) | [PVSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/PVSP_naip_2024_rgb.tif) |
| RJD | RJ Donovan Correctional Facility | [RJD_housing_qa.webp](qa_images/RJD_housing_qa.webp) | [RJD_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/RJD_naip_2024_rgb.tif) |
| SAC | California State Prison, Sacramento | [SAC_housing_qa.webp](qa_images/SAC_housing_qa.webp) | [SAC_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/SAC_naip_2024_rgb.tif) |
| SATF | California Substance Abuse Treatment Facility | [SATF_housing_qa.webp](qa_images/SATF_housing_qa.webp) | [SATF_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/SATF_naip_2024_rgb.tif) |
| SCC | Sierra Conservation Center | [SCC_housing_qa.webp](qa_images/SCC_housing_qa.webp) | [SCC_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/SCC_naip_2024_rgb.tif) |
| SOL | California State Prison, Solano | [SOL_housing_qa.webp](qa_images/SOL_housing_qa.webp) | [SOL_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/SOL_naip_2024_rgb.tif) |
| SQ | San Quentin Rehabilitation Center | [SQ_housing_qa.webp](qa_images/SQ_housing_qa.webp) | [SQ_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/SQ_naip_2024_rgb.tif) |
| SVSP | Salinas Valley State Prison | [SVSP_housing_qa.webp](qa_images/SVSP_housing_qa.webp) | [SVSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/SVSP_naip_2024_rgb.tif) |
| VSP | Valley State Prison | [VSP_housing_qa.webp](qa_images/VSP_housing_qa.webp) | [VSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/VSP_naip_2024_rgb.tif) |
| WSP | Wasco State Prison | [WSP_housing_qa.webp](qa_images/WSP_housing_qa.webp) | [WSP_naip_2024_rgb.tif](../../sources/imagery/naip_2024_rgb/WSP_naip_2024_rgb.tif) |
