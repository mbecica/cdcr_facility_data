# Buildings

Capital projects, condition ratings, institution profiles, the state property inventory, building heights and footprints, and every place a source names a building. `crosswalk/buildings.csv` combines the inventory and the mentions.

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `building_heights.csv` | A standing building or shade canopy inside a CDCR institution boundary: footprint geometry metrics, LiDAR roof heights, building category, and story count | 34 institutions (2,033 footprints; LiDAR 2014–2023, NAIP 2024) | USGS 3DEP LiDAR, FEMA USA Structures, Overture Maps, USDA NAIP |
| `building_footprints.geojson` | GeoJSON polygon feature matching `building_heights.csv` 1:1 on `footprint_id` | 34 institutions (2,033 polygons) | FEMA USA Structures, Overture Maps, LiDAR/NAIP patches |
| `mpar_projects.csv` | A capital project in one year's report: status, phase, funding or cost, scope, justification | Reports 2022–2025 | Master Plan Annual Reports (MPAR) |
| `mpar_envelope_last_completed.csv` | An institution: most recent roofing or envelope project | Reports 2020–2025 | MPAR |
| `infrastructure_plan_profiles_2026.csv` | An institution: square footage, acres, design capacity by bed type, security levels, treatment plants, deactivations | April 2026 | Infrastructure Master Plan, Appendix 1 |
| `condition_assessment_2026.csv` | An institution and system: condition rating of 45 systems | May 2026 | Infrastructure Master Plan, Appendix 2, p. 2 |
| `condition_assessment_rank_2026.csv` | An institution: overall rank, 1 (worst) to 31 (best) | May 2026 | Same, p. 1 |
| `spi_cdcr_structures.csv` | A CDCR structure in the state property inventory, with its identifiers as entered | Oct 6, 2026 | DGS Statewide Property Inventory (SPI) |
| `building_mentions.csv` | A place a source names a building or housing unit | Various | MPARs, Capital Outlay Quarterly Reports, PREA audits, CDCR web pages, court filings |
| `../../crosswalk/buildings.csv` | A building or housing unit, combining SPI and the mentions | Various | `build_buildings.py` |

## Caveats

- Condition ratings were assigned by each institution's plant operations staff, not through a formal facility condition assessment. Each rating covers the whole institution, and the rank is weighted by each system's operational impact.
- SPI has no beds or capacity, and at some institutions has no building numbers or lists several buildings as one record.
- A mention joins an SPI structure when the building numbers match (ignoring hyphens, spaces, and leading zeros), when it matches a housing unit SPI names on the same row, or when its name matches an SPI structure name unique at the institution. Otherwise mentions merge only when they use the same number or name, so one building can still appear under two keys. Wings and sides of a building are kept separate from the building.
- Coverage of the inventory's fields varies widely between institutions.
- For `building_heights.csv` and `building_footprints.geojson`, roof heights (feet above surrounding ground) come from USGS 3DEP EPT LiDAR calibrated against 3–15 m surrounding ground rings and 1 m eroded roof interiors, reconciled with Overture Maps and LiDAR/NAIP residual scans inside HIFLD/RAPT prison boundaries (`2,033` structures across 34 institutions, including closed facilities `CAC`, `CVSP`, and `FWF`). Source polygons with zero LiDAR roof returns and no standing structure visible in 2024 NAIP imagery (`80` polygons), plus one non-occupied utility apron (`ASP-fp-024`), are excluded.
- Two post-LiDAR yard/sallyport canopies (`CAC-fp-007` and `KVSP-fp-049`) are retained as `building_category = canopy` with blank `stories` (`story_confidence = indeterminate`). One library/chapel/gym building (`VSP-fp-023`) fell in a LiDAR tile void so its height percentiles remain blank, while its `1`-story assignment (`story_confidence = medium`) is derived from matching SPI structure `43778` (`BLDG 407 - Library/Chapel/Gym`) and visual inspection of 2024 NAIP imagery.

## Fields

Condition ratings: **Plus** (expected to exceed 20 years of operation), **Good** (generally well maintained), **Fair** (needs repairs, typical wear and tear), **Poor** (significant disrepair), **Failing** (at risk of failure or unusable), **N/A** (the system doesn't exist at the institution).

`mpar_projects.csv` statuses: complete, active, proposed, future within 5 years, and future in 5–10 years.

In `building_heights.csv` (and `building_footprints.geojson` feature properties):

| Column | Meaning |
| :--- | :--- |
| `cdcr_code` | Institution code joining `crosswalk/institutions.csv`. |
| `footprint_id` | Unique per-building identifier (`{cdcr_code}-fp-{n}` from USA Structures, `-ovt-{n}` from Overture patch, `-lid-{n}` from LiDAR/NAIP patch). |
| `usa_structures_build_id`, `overture_id` | Upstream source feature IDs where matched; blank otherwise. |
| `lat`, `lon` | Polygon centroid in WGS84. |
| `footprint_sqft`, `solidity` | Polygon footprint area in sq ft and area / convex-hull solidity ratio (`0–1`). |
| `footprint_source` | Geometry provenance (`usa_structures`, `overture_patch`, `lidar_naip_patch`). |
| `building_category` | Broad functional group: `housing`, `program_admin_medical`, `support_warehouse_pia`, `guard_tower_utility`, or `canopy`. |
| `is_housing`, `housing_prototype` | Whether the structure houses incarcerated people (`yes`/`no`) and architectural prototype tag (e.g., `270_housing_unit`, `180_housing_unit`, `level1_dorm_standard`, `cross_pod_dorm_1story`, or `non_housing`). |
| `stories`, `stories_range` | Point story count and plausible min–max tier range (`1`, `1-2`, `2`, `2-3`, `3`, `5`); blank when indeterminate (`canopy`). |
| `story_confidence`, `story_method` | Story confidence (`high`, `medium`, `indeterminate`) and derivation method. |
| `roof_p10_ft`–`roof_p98_ft`, `roof_spread_ft` | LiDAR roof height percentiles above ground (`ft`) and `p90 - p10` spread; blank where LiDAR height is unavailable. |
| `multi_tier_flag`, `sub_tier_heights_ft` | Whether distinct multi-tier roof modes appear (`yes`/`no`) and peak height modes with point shares. |
| `ground_slope_ft` | Elevation spread (`p90 - p10`, ft) across the surrounding ground calibration ring. |
| `height_source`, `lidar_project`, `lidar_year` | LiDAR classification tier used (`ept_laz_cls6`, `ept_laz_cls1_fallback`, `none`), USGS 3DEP EPT collection, and LiDAR collection year (`2014–2023`). |

In `crosswalk/buildings.csv`:

| Column | Meaning |
| :--- | :--- |
| `building_key` | `{cdcr_code}-{building}` for a numbered building, `{cdcr_code}-spi{n}` for an SPI structure with no usable building number (`n` is DGS's structure number), or `{cdcr_code}-{name}` for a building sources name but don't number. Where a source counts buildings without naming them, each gets a placeholder key, `{cdcr_code}-ph-{facility}-{type}{n}`. |
| `placeholder` | `yes` if this project created the key rather than taking it from a source. |
| `building` | Building or housing unit number. SPI prefixes such as `BLDG.` are removed and DGS's five-digit serial numbers aren't used as building numbers; the original values stay in `spi_agency_structure_no`. A structure SPI describes as several buildings is written with all of them (`A1/A2`). Where SPI gives several structures one number, the housing structure among them takes it and the others are keyed by DGS structure number. |
| `aliases` | Other IDs sources use for the building, including a housing unit SPI names on the same row. |
| `building_name` | Names the sources give the building. |
| `facility`, `use`, `program` | Every value the sources state, separated by semicolons; blank where no source states it. Facility is never inferred from the building number. Programs are followed by the date the source gives them. |
| `beds` | Bed capacity as stated by each source, with its date. |
| `year_built` | From SPI, or from a source that states it for that building or every building in a group it counts. Ranges aren't used. |
| `sqft` | Square footage, from SPI. |
| `spi_structure_type` | SPI's category. `use` comes from the other sources only. |
| `spi_structure_number`, `spi_agency_structure_no`, `spi_real_property_number` | SPI identifiers as entered. |
| `conflicts` | Columns where sources disagree. |
| `n_sources`, `sources` | Sources that name the building. MPAR sources are written `MPAR{year}:{project_id}`; others are the PDF filename. |

## Provenance

| Table | Source | Script and inputs | Covered through |
| :--- | :--- | :--- | :--- |
| `building_heights`, `building_footprints` | [USGS 3DEP EPT](https://registry.opendata.aws/usgs-lidar/), [FEMA USA Structures](https://disasters.geoplatform.gov/), [Overture Maps](https://overturemaps.org/), [USDA NAIP](https://naip-usdaonline.hub.arcgis.com/) | `scrapers/building_heights/`; RAPT prison boundaries, SPI cross-checks | 2023 LiDAR / 2024 NAIP |
| `mpar_projects` | [Master Plan Annual Reports](https://www.cdcr.ca.gov/fpcm/) | `extract_mpar_projects.py`; PDFs in `sources/cdcr_facilities_planning/` | 2025 report |
| `mpar_envelope_last_completed` | Same | Transcribed by hand | 2025 report |
| `infrastructure_plan_profiles_2026`, `condition_assessment_2026`, `condition_assessment_rank_2026` | [Infrastructure Master Plan](https://www.cdcr.ca.gov/fpcm/cdcr-infrastructure-master-plan/) | Transcribed by hand | May 2026 |
| `spi_cdcr_structures` | [SPI](https://services8.arcgis.com/a4GMqC2tQHvYiVtK/arcgis/rest/services/SPIPublicMapViewer/FeatureServer/1) | `fetch_spi_structures.py` | Oct 6, 2026 |
| `building_mentions` | The sources under Files; PDFs and saved pages in `sources/prea/`, `sources/cdcr_web/`, `sources/heat_cooling/` | Transcribed by hand, plus equipment rows from `extract_housing_cooling_types.py` | Oct 2026 |
| `crosswalk/buildings` | SPI and `building_mentions` | `build_buildings.py` | Oct 2026 |

## References

California Department of Corrections and Rehabilitation, Facilities Planning, Construction and Management. (2020–2025). *Master Plan Annual Report*.

California Department of Corrections and Rehabilitation, Facility Planning, Construction and Management. (2026, May). *Infrastructure Master Plan* and Appendices 1–3. https://www.cdcr.ca.gov/fpcm/cdcr-infrastructure-master-plan/

California Department of Corrections and Rehabilitation. (2018–2025). *PREA Audit Reports*. https://www.cdcr.ca.gov/prea/prea/reports-audits/ (2016–2019 reports: https://www.cdcr.ca.gov/wp-content/uploads/sites/186/2019/06/{code}-{year}-prea-report.pdf)

California Department of Corrections and Rehabilitation. (2026). *Facility Locator* [Institution web pages]. https://www.cdcr.ca.gov/facility-locator/

Department of General Services, Real Estate Services Division. (2026). *Statewide Property Inventory* [Structure layer, SPI Public Map Viewer]. https://services8.arcgis.com/a4GMqC2tQHvYiVtK/arcgis/rest/services/SPIPublicMapViewer/FeatureServer/1

Federal Emergency Management Agency (FEMA) & Oak Ridge National Laboratory. *USA Structures* [Building footprints] & *Prison Boundaries* (HIFLD / RAPT). https://disasters.geoplatform.gov/

Overture Maps Foundation. *Overture Maps Building Theme*. https://overturemaps.org/

U.S. Department of Agriculture, Farm Production and Conservation Business Center. (2024). *National Agriculture Imagery Program (NAIP)*. https://naip-usdaonline.hub.arcgis.com/

U.S. Geological Survey. (2014–2023). *3D Elevation Program (3DEP) Entwine Point Tiles*. https://registry.opendata.aws/usgs-lidar/
