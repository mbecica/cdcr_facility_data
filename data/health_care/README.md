# Health care

Health care population, staffing, costs, and mortality from California Correctional Health Care Services (CCHCS).

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `cchcs_ipc.csv` | A month, institution, and Institution & Population Characteristics measure | Jan 2017 – Aug 2026 | CCHCS dashboard |
| `cchcs_measures.csv` | A month, institution, and staffing, cost, send-out, or other trend measure | Jan 2017 – Aug 2026 | CCHCS dashboard |
| `cchcs_mortality_2006-2024.csv` | A year, system-wide: deaths and mortality rates | 2006–2024 | CCHCS dashboard, transcribed by hand |

## Caveats

These tables hold a selection of the dashboard's measures, not all of them. A row exists where the dashboard publishes a value.

`ED/Hospital Stay*` ends in Dec 2025 because the dashboard no longer lists it. `ED/Hospital Send-Outs (All)*` is a separate measure that covers all months.

## Fields

In `cchcs_measures.csv`:

| Group | Measure | Meaning |
| :--- | :--- | :--- |
| Staffing | `Actual Vacancies (All)`, `Medical Vacancies (All)`, `Mental Health Vacancies (All)`, `Dental Vacancies (All)` | Vacancy rate: all health care, medical, mental health, and dental staff |
| Major Costs | `Total Labor Cost (All)` | Labor cost per patient per month, dollars |
| Major Costs | `ED & Hospital Stays` | Non-labor ED and hospital cost per patient per month, dollars |
| Other Trends | `ED/Hospital Stay*` | ED and hospital send-outs per 1,000 patients per month |
| Care Management | `ED/Hospital Send-Outs (All)*` | ED and hospital send-outs per 1,000 patients per measurement period |
| Other Trends | `Specialty Care Referrals*` | Approved requests for specialty services per 1,000 patients per month |
| Other Trends | `Prescriptions Per Patient` | Prescribed medications per patient per month |

Risk tiers in `cchcs_ipc.csv`, as CCHCS defines them:

- **High Risk Priority 1:** two or more of these flags: sensitive medical condition; high hospital, ED, specialty care, and pharmacy costs; two or more hospitalizations; three or more ED visits; high-risk specialty consultations; significant abnormal labs; age 65 or older; specific high-risk diagnoses or procedures. A patient counted for multiple hospitalizations is not also counted for multiple ED visits.
- **High Risk Priority 2:** one of those flags.
- **Medium Risk:** one or more chronic illnesses (based on medications, lab tests, or mental health enrollment), including mental health high utilization and permanent ADA, excluding well-controlled conditions (asthma, diabetes, hypertension, HCV, latent TB).
- **Low Risk:** no chronic conditions, or only well-controlled ones.

## Provenance

| Table | Source | Script | Covered through |
| :--- | :--- | :--- | :--- |
| `cchcs_ipc` | [CCHCS dashboard](https://cchcs.ca.gov/dashboard/) | `fetch_cchcs_tables.py` | Aug 2026 |
| `cchcs_measures` | Same | `fetch_cchcs_tables.py` | Aug 2026 |
| `cchcs_mortality_2006-2024` | Same | Transcribed by hand | 2024 |

## References

California Correctional Health Care Services. (2026). *Health Care Services Dashboard* [Interactive dashboard]. https://cchcs.ca.gov/dashboard/
