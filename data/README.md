# Data

Each folder holds one topic and has its own README with file coverage, field definitions, and sources.

## Conventions

- **Time series** are long: one row per period and measure or group, not one column per month. `month` is `YYYY-MM`.
- **Institutions** are identified by `cdcr_code`, with the name as published beside it where the source gives one. `crosswalk/institutions.csv` lists the codes, FEMA facility IDs, and the alias codes sources use.
- **Source wording** stays in `_as_stated` columns. Source identifiers are kept as entered, and normalized keys go in separate columns.
- **Numbers** are stored without commas or `%` and `$` signs. Blanks stay blank and aren't converted to 0.
- **Suppressed values** stay as published (`*`, `**`) unless a table's README says otherwise.

## How the topics connect

- [`facilities_summary/`](facilities_summary/) summarizes the other folders, one row per institution, and is built by `build_cdcr_facilities.py`.
- Tables with a `cdcr_code` or `institution` column join on institution code.
- [`crosswalk/buildings.csv`](../crosswalk/buildings.csv), described in [`buildings/`](buildings/), links building-level tables in `buildings/` and `heat/cooling/`.

## Verification flags

`verification_flags.csv` lists values in these tables that conflict with the source's own totals or with other sources, with the evidence on each side and what would resolve it. Values are left as transcribed until a source settles them.
