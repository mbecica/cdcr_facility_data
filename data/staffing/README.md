# Staffing

Active state employee counts for CDCR facilities from the State Controller's Office (SCO).

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `sco_staffing.csv` | A report and SCO facility line: full-time, part-time, intermittent, indeterminate, and total employees | 8 reports, Apr 2021 – Feb 2026 | SCO, Active State Employees by Department |
| `sco_staffing_avg.csv` | An institution and SCO facility line, averaged across the year's reports | 3 reports, 2025 | Built from `sco_staffing.csv` |

## Caveats

- Reports were retrieved through Wayback Machine snapshots, so the months depend on what was archived.
- Regional offices, training academies, parole, and administrative units aren't included.
- Prison Industry Authority (PIA) sub-entries are separate rows ending in `- PIA`. PIA workers are incarcerated people. `is_pia` and `is_cchcs` mark these and CCHCS rows, and `n_snapshots` is how many of the year's reports a line appears in.

## Provenance

| Table | Source | Script and inputs | Covered through |
| :--- | :--- | :--- | :--- |
| `sco_staffing` | SCO reports, through the Wayback Machine | `extract_sco_staffing.py`; PDFs in `sources/cdcr_staffing/` | Feb 2026 |
| `sco_staffing_avg` | `sco_staffing.csv` | `build_sco_staffing_avg.py` | 2025 |

## References

California State Controller's Office. (2021–2026). *Active State Employees by Department*. Retrieved through the Internet Archive Wayback Machine.
