# CDCR Facility Data

Facility-level data on California's adult state prisons, collected from public reports and dashboards published by the California Department of Corrections and Rehabilitation (CDCR), California Correctional Health Care Services (CCHCS), and the State Controller's Office (SCO).

The main table, `data/cdcr_facilities.csv`, has one row for each of the 34 adult institutions with population, demographics, housing cooling, health care population, programs, staffing, restricted housing, and violent incidents for 2025.

## Datasets

| File | Contents | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `data/cdcr_facilities.csv` | One row per institution, 2025 annual figures | 34 institutions | Built from the files below |
| `data/cdcr_population_by_location.csv` | Monthly in-custody population by institution | Jan 2023 – Jun 2026 | CDCR Population Data Points dashboard |
| `data/tpop1_institutions.csv` | Monthly population, design capacity, % occupied, staffed capacity by institution | Jan 2015 – Mar 2026 | CDCR TPOP-1 reports |
| `data/tpop1_summary.csv` | Monthly system-wide population totals | Jan 2015 – Mar 2026 | CDCR TPOP-1 reports |
| `data/restricted_housing.csv` | Monthly restricted housing population and share by institution | Dec 2024 – Feb 2026 | CDCR STA429 reports |
| `data/cchcs_ipc.csv` | Monthly health risk tiers, mental health, disability, age, and specialized beds by institution | Jan 2017 – Dec 2025 | CCHCS dashboard |
| `data/cchcs_measures.csv` | Monthly health care staff vacancies, labor and hospital costs, ED/hospital send-outs | Jan 2017 – Dec 2025 | CCHCS dashboard |
| `data/sb601_operations.csv` | Monthly lockdowns and modified programs, deaths, overtime, use of force | FY 2021-22 – 2024-25 | CDCR SB 601 dashboard |
| `data/sb601_programs.csv` | Monthly program enrollment and operational capacity | FY 2024-25 | CDCR SB 601 dashboard |
| `data/sco_staffing.csv` | Active state employees by facility, one row per report | 8 reports, Apr 2021 – Feb 2026 | SCO reports |
| `data/sco_staffing_avg.csv` | 2025 average staff headcount by institution | 2025 | SCO reports |
| `data/cdcr_violent_incidents_by_facility.csv` | Monthly violent incidents by institution and category | Jan 2021 – Dec 2025 | CDCR incident reports |
| `data/pip_census.csv` | Psychiatric Inpatient Program census by facility, program, and custody level | 5 reports, Oct 2025 – Mar 2026 | CCHCS court reports |
| `data/pip_coleman_waitlist.csv` | PIP capacity, census, and waitlist | 4 reports, Oct 2025 – Jan 2026 | CCHCS court reports |
| `data/mhcb_census.csv` | System-wide Mental Health Crisis Bed capacity and census | 4 reports, Oct 2025 – Jan 2026 | CCHCS court reports |
| `data/bed_need_study_actuals.csv` | Mental health bed actuals and forecasts by program | FY 2014 – 2030 | CCHCS Bed Need Study, Fall 2025 |
| `data/mhsds_programs_by_facility.csv` | Mental health programs offered at each facility | 2021 | CDCR MHSDS map |
| `data/cdcr_avg_sentence_by_admission.csv` | Monthly average sentence by admission type | Jan 2023 – Mar 2026 | CDCR Population Data Points dashboard |
| `data/cdcr_recidivism_los.csv` | Three-year return rate by length of stay | Release cohorts FY 2008-09 – 2019-20 | CDCR Adult Recidivism dashboard |

Transcribed and downloaded source files in `sources/`:

| File | Contents | Source |
| :--- | :--- | :--- |
| `air_cooling_infrastructure_dec2025.csv` | Housing units by cooling type, per institution | CDCR Air Cooling Pilot Supplemental Report, Jan 2026, Table 2 |
| `air_cooling_housing_units_dec2025.csv` | Housing units by design type, per institution | Same report, Table 1 |
| `CDCR_indoor_78f_days_2025.csv` | Days with indoor temperatures above 78°F, May–Oct 2025 | Same report, Table 1 |
| `cdcr_in-custody-{age,gender,race,countryofbirth}_2025.csv` | Monthly population by demographic group and institution | CDCR Population Data Set, 2025 |
| `CDCR_2025_pop_averages.csv` | 2025 average population by institution | Transcribed from TPOP-1 reports |
| `infrastructure_plan_profiles_2026.csv` | Building square footage, acres, design capacity split into cell and dorm beds, security levels, water and wastewater treatment plants, and deactivated facilities, per institution (as of April 2026) | CDCR Infrastructure Master Plan, May 2026, Appendix 1 |
| `condition_assessment_2026.csv` | Condition rating (Plus, Good, Fair, Poor, Failing, N/A) of 45 utility and building systems at each institution, one row per institution and system | CDCR Infrastructure Master Plan, May 2026, Appendix 2, p. 2 |
| `condition_assessment_rank_2026.csv` | Overall condition rank, 1 (worst) to 31 (best), weighted by each system's operational impact | Same, Appendix 2, p. 1 |
| `cdcr_manual_data.csv` | Year opened, planned closure, California Model, Air Cooling Pilot, and Infrastructure Master Plan priority participation | LAO (2020) and online documentation |
| `mpar_projects.csv` | Every capital project in each year's report, with status (complete, active, proposed, future within 5 years, future in 5–10 years), current phase, funding or estimated cost, scope, and justification. One row per project per report year. | CDCR Master Plan Annual Reports, 2022–2025 |
| `cooling_observations.csv` | Cooling type (mechanical, evaporative, none) of specific housing units, health care units, and program spaces, as stated or observed, with condition notes | Coleman Special Master's 31st Round Heat Plan report (ECF 8558, Feb 2025), Plata joint case management statement (ECF 4013, May 2026) |
| `spi_cdcr_structures.csv` | Every CDCR structure in the state property inventory, with all its identifiers as entered (property number, DGS structure number, agency building number), name, category, square footage, and year built | DGS Statewide Property Inventory, downloaded by `scrapers/fetch_spi_structures.py` |
| `building_mentions.csv` | Every place a source names a specific building or housing unit, with the facility, use, and program it states | MPARs 2022–2025, Capital Outlay Quarterly Reports, and the documents in `sources/heat_cooling/` |
| `verification_flags.csv` | Values in these files that conflict with the source's own totals or with other sources, with the evidence on each side and what would resolve it. Values are left as transcribed until a source settles them. | Compiled from the sources above |
| `mpar_envelope_last_completed.csv` | Most recent roofing or building envelope project by institution | CDCR Master Plan Annual Reports, 2020–2025 |
| `cchcs_mortality_2006-2024.csv` | Annual deaths and mortality rates, system-wide | CCHCS Health Care Services Dashboard |

## Repository layout

```
data/          cleaned tables (outputs of the scripts below)
sources/       transcribed source files, plus downloaded PDFs (not tracked; see "Updating the data")
scrapers/      dashboard scrapers and PDF extractors
crosswalk/     institution codes, FEMA facility IDs, alias codes, and the building inventory
build_cdcr_facilities.py   builds data/cdcr_facilities.csv
```

## `cdcr_facilities.csv` fields

### Identification

| Variable | Description | Source |
| :--- | :--- | :--- |
| `facilityid` | FEMA facility ID. Joins to the facility list in [ca_prison_climate_justice](https://github.com/mbecica/ca_prison_climate_justice) for address, coordinates, security level, and boundaries. | `crosswalk/institutions.csv` |
| `cdcr_code` | CDCR institution code. | `crosswalk/institutions.csv` |
| `name` | CDCR institution name. | `crosswalk/institutions.csv` |

### Population and demographics

| Variable | Description | Source |
| :--- | :--- | :--- |
| `average_2025_population` | Mean of the twelve monthly in-custody counts for 2025. | CDCR Population Data Points dashboard |
| `capacity_percent_2025` | Mean of the twelve monthly "Percent Occupied" values for 2025 (population ÷ design capacity), as a 0–1 value. Values over 1 mean the institution is above design capacity. | CDCR TPOP-1 reports |
| `age_over_50_pct`, `age_over_55_pct` | Share of the population aged 50+ and 55+. | CDCR Population Data Set, 2025 |
| `age_50_59_pct`, `age_60_69_pct`, `age_70_79_pct`, `age_80plus_pct` | Share of the population in each age bracket. | CDCR Population Data Set, 2025 |
| `gender_female_pct`, `gender_male_pct` | Share of the population by gender. | CDCR Population Data Set, 2025 |
| `race_white_pct`, `race_peopleofcolor_pct` | Share of the population identifying as White, and as any other race. | CDCR Population Data Set, 2025 |

Demographic shares are the mean monthly count in each group divided by `average_2025_population`. CDCR suppresses counts under 10 (shown as `*`) and under 50 (`**`); these are counted as 5 and 25. Institutions without a 2025 population (CAC and CVSP, closed; FWF, not reported separately) have blank population and demographic fields.

### Housing and cooling

| Variable | Description | Source |
| :--- | :--- | :--- |
| `n_housing_units` | Active housing units (wings, dormitories, or cell tiers) as of December 2025. | CDCR Air Cooling Pilot Supplemental Report, Jan 2026, Table 2 |
| `pct_hu_mechanical` | Share of housing units with mechanical (refrigerant) cooling. | Same |
| `pct_hu_evaporative` | Share of housing units with evaporative (swamp) cooling. | Same |
| `pct_hu_air_handlers` | Share of housing units with air handlers only (ventilation, no cooling). | Same |

Housing units with more than one cooling type are counted under each, so the three shares can sum to slightly more than 1. CVSP and FWF are not in the report. The report's tables don't always add up, and some counts conflict with other CDCR documents; `sources/verification_flags.csv` lists each case by institution. CIM's mix is the least certain: the report shows no evaporative cooling, although its Facility A retrofit completed in February 2025 is evaporative (CEQA #2018128257).

| Variable | Description | Source |
| :--- | :--- | :--- |
| `cond_cooling_mechanical_2026`, `cond_cooling_evaporative_2026` | Condition of the institution's mechanical (A/C) and evaporative cooling systems. | CDCR Infrastructure Master Plan, May 2026, Appendix 2 |
| `cooling_types_outside_housing` | Cooling types (`mechanical`, `evaporative`) that have a condition rating at the institution but are in none of its housing units, so they serve only non-housing buildings. CIM's `evaporative` may be an exception: its Facility A evaporative retrofit (see above) is not in the Air Cooling report's housing counts. | Appendix 2 and Air Cooling Pilot Supplemental Report, Table 2 |
| `cond_hydronic_loops_2026`, `cond_boilers_2026`, `cond_automated_controls_2026`, `cond_emergency_electrical_2026`, `cond_roofs_2026` | Condition of hydronic (chilled/hot water) loops, central boilers, automated building controls (SCADA, BMS, BAS), emergency electrical distribution, and roofs. | Same |
| `condition_rank_2026` | Overall condition rank across all 45 systems, 1 (worst) to 31 (best). CDCR's Correctional Training Center, the officer academy, is ranked but not in this table. | Same, p. 1 |

Ratings were assigned by each institution's plant operations staff, not through a formal facility condition assessment: **Plus** (expected to exceed 20 years of operation), **Good** (generally well maintained), **Fair** (needs repairs, typical wear and tear), **Poor** (significant disrepair), **Failing** (at risk of failure or unusable), and **N/A** (the system does not exist at the institution). Each rating covers the whole institution, including non-housing buildings, so a rated cooling system may not serve any housing unit (for example, ASP has a mechanical A/C rating but no housing units with mechanical cooling).

### Facility characteristics

| Variable | Description | Source |
| :--- | :--- | :--- |
| `year_opened` | Year the institution opened as a state facility. FOL (1880) and CVSP (1988) are filled in where the LAO data has no value; CMC (1961) and CTF (1946) differ from LAO's 1954 and 1948. FWF (2013) is not in the LAO figure. | LAO (2020), Figure 1 |
| `year_opened_notes` | Notes on prior uses of the site or source discrepancies. | LAO (2020), Figure 1 |
| `planned_closure` | `Yes` if the institution is marked for closure. | Online documentation |
| `california_model_facility` | `Yes` if the institution is part of the California Model. | Online documentation |
| `cdcr_air_cooling_pilot` | `Yes` if the institution is in the Air Cooling Pilot. | Online documentation |
| `infrastructure_priority_2026` | `Yes` for the five institutions slated for major capital projects in the next five years (CMF, CCWF, SCC, COR, CIM). | CDCR Infrastructure Master Plan, May 2026, p. 20 |
| `building_sqft` | Square feet of buildings at the institution, all uses. | CDCR Infrastructure Master Plan, May 2026, Appendix 1 |
| `cell_beds`, `dorm_beds` | Design capacity split into cell beds and dormitory beds, as of April 2026. The two sum to design capacity. | Same |
| `building_sqft_per_design_bed` | `building_sqft` ÷ design capacity. Blank for SCC, CIW, and CMC: their design capacity includes conservation camp beds (31, 2, and 1 camps), and no source separates camp beds from institution beds (TPOP-1 reports CIW and SCC camps only as one combined line). | Same |

### Programs

| Variable | Description | Source |
| :--- | :--- | :--- |
| `cognitive_behavioral_interventions` | Semicolon-separated list of Cognitive Behavioral Intervention programs with operational capacity in any month of FY 2024-25. | CDCR SB 601 dashboard |
| `rehabilitative_programs` | Semicolon-separated list of rehabilitative programs (academic, career technical, and others) with operational capacity in any month of FY 2024-25. | CDCR SB 601 dashboard |

### Health care population

| Variable | Description | Source |
| :--- | :--- | :--- |
| `cchcs_high_risk_p1_pct_2025` | % of the population classified High Risk Priority 1. | CCHCS dashboard |
| `cchcs_high_risk_p2_pct_2025` | % classified High Risk Priority 2. | CCHCS dashboard |
| `cchcs_medium_risk_pct_2025` | % classified Medium Risk. | CCHCS dashboard |
| `cchcs_low_risk_pct_2025` | % classified Low Risk. | CCHCS dashboard |
| `cchcs_mental_health_eop_pct_2025` | % in the Mental Health Enhanced Outpatient Program. | CCHCS dashboard |
| `cchcs_dpp_pct_2025` | % in the Disability Placement Program. | CCHCS dashboard |
| `cchcs_age_over_50_pct_2025` | % aged 50 or older. | CCHCS dashboard |
| `cchcs_specialized_beds_2025` | Specialized health care beds (count). | CCHCS dashboard |

All values are 2025 monthly averages, and percentages use the total institution population as the denominator. The four risk tiers sum to 100%. FWF has no separate CCHCS entry.

Risk tiers, as defined by CCHCS:

- **High Risk Priority 1:** two or more of these flags: sensitive medical condition; high hospital, ED, specialty care, and pharmacy costs; two or more hospitalizations; three or more ED visits; high-risk specialty consultations; significant abnormal labs; age 65 or older; specific high-risk diagnoses or procedures. A patient counted for multiple hospitalizations is not also counted for multiple ED visits.
- **High Risk Priority 2:** one of those flags.
- **Medium Risk:** one or more chronic illnesses (based on medications, lab tests, or mental health enrollment), including mental health high utilization and permanent ADA, excluding well-controlled conditions (asthma, diabetes, hypertension, HCV, latent TB).
- **Low Risk:** no chronic conditions, or only well-controlled ones.

### Staffing

| Variable | Description | Source |
| :--- | :--- | :--- |
| `sco_state_staff_2025` | Mean active state employees across the February, May, and June 2025 reports. For CHCF, includes both CDCR and CCHCS staff, which SCO reports separately. | SCO Active State Employees by Department |
| `sco_incarcerated_staff_2025` | Mean Prison Industry Authority (PIA) workers across the same reports. PIA workers are incarcerated people. Blank if the institution has no PIA operation. | Same |

### Restricted housing and incidents

| Variable | Description | Source |
| :--- | :--- | :--- |
| `rhu_pct_2025` | Mean of the twelve monthly shares of the population in restricted housing, 2025. CRC and ASP report no restricted housing units. | CDCR STA429 reports |
| `avg_annual_violent_incidents` | Total violent incidents, 2021–2025, divided by the number of years with reported data. CAC and CVSP are averaged over the years before they closed. | CDCR incident reports |

## Other datasets

### Population (`tpop1_institutions.csv`, `tpop1_summary.csv`, `cdcr_population_by_location.csv`)

TPOP-1 is CDCR's monthly Total Population Report. `tpop1_institutions.csv` has each institution's population, design capacity, percent occupied, and staffed capacity; `tpop1_summary.csv` has the system-wide totals from the report's first page. For 2015–2018, when only weekly reports are available, the last report of each month is used. `cdcr_population_by_location.csv` is the monthly in-custody count from the Population Data Points dashboard; counts under 10 are suppressed by CDCR and left blank. See `scrapers/README_tpop1.md` for the report formats.

### Restricted housing (`restricted_housing.csv`)

Institution-level restricted housing population, total population, and share in restricted housing, from Table 2 of CDCR's STA429 monthly reports. Each report is published early in the month and reflects the last day of the prior month.

### Health care (`cchcs_ipc.csv`, `cchcs_measures.csv`)

Both files are long format: one row per month, institution, and measure. `cchcs_ipc.csv` holds the Institution & Population Characteristics measures described above plus total institution population. `cchcs_measures.csv` holds:

| Group | Measure | Description |
| :--- | :--- | :--- |
| Staffing | `Actual Vacancies (All)` | Vacancy rate, all health care staff |
| Staffing | `Medical Vacancies (All)` | Vacancy rate, medical staff |
| Staffing | `Mental Health Vacancies (All)` | Vacancy rate, mental health staff |
| Staffing | `Dental Vacancies (All)` | Vacancy rate, dental staff |
| Major Costs | `Total Labor Cost (All)` | Labor cost per patient per month (dollars) |
| Major Costs | `ED & Hospital Stays` | Non-labor ED and hospital cost per patient per month (dollars) |
| Other Trends | `ED/Hospital Stay*` | ED and hospital send-outs per 1,000 patients per month |

### Operations and programs (`sb601_operations.csv`, `sb601_programs.csv`)

From the dashboard CDCR publishes under SB 601. `sb601_operations.csv` has monthly lockdowns and modified programs, deaths, overtime hours, and use of force by institution and fiscal year. `sb601_programs.csv` has monthly enrollment and operational capacity by program for FY 2024-25.

### Staffing (`sco_staffing.csv`, `sco_staffing_avg.csv`)

Active employee counts (full-time, part-time, intermittent, indeterminate, total) for CDCR facilities from SCO's Active State Employees by Department reports, retrieved through Wayback Machine snapshots. Regional offices, training academies, parole, and administrative units are excluded. PIA sub-entries are kept as separate rows ending in `- PIA`. `CDCR/CCHCS CA HEALTH CARE` is CCHCS staff at CHCF, separate from the CDCR operational staff row for the same facility. `sco_staffing_avg.csv` averages the 2025 reports and maps each row to a CDCR code.

### Violent incidents (`cdcr_violent_incidents_by_facility.csv`)

Monthly counts by institution from CDCR's CompStat and public incident reports. `violent_incidents` sums assault and battery on staff or non-incarcerated people, assault and battery on incarcerated people, cell extractions, fighting, and riots (incident count, not people involved). `inmate_on_inmate` and `staff_involved` split that total. Controlled substance and use-of-force rows are excluded. Where reports overlap, the most recent report is used.

| Year | System-wide violent incidents |
| :--- | ---: |
| 2021 | 7,169 |
| 2022 | 8,015 |
| 2023 | 10,077 |
| 2024 | 12,376 |
| 2025 | 12,512 |

### Mental health beds (`pip_census.csv`, `pip_coleman_waitlist.csv`, `mhcb_census.csv`, `bed_need_study_actuals.csv`, `mhsds_programs_by_facility.csv`)

From the monthly reports CCHCS files in the *Coleman* case, the Fall 2025 Mental Health Bed Need Study, and CDCR's Mental Health Services Delivery System map. In `pip_census.csv`, the `Out of LRH`, `PC 1370`, and `WIC 7301` rows are subsets of the census, not additional patients. In `pip_coleman_waitlist.csv`, referral and waitlist columns are reported only on section total rows. In `bed_need_study_actuals.csv`, `Total ADC` is average census plus average pending list, and `is_forecast` marks FY 2026 onward.

### Sentences and returns (`cdcr_avg_sentence_by_admission.csv`, `cdcr_recidivism_los.csv`)

Average sentence length at admission, in months, by admission type and month; some months are suppressed. Three-year return-to-prison rates by length of stay for each release cohort. Rates for cohorts released before the 2011 Public Safety Realignment are not comparable to later cohorts, and the FY 2017-18 through 2019-20 cohorts were affected by COVID-19 disruptions to courts and intake.

## Institution codes

`crosswalk/institutions.csv` lists the 34 institutions with their CDCR code, name, FEMA facility ID, and any alias codes used in source documents. Sources use FSP for Folsom State Prison (FOL), SQRC for San Quentin Rehabilitation Center (SQ), and FEMA uses CCFW for Central California Women's Facility (CCWF). The build maps these to the CDCR code.

## Buildings

`crosswalk/buildings.csv` is an inventory of buildings and housing units, built by `python3 scrapers/build_buildings.py` from two sources: the Department of General Services' Statewide Property Inventory (SPI), which lists every state-owned structure with its square footage and year built, and `sources/building_mentions.csv`, which records each place another source names a building. SPI has no beds or capacity, codes every housing building (cells or dorms) as "DORMITORY", and at some institutions has no building numbers or lists several buildings as one record. Coverage of the other fields varies widely between institutions.

| Variable | Description |
| :--- | :--- |
| `building_key` | `{cdcr_code}-{building}` for a numbered building, `{cdcr_code}-spi{n}` for an SPI structure with no usable building number (`n` is DGS's structure number), or `{cdcr_code}-{name}` for a building other sources name but don't number (for example `CIW-walker-unit`). Where a source counts buildings without naming them, each gets a placeholder key, `{cdcr_code}-ph-{facility}-{type}{n}` (for example `CIM-ph-A-HU1`). |
| `placeholder` | `yes` if the key was created by this project rather than taken from a source. Replace a placeholder with the real building number once a source gives it. |
| `building` | Building or housing unit number (`3410`, `405A`, `3A03`, `4A1R`). SPI numbers have prefixes such as `BLDG.` or `SQ-B-` removed, and DGS's five-digit serial numbers aren't used as building numbers; the original values are kept in `spi_agency_structure_no`. A structure SPI describes as two housing units is written as a pair (`A1/A2`). Where SPI gives several structures the same number, the number goes to the one housing structure among them (CEN `325` is Housing Unit A-5; its exercise yards share the number), and the others are keyed by DGS structure number. |
| `aliases` | Other IDs sources use for the building, including a housing unit SPI names on the same row (LAC `3410` is "Housing Unit D-5", so mentions of `D5` join it). |
| `building_name` | Names the sources give the building (`Laundry`, `Central Health Services`). |
| `facility`, `use`, `program` | Every value the sources state, separated by semicolons. Blank where no source states it. Facility is never inferred from the building number. |
| `year_built` | Year the building was built, from SPI or from a source that states it for that building, or for every building in a group it counts (placeholders). Ranges of years are not used. |
| `sqft` | Square footage, from SPI. |
| `spi_structure_type` | SPI's category (`DORMITORY`, `CLASSROOM`, `LOOKOUT (GUARD STATION)`). `use` comes from the other sources only. |
| `spi_structure_number`, `spi_agency_structure_no`, `spi_real_property_number` | SPI identifiers as entered: DGS's structure number, the agency's building number (`SQ-B-23`, `14929-E`, `507     BID PACAKAGE 5`), and DGS's number for the property. |
| `conflicts` | Columns where sources disagree. |
| `n_sources`, `sources` | Sources that name the building. `SPI` is the property inventory; MPAR sources are written `MPAR{year}:{project_id}`; others are the PDF filename in `sources/heat_cooling/` or `sources/cdcr_facilities_planning/`. |

A mention joins an SPI structure when the building numbers match (ignoring hyphens, spaces and leading zeros), when it matches a housing unit SPI names on the same row, or when its name matches an SPI structure name that is unique at the institution. Otherwise mentions merge only when they use the same number or name, so one building can still appear under two keys. Wings and sides of a building (`4A1R`) are kept separate from the building.

`cooling_observations.csv` records cooling for areas smaller than an institution. Join it to the inventory on `cdcr_code` and `building` or `aliases` where a building is given. Most rows name a program or facility instead (the MHCB, the CTC, Facility D). `cooling_as_stated` keeps the source's words, and `cooling_type` maps "air-conditioned" and "refrigeration" to `mechanical` and "swamp cooler" to `evaporative`. `basis` says whether the Special Master's monitors observed the cooling, staff or patients reported it, or the report states it without attribution. `space` is `health_care` for MHCB, PIP, and CTC units, which may also be counted as housing units in the Air Cooling report.

## Updating the data

Source PDFs are not stored in the repository. Download new reports into the matching `sources/` folder, then run the extractor. Dashboard scrapers drive the live Power BI dashboards in a visible browser (`npm install`, then `npx playwright install chromium`) and can break when a dashboard's layout changes. After updating any source, rebuild the main table with `python3 build_cdcr_facilities.py`.

| Data | Where to get it | Put it in | Run |
| :--- | :--- | :--- | :--- |
| Population | Population Data Points dashboard | — | `node scrapers/fetch_cdcr_population.js` |
| TPOP-1 | [Population reports](https://www.cdcr.ca.gov/research/population-reports-2/) | `sources/cdcr_population_pdfs/` (`Tpop1d{YYMM}.pdf`) | `python3 scrapers/extract_tpop1.py` |
| Restricted housing | CDCR Office of Research STA429 monthly reports | `sources/restricted_housing/` (`STA429-MMDDYY-M.pdf`) | `python3 scrapers/extract_restricted_housing.py` |
| Health care | [CCHCS dashboard](https://cchcs.ca.gov/dashboard/) | — | `node scrapers/fetch_cchcs_ipc.js`, `node scrapers/fetch_cchcs_measures.js` |
| SB 601 | SB 601 dashboard | — | `node scrapers/fetch_sb601_operations.js`, `node scrapers/fetch_sb601_programs.js` |
| Staffing | SCO Active State Employees by Department | `sources/cdcr_staffing/` | `python3 scrapers/extract_sco_staffing.py`, then `build_sco_staffing_avg.py` |
| Violent incidents | CDCR incident reports | `sources/cdcr_incidents/` | Add the filename to the list in `scrapers/extract_violent_incidents.py`, then run it |
| Mental health beds | [CCHCS reports](https://cchcs.ca.gov/reports/): monthly PIP census, Coleman PIP waitlist, and MHCB census reports, and the Mental Health Bed Need Study | `sources/specialized_beds/`, keeping the `YYYY-MM-DD_` report-date prefix | `python3 scrapers/extract_specialized_beds.py` |
| Sentences, returns | Population Data Points and Adult Recidivism dashboards | — | `node scrapers/fetch_cdcr_avg_sentence.js`, `node scrapers/fetch_cdcr_recidivism_los.js` |
| MPAR projects | [Master Plan Annual Reports](https://www.cdcr.ca.gov/fpcm/) | `sources/cdcr_facilities_planning/` (add the filename to `MPARS` in the script) | `python3 scrapers/extract_mpar_projects.py` |
| State property inventory | DGS Statewide Property Inventory (public map service) | — | `python3 scrapers/fetch_spi_structures.py`, then `build_buildings.py` |
| Buildings | Any source naming a building | Add rows to `sources/building_mentions.csv` | `python3 scrapers/build_buildings.py` |
| Cooling, indoor heat, cooling observations, facility metadata | CDCR reports and court filings | `sources/`, `sources/heat_cooling/` | Transcribed by hand |

To add a year to the main table, change `YEAR` at the top of `build_cdcr_facilities.py`; the year is part of the column names (`average_2026_population`, `cchcs_dpp_pct_2026`). The dashboard scrapers have `LATEST_YEAR` or `FISCAL_YEAR` settings at the top of each script.

## License

Code is MIT and data is CC BY 4.0; see [LICENSE.md](LICENSE.md). The data are public records published by CDCR, CCHCS, and SCO. The license covers this project's compilation, cleaning, and transcriptions, not the underlying figures. Please credit the original agency source as well.

## References

California Correctional Health Care Services. (2025). *Health Care Services Dashboard* [Interactive dashboard]. https://cchcs.ca.gov/dashboard/

California Correctional Health Care Services. (2025–2026). *Reports & Court Orders* [PIP census, Coleman waitlist, MHCB census]. https://cchcs.ca.gov/reports/

California Correctional Health Care Services. (2025). *Fall 2025 Mental Health Bed Need Study*. https://cchcs.ca.gov/wp-content/uploads/sites/60/Fall-2025-Mental-Health-Bed-Need-Study.pdf

California Department of Corrections and Rehabilitation. (2015–2026). *Monthly Total Population Report (TPOP-1)*. Office of Research. https://www.cdcr.ca.gov/research/population-reports-2/

California Department of Corrections and Rehabilitation. (2025). *Population Data Set* and *Population Data Points* [Dataset and dashboard]. Office of Research.

California Department of Corrections and Rehabilitation. (2024–2026). *Restricted Housing Monthly Report (STA429)*. Office of Research.

California Department of Corrections and Rehabilitation. (2025). *SB 601 Programs Dashboard* [Interactive dashboard]. https://app.powerbigov.us/view?r=eyJrIjoiYzlkM2RiNWEtZDRjMi00ODllLTg2YzEtZjYyM2MwMjA5NmQ0IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9&pageName=5a926528bbf7e48d60c2

California Department of Corrections and Rehabilitation. (2021–2025). *CompStat Incident Report* and *Incident Report – Public*.

California Department of Corrections and Rehabilitation. (2026, January). *Air Cooling Pilot Program Supplemental Report*. https://www.cdcr.ca.gov/fpcm/wp-content/uploads/sites/184/2026/02/Air_Cooling_Document_for_Legislature.pdf

California Department of Corrections and Rehabilitation, Facilities Planning, Construction and Management. (2020–2025). *Master Plan Annual Report*.

California Department of Corrections and Rehabilitation, Facility Planning, Construction and Management. (2026, May). *Infrastructure Master Plan* and Appendices 1–3. https://www.cdcr.ca.gov/fpcm/cdcr-infrastructure-master-plan/

California Department of Corrections and Rehabilitation. (2021). *Mental Health Services Delivery System Map*. https://www.cdcr.ca.gov/bph/wp-content/uploads/sites/161/2021/10/MHSDS-Map-2021.07.02.pdf

California State Controller's Office. (2021–2026). *Active State Employees by Department*. Retrieved through the Internet Archive Wayback Machine.

Coleman v. Newsom, No. 2:90-cv-0520 KJM SCR (E.D. Cal.). (2025, February 28). *Special Master's Thirty-First Round Focused Heat Plan Monitoring Report* (ECF No. 8558). https://storage.courtlistener.com/recap/gov.uscourts.caed.83056/gov.uscourts.caed.83056.8558.0.pdf

Plata v. Newsom, No. 4:01-cv-01351-JST (N.D. Cal.). (2026, May 26). *Joint Case Management Conference Statement* (ECF No. 4013). https://storage.courtlistener.com/recap/gov.uscourts.cand.76/gov.uscourts.cand.76.4013.0.pdf

Department of General Services, Real Estate Services Division. (2026). *Statewide Property Inventory* [Structure layer, SPI Public Map Viewer]. https://services8.arcgis.com/a4GMqC2tQHvYiVtK/arcgis/rest/services/SPIPublicMapViewer/FeatureServer/1

Legislative Analyst's Office. (2020). *Effectively Managing State Prison Infrastructure* (Report 4186). https://lao.ca.gov/reports/2020/4186/prison-infrastructure-022820.pdf
