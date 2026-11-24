# Buildings

Capital project logs, condition ratings, institution profiles, the state property inventory, building heights and footprints, and the location tables that link facilities, housing units and buildings.

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `building_heights.csv` | A standing building or shade canopy inside a CDCR institution boundary: footprint geometry metrics, LiDAR roof heights, building category, and story count | 34 institutions (2,011 footprints; LiDAR 2014–2023, NAIP 2024) | USGS 3DEP LiDAR, FEMA USA Structures, Overture Maps, USDA NAIP |
| `building_footprints.geojson` | GeoJSON polygon feature matching `building_heights.csv` 1:1 on `footprint_id` | 34 institutions (2,011 polygons) | FEMA USA Structures, Overture Maps, LiDAR/NAIP patches |
| `mpar_projects.csv` | A capital project in one year's report: status, phase, funding or cost, scope, justification | Reports 2022–2025 | Master Plan Annual Reports (MPAR) |
| `mpar_envelope_last_completed.csv` | An institution: most recent roofing or envelope project | Reports 2020–2025 | MPAR |
| `infrastructure_plan_profiles_2026.csv` | An institution: square footage, acres, design capacity by bed type, security levels, treatment plants, deactivations | April 2026 | Infrastructure Master Plan, Appendix 1 |
| `condition_assessment_2026.csv` | An institution and system: condition rating of 45 systems | May 2026 | Infrastructure Master Plan, Appendix 2, p. 2 |
| `condition_assessment_rank_2026.csv` | An institution: overall rank, 1 (worst) to 31 (best) | May 2026 | Same, p. 1 |
| `spi_cdcr_structures.csv` | A CDCR structure in the state property inventory, with its identifiers as entered | Oct 6, 2026 | DGS Statewide Property Inventory (SPI) |
| `building_mentions.csv` | A place a source names a building or housing unit | Various | MPARs, Capital Outlay Quarterly Reports, PREA audits, CDCR web pages, court filings |
| `locations/facilities.csv` | A facility, yard or complex within an institution | 161 facilities, 32 institutions | PREA audits, *Coleman* Receiver CQIT audits, CDCR Facility Locator, heat-log headers |
| `locations/housing_units.csv` | A housing unit | 788 units, 32 institutions | Same, plus SPI, MPARs and the 2024 heat logs |
| `locations/places.csv` | A building or other structure | 3,620 places, 32 institutions | SPI, `building_mentions.csv`, OpenStreetMap |
| `locations/place_parts.csv` | A wing, side, section or post of a place | 211 parts | Heat-log headers, PREA audits, SPI |
| `locations/place_sets.csv` | A place in a set of identical buildings | 7 sets, 52 places (HDSP, KVSP, SVSP) | SPI |
| `locations/unit_links.csv` | A link from a housing unit to a place, part or set | 719 links | The sources above |
| `locations/footprint_places.csv` | A place matched to a footprint in `building_heights.csv` | 73 places, 41 footprints (CMC, COR, SQ) | OpenStreetMap building names |
| `locations/footprint_sets.csv` | A place set and its candidate footprints in `building_heights.csv` | 7 sets | `building_heights.csv`, `place_sets.csv` |

## Fields

Condition ratings: **Plus** (expected to exceed 20 years of operation), **Good** (generally well maintained), **Fair** (needs repairs, typical wear and tear), **Poor** (significant disrepair), **Failing** (at risk of failure or unusable), **N/A** (the system doesn't exist at the institution).

`mpar_projects.csv` statuses: complete, active, proposed, future within 5 years, and future in 5–10 years.

In `building_heights.csv` (and `building_footprints.geojson` feature properties):

| Column | Meaning |
| :--- | :--- |
| `cdcr_code` | Institution code joining `data/institutions.csv`. |
| `footprint_id` | Unique per-building identifier (`{cdcr_code}-fp-{n}` from USA Structures, `-ovt-{n}` from Overture patch, `-lid-{n}` from LiDAR/NAIP patch). |
| `usa_structures_build_id`, `overture_id` | Upstream source feature IDs where matched; blank otherwise. |
| `lat`, `lon` | Polygon centroid in WGS84. |
| `footprint_sqft`, `solidity` | Polygon footprint area in sq ft and area / convex-hull solidity ratio (`0–1`). |
| `footprint_source` | Geometry provenance (`usa_structures`, `overture_patch`, `lidar_naip_patch`). |
| `building_category` | Broad functional group: `housing`, `program_admin_medical`, `support_warehouse_pia`, `guard_tower_utility`, or `canopy`. |
| `is_housing`, `housing_prototype` | Whether the structure houses incarcerated people (`yes`/`no`) and architectural prototype tag (e.g., `270_housing_unit`, `180_housing_unit`, `level1_dorm_standard`, `cross_pod_dorm_1story`, or `non_housing`). |
| `stories`, `stories_range` | Point story count and plausible min–max tier range (`1`, `1-2`, `2`, `2-3`, `3`, `1-3`, `3-6`, `5`, `6`); blank when indeterminate (`canopy`, or built after the LiDAR). Counts occupied levels: interior cell tiers count as stories where a source or the heat logs document them, because tiers of 9–10 ft can fit three under a 26–30 ft roof. LiDAR measures only the exterior roof. |
| `story_confidence`, `story_method` | Story confidence (`high`, `medium`, `indeterminate`) and derivation method. |
| `roof_p10_ft`–`roof_p98_ft`, `roof_spread_ft` | LiDAR roof height percentiles above ground (`ft`) and `p90 - p10` spread; blank where LiDAR height is unavailable. |
| `multi_tier_flag`, `sub_tier_heights_ft` | Whether distinct multi-tier roof modes appear (`yes`/`no`) and peak height modes with point shares. |
| `ground_slope_ft` | Elevation spread (`p90 - p10`, ft) across the surrounding ground calibration ring. |
| `height_source`, `lidar_project`, `lidar_year` | LiDAR classification tier used (`ept_laz_cls6`, `ept_laz_cls1_fallback`, `none`), USGS 3DEP EPT collection, and LiDAR collection year (`2014–2023`). |

`condition_assessment_2026.csv`: `institution` is the code as printed (`FSP`, `SQRC`); `cdcr_code` is the code in `data/institutions.csv` (`FOL`, `SQ`), blank for `CTC`.

Keys in `locations/`: `facility_key` is `{cdcr_code}-{facility}`, `unit_key` is `{cdcr_code}-{unit}`, `place_key` is `{cdcr_code}-{building}` (the building number), `{cdcr_code}-spi{n}` (an SPI structure with no usable number), `{cdcr_code}-{name}` (a building sources name but don't number) or `{cdcr_code}-ph-{n}` (a building a source counts without naming), `part_key` is `{place_key}:{part}`, and `set_key` is `{cdcr_code}-set-{name}`. `source`, `page` and `quote` give the source of a row and its words; `;` separates several values.

`locations/facilities.csv`:

| Column | Meaning |
| :--- | :--- |
| `facility` | The facility's letter or name (`A`, `MSF`, `East`). |
| `within` | `facility_key` of the facility or complex that contains this one. |
| `names` | Names sources use for the facility. |
| `status_as_written`, `status_source` | A source's statement that the facility was closed or deactivated, and its source. |
| `sources`, `quotes` | Sources and quoted text naming the facility; `\|\|` separates quotes. |

`locations/housing_units.csv`:

| Column | Meaning |
| :--- | :--- |
| `unit` | The unit's name. |
| `names` | Names sources write for the unit. |
| `facility_key` | The unit's facility; blank where no source places it. |
| `facility_basis` | How the facility is known: `unit name`, `written with the unit`, `numbering pattern`, `Level I housing = MSF`, or `see source and note`. |
| `facility_source`, `facility_page`, `facility_quote` | Source of the facility. |
| `program` | Program or mission as stated, with the source's date. |
| `from_building_key` | Key of a building-inventory record that is this unit rather than a building. |

`locations/places.csv`:

| Column | Meaning |
| :--- | :--- |
| `place`, `place_name` | Building number and name as sources write them. |
| `kind` | `building` or `other structure`. |
| `aliases` | Other IDs sources use for the place. |
| `placeholder` | `yes` for a building a source counts without naming. |
| `facility_as_written`, `facility_source` | The facility as a source writes it, and its source. |
| `facility_key` | The facility `facility_as_written` names; blank when it names none. |
| `record_covers` | `several buildings` when one record covers several buildings or units. |
| `use`, `program`, `beds`, `year_built` | Every value sources state; programs and beds carry the source's date. `use` comes from sources other than SPI. |
| `sqft`, `spi_structure_type` | Size and structure type in SPI. |
| `spi_structure_number`, `spi_agency_structure_no`, `spi_real_property_number` | SPI identifiers as entered. |
| `conflicts` | Columns where sources disagree. |
| `n_sources`, `sources` | Sources naming the place. |

`locations/place_parts.csv`:

| Column | Meaning |
| :--- | :--- |
| `part_type`, `part` | `wing`, `side`, `section` or `post`, and its letter or name. |
| `names` | Names sources write for the part. |
| `basis` | How the part is known: `source writes it`, `inside a large SPI record`, `unit name`, `follows the place link`, `page layout`, `number match`, or `see source and note`. |
| `from_building_key` | Key of a building-inventory record that is this part. |

`locations/place_sets.csv`: one row per place in a set of buildings SPI describes identically. `basis` is `SPI name writes the design` or `SPI name writes the yard`.

`locations/unit_links.csv`:

| Column | Meaning |
| :--- | :--- |
| `target_key`, `target_table` | The place, part or set the unit links to, and its table (`places`, `place_parts`, `place_sets`). |
| `level` | The floor of the building the unit occupies, where a source gives it. |
| `relation` | `same as building` (the unit is the building), `part of building` (a wing, side or floor of it), `part of group` (the target record covers several buildings, the unit's among them), `one of these buildings` (the unit is in one building of the set), or `one of several buildings` (one of several places). |
| `basis` | How the link is known, e.g. `source pairs them`, `group record`, `unit name`, `name match`, `number match`, `unit count matches the design`, `identical records of the unit's design`, `by elimination`. |

`locations/footprint_places.csv`:

| Column | Meaning |
| :--- | :--- |
| `footprint_id` | The footprint in `building_heights.csv`. |
| `relation` | `same as building` or `footprint holds several places`. |
| `basis` | `OSM name carries the SPI building letter or number`, `OSM name is the SPI building code`, or `OSM name and SPI name match`. |
| `source`, `source_name`, `place_name` | The OpenStreetMap way, its name, and the place's name. |

`locations/footprint_sets.csv`:

| Column | Meaning |
| :--- | :--- |
| `n_places`, `n_candidate_footprints` | Places in the set and footprints of the same prototype at the institution. |
| `shared_with_sets` | Another set with the same candidate footprints. |
| `housing_prototype`, `stories`, `stories_range` | As in `building_heights.csv`, shared by the candidates. |
| `roof_p50_ft_min`, `roof_p50_ft_max`, `footprint_sqft_min`, `footprint_sqft_max` | Range across the candidates. |
| `footprint_ids` | The candidate footprints. |
| `basis` | The count match between footprints and places. |

## Provenance

| Table | Source | Script and inputs | Covered through |
| :--- | :--- | :--- | :--- |
| `building_heights`, `building_footprints` | [USGS 3DEP EPT](https://registry.opendata.aws/usgs-lidar/), [FEMA USA Structures](https://disasters.geoplatform.gov/), [Overture Maps](https://overturemaps.org/), [USDA NAIP](https://naip-usdaonline.hub.arcgis.com/) | `scrapers/building_heights/`; RAPT prison boundaries, SPI cross-checks | 2023 LiDAR / 2024 NAIP |
| `mpar_projects` | [Master Plan Annual Reports](https://www.cdcr.ca.gov/fpcm/) | `extract_mpar_projects.py`; PDFs in `sources/cdcr_facilities_planning/` | 2025 report |
| `mpar_envelope_last_completed` | Same | Transcribed by hand | 2025 report |
| `infrastructure_plan_profiles_2026`, `condition_assessment_2026`, `condition_assessment_rank_2026` | [Infrastructure Master Plan](https://www.cdcr.ca.gov/fpcm/cdcr-infrastructure-master-plan/) | Transcribed by hand | May 2026 |
| `spi_cdcr_structures` | [SPI](https://services8.arcgis.com/a4GMqC2tQHvYiVtK/arcgis/rest/services/SPIPublicMapViewer/FeatureServer/1) | `fetch_spi_structures.py` | Oct 6, 2026 |
| `building_mentions` | The sources under Files; PDFs and saved pages in `sources/prea/`, `sources/cdcr_web/`, `sources/heat_cooling/` | Transcribed by hand, plus equipment rows from `extract_housing_cooling_types.py` | Oct 2026 |
| `locations/places` | SPI, `building_mentions`, [OpenStreetMap](https://www.openstreetmap.org/) | `build_places.py`; `sources/openstreetmap/osm_cdcr_buildings.csv` | Nov 2026 |
| `locations/facilities`, `housing_units`, `place_parts`, `place_sets`, `unit_links` | The sources under Files | Compiled by hand | Nov 2026 |
| `locations/footprint_places`, `footprint_sets` | OpenStreetMap, `building_heights`, `place_sets` | `building_heights/build_footprint_places.py` | Nov 2026 |

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
