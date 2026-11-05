# 2024 Heat Plan records

Tables from CDCR's 2024 Heat Plan monthly packages, May–October, released under the California Public Records Act to Reuters and published with "Scorching cells" (July 2025). There are 189 packages and 28,651 scanned pages. The handwritten indoor temperature readings aren't in this folder yet.

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `heat_plan_monthly_summaries_2024.csv` | A Heat Plan Monthly Summary Report (MH-7711-1): days each stage was initiated, cooling measures, Stage III rounds, heat illness patients | May–Oct 2024 | Reuters packages |
| `heat_plan_log_pages_2024.csv` | A page of a package: the form it holds and its printed header fields | May–Oct 2024 | Same |
| `heat_plan_log_pages_2024_units.csv` | An inside temperature record: the housing unit as written, read from the page image | 18,066 pages | Same |
| `heat_plan_log_stage_days_2024.csv` | A prison and month: Stage I, II, and III days counted from the logs | 92 prison-months, mostly Jun–Aug 2024 | Same, and Reuters' extracted readings |
| `heat_plan_log_stage_days_2024_evidence.csv` | A day counted or considered, with the page and reading it rests on | Same | Same |

## Caveats

- **Monthly summaries** are CDCR's self-reported figures. The form asks for the number of days each stage was initiated, so a day with alerts in several housing units counts once. Each answer is kept as printed in `*_as_stated`, with a parsed integer where it's a number; `N/A`, `NA`, `None`, and a slashed zero are 0. A blank integer means the form left the answer blank or there's no form, and `note` says so. Where a form gives no year, the year comes from the file name.
- **Page index:** forms were classified from OCR of each page's printed title, so `form` is a guide, not a verified count. `cdcr_2031` includes institutions' own inside-temperature forms and a few pages that aren't inside readings, and some inside records too dark or misoriented to OCR are under `other_form`. The `*_as_stated` header fields are OCR text and weren't checked.
- **Units:** the housing unit is as written and hasn't been cleaned or linked to the building inventory. Inside records with `header_check` = `ocr`, mostly forms without the standard unit line, have no checked unit.
- `package_month` is the month in Reuters' file name, corrected where the name is wrong. A package can also hold logs from the end of the previous month or the start of the next.
- **Stage days:** most prison-months come from Reuters' extracted indoor readings for June–August (`source` = `reuters_json`), which have no housing unit or page and are a cross-check only. `rule` says how each count was made. Readings that couldn't be read with confidence aren't counted, so a count can be a lower bound, and `note` then gives the upper bound.

## Fields

| Column | Meaning |
| :--- | :--- |
| `form` | `mh_7711_1` (monthly summary), `mh_7711_2` (heat incident log), `mh_7711_3` (Stage III rounds log), `cdcr_2030` (outside temperature record), `cdcr_2031` (inside temperature record), `other_form`, or `blank_or_unreadable`. |
| `ocr_check` | In the summaries, `ocr` where OCR read every answer the same as the page image, `corrected from image` where an answer was taken from the image. |
| `source_file`, `page` | The package and page in the Reuters files. |

## Provenance

| Table | Source | Script and inputs | Covered through |
| :--- | :--- | :--- | :--- |
| `heat_plan_monthly_summaries_2024` | [Reuters prison-heat-records](https://github.com/reuters-graphics/prison-heat-records) | `extract_reuters_msr.py`, needs `tesseract`; PDFs in `sources/reuters_heat_records/california/responses/` | Oct 2024 |
| `heat_plan_log_pages_2024`, `_units` | Same | `index_reuters_heat_pages.py`, needs `tesseract`; units read from page images | Oct 2024 |
| `heat_plan_log_stage_days_2024`, `_evidence` | Same | `count_heat_log_stage_days.py` | Oct 2024 |

## References

Raychaudhuri, D., Farley, C., Hartman, T., & Arranz, A. (2025, July 30). *Scorching cells: How heat threatens lives in America's prisons*. Reuters. https://www.reuters.com/graphics/USA-TEMPERATURE/PRISONS/jnpwbejwlvw/

Reuters. (2025). *prison-heat-records* [California Department of Corrections and Rehabilitation Heat Plan monthly packages, May–October 2024, released under the California Public Records Act]. GitHub. https://github.com/reuters-graphics/prison-heat-records
