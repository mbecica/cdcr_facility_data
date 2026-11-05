# CDCR Facility Data

The California Department of Corrections and Rehabilitation (CDCR) releases most of its data as PDFs, as Power BI dashboards without exports, or scattered across Public Records Act responses. This repository makes that data available as CSVs, along with related data from California Correctional Health Care Services (CCHCS), the State Controller's Office, the Department of General Services, and federal court filings.

## Data

| Folder | Contents | Years covered |
| :--- | :--- | :--- |
| [`data/facilities/`](data/facilities/) | One row per adult institution, summarizing the other tables for the latest complete year | 2025 |
| [`data/population/`](data/population/) | Population, capacity, demographics, sentences, and returns to prison | 2015–2026; return cohorts FY 2008-09 to 2019-20 |
| [`data/health_care/`](data/health_care/) | Health risk, staffing vacancies, costs, and hospital send-outs by institution; system-wide mortality | 2017–2025; mortality 2006–2024 |
| [`data/mental_health_beds/`](data/mental_health_beds/) | Inpatient and crisis bed census, waitlists, bed need, and programs by facility | 2014–2026; forecasts to 2030 |
| [`data/operations/`](data/operations/) | SB 601 reporting, grievances, violent incidents, and restricted housing | 2020–2026 |
| [`data/staffing/`](data/staffing/) | Active state employees by facility | 2021–2026 |
| [`data/buildings/`](data/buildings/) | Capital projects, condition ratings, property inventory, and building mentions | 2020–2026 |
| [`data/heat/`](data/heat/) | Cooling infrastructure, court monitoring of the Heat Plan, and 2024 heat records | 2015–2026 |

Coverage varies by table within each folder; each folder's README lists it. [`data/README.md`](data/README.md) describes the conventions the tables share.

`sources/` holds raw inputs, `scrapers/` holds the code that produces the tables, and `crosswalk/` links institutions and buildings across sources.

## Identifiers

`cdcr_code` identifies an institution in every table and is blank for locations that aren't CDCR institutions. Names as the source published them stay in `_as_stated` columns. [`crosswalk/institutions.csv`](crosswalk/institutions.csv) lists each code with its FEMA facility ID and the other codes sources use for it.

## License and citation

Code is MIT and data is CC BY 4.0; see [LICENSE.md](LICENSE.md). The license covers this project's compilation, cleaning, and transcriptions, not the underlying figures, which are public records. Please credit the original agency as well.

Becica, M. (2026). *CDCR Facility Data* [Data set]. GitHub. https://github.com/mbecica/cdcr_facility_data
