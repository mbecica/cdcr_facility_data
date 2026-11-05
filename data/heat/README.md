# Heat

Cooling infrastructure, court monitoring of CDCR's Heat Plan, and CDCR's 2024 heat records. The 2024 records are described in [`logs_2024/`](logs_2024/).

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `cooling/air_cooling_infrastructure_dec2025.csv` | An institution: housing units by cooling type | Dec 2025 | Air Cooling Pilot Supplemental Report, Jan 2026, Table 2 |
| `cooling/air_cooling_housing_units_dec2025.csv` | An institution: housing units by design type | Dec 2025 | Same, Table 1 |
| `cooling/CDCR_indoor_78f_days_2025.csv` | An institution: days with indoor temperatures above 78°F | May–Oct 2025 | Same, Table 1 |
| `cooling/housing_cooling_equipment_2024.csv` | A piece of cooling or ventilation equipment serving a housing building | Aug 2024 | CDCR table filed as *Plata* ECF 3952-1, Exhibit E |
| `cooling/cooling_observations.csv` | A specific housing unit, health care unit, or program space: cooling type as stated or observed | Stated in 2025–2026 filings | *Coleman* ECF 8558, *Plata* ECF 4013 |
| `monitoring/coleman_heat_plan_findings.csv` | A report, institution, and heat plan area: compliance finding | Heat seasons 2015–2025, audits to May 2026 | *Coleman* monitoring reports and audits |
| `monitoring/coleman_heat_plan_counts.csv` | A report, institution, period, and measure: heat alerts, illnesses, training | Oct 2015 – May 2026 | Same, plus statewide figures from CDCR and *Plata* ECF 4013 |

## Caveats

- **Air Cooling report:** the tables are transcribed as printed. `../verification_flags.csv` lists values that conflict with the report's totals or other sources.
- **Equipment:** one row per piece of equipment, so a building can have several rows and more than one type. `type_of_cooling` is as printed; `cooling_type` maps it to `mechanical`, `evaporative`, or `none`, and `note` explains rows where CDCR has since corrected the type. The table doesn't list every housing unit. Many building IDs are CDCR's own and don't match the state property inventory, so they have their own keys in `crosswalk/buildings.csv`. The court copy is a scan: `ocr_check` says whether two OCR passes agreed or the value was checked against the page image.
- **Cooling observations:** most rows name a program or facility rather than a building. `cooling_as_stated` keeps the source's words and `cooling_type` maps them. `basis` says whether monitors observed the cooling, staff or patients reported it, or the report states it without attribution. `space` is `health_care` for units that may also be counted as housing units in the Air Cooling report.
- **Coleman tables:** both keep a verbatim `quote` for every value, checked against the PDF, and `page` is the PDF page. Findings from the focused heat report cover seven areas for every institution; round reports record only the findings their text states. Most count periods cover only the months reviewed before a tour, often May–July, not the full season. When monitors found a different count in the logs than in a Summary Report, both are rows for the same month.

## Fields

`type_of_cooling` in `housing_cooling_equipment_2024.csv`, as CDCR defines it:

- **Ventilation without cooling:** an air handling system that supplies air with no cooling.
- **Refrigeration cooling:** air passed over refrigerant-chilled coils.
- **Evaporation cooling:** air passed over a water-soaked medium.

`coleman_heat_plan_findings.csv`:

| Column | Meaning |
| :--- | :--- |
| `area` | Heat plan area. `heat_plan` is a verdict on the plan as a whole; `temperature_logs` covers logs the text doesn't identify as indoor or outdoor; `overall_opening` and `overall_conclusion` are the verdicts at the start and end of an institution summary. |
| `finding` | `compliant`, `not_compliant`, `unable_to_report`, or the report's own word where it uses another. |

`coleman_heat_plan_counts.csv`:

| Column | Meaning |
| :--- | :--- |
| `recorded_in` | The CDCR record a figure comes from, `not_stated` if the report doesn't name one, or `cqit_indicator` for Receiver audit indicators. |
| `scope` | `institution` where the report says counts cover the whole institution, `PIP` where it attributes a figure to the inpatient program, blank if it doesn't say. |
| `value` | The count. Blank means the report describes the event without giving one. |
| `cdcr_code` | `ALL` for statewide rows. |
| `note` | Where older reports give alerts as days above a threshold, call illnesses "incidents", or give activation days without a stage. |

## Provenance

| Table | Source | Script and inputs | Covered through |
| :--- | :--- | :--- | :--- |
| `air_cooling_*`, `CDCR_indoor_78f_days_2025` | [Air Cooling report](https://www.cdcr.ca.gov/fpcm/wp-content/uploads/sites/184/2026/02/Air_Cooling_Document_for_Legislature.pdf) | Transcribed by hand | Dec 2025 |
| `housing_cooling_equipment_2024` | [Plata ECF 3952-1](https://storage.courtlistener.com/recap/gov.uscourts.cand.76/gov.uscourts.cand.76.3952.1.pdf) | `extract_housing_cooling_types.py`, needs `tesseract`; PDF in `sources/heat_cooling/` | Aug 2024 |
| `cooling_observations` | The filings under Files | Transcribed by hand | May 2026 filing |
| `coleman_heat_plan_*` | [Coleman docket](https://www.courtlistener.com/docket/4161512/pc-coleman-v-newsom/), [CCHCS reports](https://cchcs.ca.gov/reports/) | `extract_coleman_heat.py`; PDFs in `sources/heat_cooling/` | May 2026 |

## References

California Department of Corrections and Rehabilitation. (2026, January). *Air Cooling Pilot Program Supplemental Report*. https://www.cdcr.ca.gov/fpcm/wp-content/uploads/sites/184/2026/02/Air_Cooling_Document_for_Legislature.pdf

California Department of Corrections and Rehabilitation. (2025, June). *Climate and the Impact on CDCR: Air Cooling Infrastructure/Needs at Institutions Statewide* [also filed as Exhibit F to Plata ECF 3984-1]. https://www.cdcr.ca.gov/green/wp-content/uploads/sites/176/2025/06/Climate-and-the-Impact-on-CDCR.pdf

Coleman v. Newsom, No. 2:90-cv-0520 KJM SCR (E.D. Cal.). (2018–2024). *Special Master's 27th–30th Round Monitoring Reports* (ECF Nos. 5779, 7074, 7555, 7715, 7716, 7833, 8095, 8359). https://storage.courtlistener.com/recap/gov.uscourts.caed.83056/gov.uscourts.caed.83056.{ECF}.0.pdf

Coleman v. Newsom, No. 2:90-cv-0520 KJM SCR (E.D. Cal.). (2025, December 18). *Special Master's Thirty-First Round Monitoring Report – Part B*, Appendix A: *Institutional Summaries* (ECF No. 8838-1). https://storage.courtlistener.com/recap/gov.uscourts.caed.83056/gov.uscourts.caed.83056.8838.1.pdf

Coleman v. Newsom, No. 2:90-cv-0520 KJM SCR (E.D. Cal.). (2025, February 28). *Special Master's Thirty-First Round Focused Heat Plan Monitoring Report* (ECF No. 8558). https://storage.courtlistener.com/recap/gov.uscourts.caed.83056/gov.uscourts.caed.83056.8558.0.pdf

Coleman v. Newsom, No. 2:90-cv-0520 KJM SCR (E.D. Cal.). (2026). *Continuous Quality Improvement Reports* [Receiver's Compliance Team, Statewide Mental Health Program; CCI, CCWF, CHCF, CIW, CTF, FSP, KVSP, MCSP, NKSP, PBSP, PVSP, RJD, SCC, SOL; review periods Aug 2025 – May 2026]. https://cchcs.ca.gov/reports/

Plata v. Newsom, No. 4:01-cv-01351-JST (N.D. Cal.). (2025, March 10). *Joint Case Management Conference Statement, Exhibits* (ECF No. 3952-1), Exhibit E, Attachment B: *CDCR Housing Unit Cooling Types by Institution* (dated August 22, 2024). https://storage.courtlistener.com/recap/gov.uscourts.cand.76/gov.uscourts.cand.76.3952.1.pdf

Plata v. Newsom, No. 4:01-cv-01351-JST (N.D. Cal.). (2025, June 10). *Joint Case Management Conference Statement [Corrected], Exhibits* (ECF No. 3968-1). https://storage.courtlistener.com/recap/gov.uscourts.cand.76/gov.uscourts.cand.76.3968.1.pdf

Plata v. Newsom, No. 4:01-cv-01351-JST (N.D. Cal.). (2026, May 26). *Joint Case Management Conference Statement* (ECF No. 4013). https://storage.courtlistener.com/recap/gov.uscourts.cand.76/gov.uscourts.cand.76.4013.0.pdf

Plata v. Newsom, No. 4:01-cv-01351-JST (N.D. Cal.). (2026, May 26). *Joint Case Management Conference Statement, Exhibits* (ECF No. 4013-1). https://storage.courtlistener.com/recap/gov.uscourts.cand.76/gov.uscourts.cand.76.4013.1.pdf

Raychaudhuri, D., Farley, C., Hartman, T., & Arranz, A. (2025, July 30). *Scorching cells: How heat threatens lives in America's prisons*. Reuters. https://www.reuters.com/graphics/USA-TEMPERATURE/PRISONS/jnpwbejwlvw/ [CDCR's housing cooling table and CDCR's June 27, 2025 clarification email, as released by Reuters]
