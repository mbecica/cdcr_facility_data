# Operations

SB 601 reporting, grievances, violent incidents, and restricted housing.

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `sb601_operations.csv` | An institution, month, and metric: lockdowns and modified programs, deaths, overtime, use of force, budget and expenditures | Jan 2019 – Jun 2026 | SB 601 dashboard |
| `sb601_programs.csv` | An institution, month, and metric: program enrollment and capacity, contraband, housing, positions, and sick leave | Jan 2020 – Jun 2026 | SB 601 dashboard |
| `sb601_grievances.csv` | An institution, report date, and metric: grievance and appeal claims | Jan 2020 – Jun 2026 | SB 601 dashboard and open data |
| `cdcr_violent_incidents_by_facility.csv` | An institution and month: violent incidents by category | Jan 2021 – Dec 2025 | CompStat and public incident reports |
| `restricted_housing.csv` | An institution and month: restricted housing population and share | Dec 2024 – Feb 2026 | STA429 monthly reports |

## Caveats

- **SB 601 tables:** these match the dashboard's Institution Table but are read through its query endpoint, so they include months before the fiscal years its slicers offer (FY 2022-23 on). Start dates vary by category. A row exists where the dashboard publishes a value. Contraband starts in Jul 2024 here; earlier contraband is in the open data download.
- **SB 601 contraband:** the report now holds some seizure counts without a date, which can't be placed in a month and aren't in these tables. Monthly FY 2024-25 values that the report no longer gives are kept from an earlier refresh.
- **Grievances:** counts are claims, and one grievance can contain several claims. The file has no grievance subject. `source` says where each row came from: `dashboard` for every month the dashboard covers, Jul 2021 on plus a few Jan 2021 values, and `open_data` for Jan 2020 – Jun 2021. The two sources group statuses differently, and CDCR notes that counts are subject to restatement. `institution` and `report_date` are as published; `month` groups report dates that aren't the month's last day with the rest of that month. The counting rules in `sources/sb601_open_data/` define each metric.
- **Violent incidents:** `violent_incidents` sums assault and battery on staff or non-incarcerated people, assault and battery on incarcerated people, cell extractions, fighting, and riots, as incident counts rather than people involved. `inmate_on_inmate` and `staff_involved` split that total. Controlled substance and use-of-force rows aren't included. Where reports overlap, the most recent is used.
- **Restricted housing:** each report reflects the last day of the prior month, and `month` is that month.

## Provenance

| Table | Source | Script and inputs | Covered through |
| :--- | :--- | :--- | :--- |
| `sb601_operations` | [SB 601 dashboard](https://app.powerbigov.us/view?r=eyJrIjoiYzlkM2RiNWEtZDRjMi00ODllLTg2YzEtZjYyM2MwMjA5NmQ0IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9&pageName=5a926528bbf7e48d60c2) | `fetch_sb601_tables.py` | Jun 2026 |
| `sb601_programs` | Same | `fetch_sb601_tables.py` | Jun 2026 |
| `sb601_grievances` | Same, and [SB 601 open data](https://data.ca.gov/dataset/sb601-reporting) | `fetch_sb601_grievances.py`; download in `sources/sb601_open_data/` | Jun 2026 |
| `cdcr_violent_incidents_by_facility` | CompStat and public incident reports | `extract_violent_incidents.py`; PDFs in `sources/cdcr_incidents/` | Dec 2025 |
| `restricted_housing` | STA429 monthly reports | `extract_restricted_housing.py`; PDFs in `sources/restricted_housing/` | Feb 2026 |

## References

California Department of Corrections and Rehabilitation. (2026). *SB 601 Programs Dashboard* [Interactive dashboard]. https://app.powerbigov.us/view?r=eyJrIjoiYzlkM2RiNWEtZDRjMi00ODllLTg2YzEtZjYyM2MwMjA5NmQ0IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9&pageName=5a926528bbf7e48d60c2

California Department of Corrections and Rehabilitation. (2024). *SB601 Reporting* [Dataset, data through June 2024]. California Open Data Portal. https://data.ca.gov/dataset/sb601-reporting

California Department of Corrections and Rehabilitation. (2021–2025). *CompStat Incident Report* and *Incident Report – Public*.

California Department of Corrections and Rehabilitation. (2024–2026). *Restricted Housing Monthly Report (STA429)*. Office of Research.
