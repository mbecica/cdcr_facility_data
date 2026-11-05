# Buildings

Capital projects, condition ratings, institution profiles, the state property inventory, and every place a source names a building. `crosswalk/buildings.csv` combines the inventory and the mentions.

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
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

## Fields

Condition ratings: **Plus** (expected to exceed 20 years of operation), **Good** (generally well maintained), **Fair** (needs repairs, typical wear and tear), **Poor** (significant disrepair), **Failing** (at risk of failure or unusable), **N/A** (the system doesn't exist at the institution).

`mpar_projects.csv` statuses: complete, active, proposed, future within 5 years, and future in 5–10 years.

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
