# Mental health beds

Inpatient and crisis bed census, waitlists, forecast bed need, and mental health programs by facility.

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `pip_census.csv` | A report, program line, and measure: Psychiatric Inpatient Program census | 5 reports, Oct 2025 – Mar 2026 | CCHCS reports filed in *Coleman* |
| `pip_coleman_waitlist.csv` | A report and program line: capacity, census, waitlist | 4 reports, Oct 2025 – Jan 2026 | Same |
| `mhcb_census.csv` | A report and program, system-wide: Mental Health Crisis Bed capacity and census | 4 reports, Oct 2025 – Jan 2026 | Same |
| `bed_need_study_actuals.csv` | A program, measure, and fiscal year: actuals and forecasts | FY 2014 – 2030 | Fall 2025 Bed Need Study |
| `mhsds_programs_by_facility.csv` | A facility: programs offered | July 2021 | MHSDS map |
| `iflex_inpatient_beds_2023.csv` | An inpatient bed designated as an Inpatient Flex bed: facility, building, bed number, current and new use | May 2023 | *Coleman* ECF 7833-1, Attachment B |

## Caveats

- In `pip_census.csv`, the `Out of LRH`, `PC 1370`, and `WIC 7301` rows are subsets of the census, not additional patients.
- In `pip_coleman_waitlist.csv`, referral and waitlist columns are reported only on section total rows.
- In `bed_need_study_actuals.csv`, `Total ADC` is average census plus average pending list, and `is_forecast` marks FY 2026 onward.

## Provenance

| Table | Source | Script and inputs | Covered through |
| :--- | :--- | :--- | :--- |
| `pip_census`, `pip_coleman_waitlist`, `mhcb_census`, `bed_need_study_actuals` | [CCHCS reports](https://cchcs.ca.gov/reports/) | `extract_specialized_beds.py`; PDFs in `sources/specialized_beds/` with a `YYYY-MM-DD_` prefix | Mar 2026, Jan 2026, Jan 2026, Fall 2025 study |
| `mhsds_programs_by_facility` | [MHSDS map](https://www.cdcr.ca.gov/bph/wp-content/uploads/sites/161/2021/10/MHSDS-Map-2021.07.02.pdf) | Transcribed by hand | July 2021 |
| `iflex_inpatient_beds_2023` | [ECF 7833-1](https://storage.courtlistener.com/recap/gov.uscourts.caed.83056/gov.uscourts.caed.83056.7833.1.pdf) | Transcribed by hand | May 2023 |

## References

California Correctional Health Care Services. (2025–2026). *Reports & Court Orders* [PIP census, Coleman waitlist, MHCB census]. https://cchcs.ca.gov/reports/

California Correctional Health Care Services. (2025). *Fall 2025 Mental Health Bed Need Study*. https://cchcs.ca.gov/wp-content/uploads/sites/60/Fall-2025-Mental-Health-Bed-Need-Study.pdf

California Department of Corrections and Rehabilitation. (2021). *Mental Health Services Delivery System Map*. https://www.cdcr.ca.gov/bph/wp-content/uploads/sites/161/2021/10/MHSDS-Map-2021.07.02.pdf

Coleman v. Newsom, No. 2:90-cv-0520 KJM SCR (E.D. Cal.). (2023, May 11). *Inpatient Flex Beds* (ECF No. 7833-1). https://storage.courtlistener.com/recap/gov.uscourts.caed.83056/gov.uscourts.caed.83056.7833.1.pdf
