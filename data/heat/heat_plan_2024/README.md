# 2024 Heat Plan records

Tables from CDCR's 2024 Heat Plan monthly packages, May–October, released under the California Public Records Act to Reuters and published with "Scorching cells" (July 2025). There are 189 packages and 28,651 scanned pages. The handwritten indoor temperature readings aren't in this folder yet.

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `heat_plan_monthly_summaries_2024.csv` | A Heat Plan Monthly Summary Report (MH-7711-1): days each stage was initiated, cooling measures, Stage III rounds, heat illness patients | May–Oct 2024 | Reuters packages |
| `heat_plan_log_pages_2024.csv` | A page of a package: the form it holds and its printed header fields | May–Oct 2024 | Same |
| `indoor/locations.csv` | A housing unit or location string as written on an indoor temperature page: its facility, housing unit, building, spot and level | May–Oct 2024 | Reuters packages; `data/buildings/locations/` |

## Caveats

- **Monthly summaries** are CDCR's self-reported figures. The form asks for the number of days each stage was initiated, so a day with alerts in several housing units counts once. Each answer is kept as printed in `*_as_stated`, with a parsed integer where it's a number; `N/A`, `NA`, `None`, and a slashed zero are 0. A blank integer means the form left the answer blank or there's no form, and `note` says so. Where a form gives no year, the year comes from the file name.
- **Page index:** forms were classified from OCR of each page's printed title, so `form` is a guide, not a verified count. `cdcr_2031` includes institutions' own inside-temperature forms and a few pages that aren't inside readings. Pages in the indoor transcription, and pages whose title didn't OCR but were checked by eye, take their `form` from the page image (`note` = `identified from page image`). The `*_as_stated` header fields are OCR text and weren't checked.
- **Units:** the housing unit is as written and hasn't been cleaned or linked to the building inventory. Inside records with `header_check` = `ocr`, mostly forms without the standard unit line, have no checked unit.
- `package_month` is the month in Reuters' file name, corrected where the name is wrong. A package can also hold logs from the end of the previous month or the start of the next.

## Fields

| Column | Meaning |
| :--- | :--- |
| `form` | `mh_7711_1` (monthly summary), `mh_7711_2` (heat incident log), `mh_7711_3` (Stage III rounds log), `cdcr_2030` (outside temperature record), `cdcr_2031` (inside temperature record), `weather_station_export` (weather-station data printout), `other_form`, or `blank_or_unreadable`. |
| `ocr_check` | In the summaries, `ocr` where OCR read every answer the same as the page image, `corrected from image` where an answer was taken from the image. |
| `source_file`, `page` | The package and page in the Reuters files. |

`indoor/locations.csv` joins the indoor readings on `package`, `page` and `housing_unit_as_written`:

| Column | Meaning |
| :--- | :--- |
| `cdcr_code` | Institution code (`data/institutions.csv`). |
| `form` | The page's form: `2031` (CDCR 2031), `local` (an institution's own form), or a named local form. |
| `readings` | Reading cells the string has in the indoor tables. |
| `facility_key` | The unit's facility, else the facility the string names (`data/buildings/locations/facilities.csv`). |
| `unit_key` | The housing unit (`housing_units.csv`). |
| `unit_source` | `string` (the page's own string), `page (hand)`, `page (review)` or `page (rule)` (the unit is set for the page). |
| `place_key` | The building (`places.csv`) or set of identical buildings (`place_sets.csv`); `;` separates several. |
| `place_part` | The part of the building the unit is (`place_parts.csv`). |
| `place_relation` | The unit's link to the place, as `relation` in `unit_links.csv`; `several places` when its links differ, `unit not linked to a place`, or `non-housing place`. |
| `section` | Section, side or wing letter (`A`–`H`, `EAST`, `WEST`). |
| `place_type` | `housing`, or a non-housing type: `work/industry`, `education`, `dining`, `program office/admin`, `kitchen`, `chapel`, `canteen`, `health care`, `gym/recreation`, `visiting`, `other non-housing`. |
| `place_written` | The place as written when the string names no housing unit. |
| `location_type` | Where in the unit the reading was taken: `tier`, `dayroom/common area`, `officer podium/desk`, `control booth`, `hallway`, `cell/room`, `office`, `swamp cooler`, or `varies`. |
| `room_written`, `room_kind`, `room_kind_source` | A room as written, whether it's a `cell` or `dorm`, and whether that's `written` or follows the prison's numbering (`prison rule`). |
| `level`, `level_source` | Floor or tier, and its source: `written` on the page, `unit` (the unit name carries the floor), `building` (a single-story building), `same unit` (every page of the unit that writes a level writes this one), or `page override`. |
| `location_note` | A note on the page's location, such as two sheets for one section on the same day. |

## Provenance

| Table | Source | Script and inputs | Covered through |
| :--- | :--- | :--- | :--- |
| `heat_plan_monthly_summaries_2024` | [Reuters prison-heat-records](https://github.com/reuters-graphics/prison-heat-records) | `extract_reuters_msr.py`, needs `tesseract`; PDFs in `sources/reuters_heat_records/california/responses/` | Oct 2024 |
| `heat_plan_log_pages_2024` | Same | `index_reuters_heat_pages.py`, needs `tesseract`; units read from page images | Oct 2024 |
| `indoor/locations` | Same, and `data/buildings/locations/` | Built from the page strings and the location tables | Oct 2024 |

## References

Raychaudhuri, D., Farley, C., Hartman, T., & Arranz, A. (2025, July 30). *Scorching cells: How heat threatens lives in America's prisons*. Reuters. https://www.reuters.com/graphics/USA-TEMPERATURE/PRISONS/jnpwbejwlvw/

Reuters. (2025). *prison-heat-records* [California Department of Corrections and Rehabilitation Heat Plan monthly packages, May–October 2024, released under the California Public Records Act]. GitHub. https://github.com/reuters-graphics/prison-heat-records
