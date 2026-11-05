# Population

Population counts, capacity, demographics, sentences, and returns to prison.

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `tpop1_institutions.csv` | An institution section in a monthly report: population, design capacity, percent occupied, staffed capacity | Jan 2015 – Mar 2026 | TPOP-1 reports |
| `tpop1_summary.csv` | A line in a report's system-wide table | Jan 2015 – Mar 2026 | TPOP-1 reports |
| `cdcr_population_by_location.csv` | A location and month: in-custody count | Jan 2023 – Oct 2026 | Population Data Points dashboard |
| `cdcr_in-custody-age.csv`, `-gender`, `-race`, `-ethnicity`, `-countryofbirth`, `-controllingcounty` | A month, location, and demographic group: in-custody count | Jan 2023 – Oct 2026 | Population Data Points dashboard |
| `cdcr_avg_sentence_by_admission.csv` | A month and admission type: average sentence in months | Jan 2023 – Oct 2026 | Population Data Points dashboard |
| `cdcr_recidivism_los.csv` | A release cohort and length of stay: three-year return rate | FY 2008-09 – 2020-21 | Adult Recidivism dashboard |

## Caveats

- For 2015–2018, when only weekly TPOP-1 reports are available, the last report of each month is used.
- TPOP-1 changed format. Reports from 2018 on list full institution names; 2015–2017 use short names and aren't normalized. `change_last_period` is the change since last month in monthly reports, since last week in 2018 weekly reports, and the year-over-year change in 2015–2017 reports, where `change_last_year` is blank. `row_label` puts each line under one label across years, and `row_label_as_stated` keeps the printed label.
- An institution with both male and female sections has two rows in a month; `gender` tells them apart. `gender` is blank from Nov 2021, when reports stopped having gendered sections.
- In the `cdcr_in-custody-` tables, `population` keeps `*` (under 10) and `**` (under 50) as published, and a blank means zero observations, as the dashboard states. Sums can't always be rebuilt because of suppression. Locations vary by month as facilities open and close, and `cdcr_code` is blank for locations that aren't CDCR institutions.
- In `cdcr_population_by_location.csv`, counts under 10 are blank.
- The dashboard notes that return rates for cohorts released before the 2011 Public Safety Realignment aren't comparable to later cohorts, and that the FY 2017-18 through 2019-20 cohorts were affected by COVID-19 disruptions to courts and intake.

## Provenance

| Table | Source | Script and inputs | Covered through |
| :--- | :--- | :--- | :--- |
| `tpop1_*` | [Population reports](https://www.cdcr.ca.gov/research/population-reports-2/) | `extract_tpop1.py`; monthly PDFs in `sources/cdcr_population_pdfs/`, 2015–2018 weekly in `tpop_weekly/` | Mar 2026 |
| `cdcr_population_by_location` | [Population Data Points](https://app.powerbigov.us/view?r=eyJrIjoiN2RjZmFjNzItMzI0Ni00M2IwLWJmZjgtNDgyMjUyMjVhOWMwIiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9&pageName=6eb2cf1a956ed8b180cb) | `fetch_cdcr_population.js` | Oct 2026 |
| `cdcr_in-custody-*` | Same | `fetch_cdcr_demographics.js` | Oct 2026 |
| `cdcr_avg_sentence_by_admission` | Same | `fetch_cdcr_avg_sentence.js` | Oct 2026 |
| `cdcr_recidivism_los` | [Adult Recidivism dashboard](https://app.powerbigov.us/view?r=eyJrIjoiNmRjOTkwMWEtYmVkMy00MTA1LWIxZDYtYzg4OTIzYjkxNTRlIiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9) | `fetch_cdcr_recidivism_los.py` | FY 2020-21 cohort |

## References

California Department of Corrections and Rehabilitation. (2015–2026). *Monthly Total Population Report (TPOP-1)*. Office of Research. https://www.cdcr.ca.gov/research/population-reports-2/

California Department of Corrections and Rehabilitation. (2026). *Population Data Points* [Dashboard]. Office of Research.
