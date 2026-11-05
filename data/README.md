# Data

Each folder holds one topic and has its own README with file coverage, field definitions, and sources.

## Conventions

- **Time series** are long: one row per period and measure or group. `month` is `YYYY-MM`.
- **Institutions** are identified by `cdcr_code`, with the name as published beside it wherever possible. `crosswalk/institutions.csv` lists the codes, FEMA facility IDs, and the alias codes sources use.
- **Source wording** stays in `_as_stated` columns. Source identifiers are kept as entered, and normalized keys go in separate columns.
- **Numbers** are stored without commas or `%` and `$` signs. Blanks stay blank and aren't converted to 0.
- **Suppressed values** stay as published (`*`, `**`) unless a table's README says otherwise.

## How data is joined

- [`facilities_summary/`](facilities_summary/) summarizes the other folders, one row per institution, and is built by `build_cdcr_facilities.py`.
- Tables with a `cdcr_code` or `institution` column join on institution code.
- [`crosswalk/buildings.csv`](../crosswalk/buildings.csv), described in [`buildings/`](buildings/), links building-level tables in `buildings/` and `heat/cooling/`.

## Revisions

CDCR changes some published values later. A refresh replaces the old value with the current one, and keeps a value the source no longer gives.

| Series | Refreshes compared | What changed |
| :--- | :--- | :--- |
| Average sentence | Apr and Nov 2026 | 16 of 86 values, most by 1–2 months, for months back to Jul 2023 |
| SB 601 contraband | Mar and Nov 2026 | 516 quantities for Oct 2024 – Apr 2025 fell, most by half; 778 FY 2024-25 values no longer appear by month |
| CCHCS measures | Mar and Nov 2026 | None in the staffing, cost, or population measures here, though the dashboard's Version History records recalculations of other measures |

No values changed between refreshes in SB 601 operations, population by location, or return rates.

## Verification flags

`verification_flags.csv` lists values in these tables that conflict with the source's own totals or with other sources, with the evidence on each side and what would resolve it. Values are left as transcribed if conflicts are found.
