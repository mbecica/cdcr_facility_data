#!/usr/bin/env python3
"""
Monthly institution totals from the SB 601 dashboard, read through its query endpoint with the
same sum and category and metric names as the dashboard's Institution Table.

The report's slicers offer only recent fiscal years, but its data goes further back, so this
reads every report date instead of the slicer's years.

Output, one row per institution, month and metric with a published value:
  data/operations/sb601_operations.csv   lockdowns and modified programs, deaths, overtime, use of force, fiscal
  data/operations/sb601_programs.csv     every category but grievances, which fetch_sb601_grievances.py reads

Refreshes add to the files. A new value replaces the old one, and a value the report no longer
gives stays, so nothing is lost when CDCR removes a year or a date.

Usage:
  python3 scrapers/fetch_sb601_tables.py
"""

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from institution_codes import load_codes
from powerbi_query import Report, column, equals, total

ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = ROOT / "data" / "operations" / "sb601_operations.csv"
PROGRAMS = ROOT / "data" / "operations" / "sb601_programs.csv"

REPORT_R = "eyJrIjoiYzlkM2RiNWEtZDRjMi00ODllLTg2YzEtZjYyM2MwMjA5NmQ0IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9"
SOURCES = {"s": "SB601", "i": "dimInstitution", "c": "dimCategory", "m": "dimMetric"}
GRIEVANCES = "Incarcerated Persons Grievances and Appeals"
OPERATIONS_CATEGORIES = {"Fiscal", "Lockdowns and Modified Programs", "Number of Deaths",
                         "Overtime Hours", "Use of Force (UOF)"}
# A month with fewer values than this is stray rows, such as a date entered in the future,
# and not a reported month.
MIN_MONTH_ROWS = 1000
KEY = ["institution_as_stated", "month", "category", "metric"]
COLUMNS = ["cdcr_code", "institution_as_stated", "month", "category", "metric", "value"]


def fetch():
    report = Report(REPORT_R)
    dates = report.query({"s": "SB601"}, [column("s", "Date")])
    dates = sorted(r[0] for r in dates if r[0] is not None)
    print(f"{len(dates)} report dates")
    select = [column("i", "Institution"), column("c", "Category - Institution"),
              column("m", "Metric - Institution"), total("s", "Value")]
    rows = []
    for ms in dates:
        d = datetime.fromtimestamp(ms / 1000, timezone.utc)
        where = [equals("s", "Date", f"datetime'{d:%Y-%m-%dT00:00:00}'")]
        rows += [[f"{d:%Y-%m}", *r] for r in report.query(SOURCES, select, where)]
    df = pd.DataFrame(rows, columns=["month", "institution_as_stated", "category", "metric", "value"])
    df["value"] = pd.to_numeric(df["value"])
    df = df.dropna(subset=["value"]).groupby(KEY, as_index=False)["value"].sum()
    df["value"] = df["value"].round(6)

    counts = df["month"].value_counts()
    last = counts[counts >= MIN_MONTH_ROWS].index.max()
    stray = df[df["month"] > last]
    print(f"Leaving out {len(stray)} values dated after {last}: {sorted(stray['month'].unique())}")
    return df[df["month"] <= last]


def merge(new, path, aliases):
    """New values replace old ones, and old values the report no longer gives stay."""
    old = pd.read_csv(path).dropna(subset=["value"])
    both = old.merge(new, on=KEY, how="left", suffixes=("_old", ""))
    kept = old[both["value"].isna().values]
    changed = both[both["value"].notna() & ((both["value"] - both["value_old"]).abs() > 0.0051)]
    out = pd.concat([new, kept[KEY + ["value"]]], ignore_index=True)
    out["cdcr_code"] = out["institution_as_stated"].map(lambda i: aliases.get(i, ""))
    out["value"] = out["value"].map(lambda v: f"{v:.6f}".rstrip("0").rstrip("."))
    out = out[COLUMNS].sort_values(["cdcr_code", "institution_as_stated", "month", "category", "metric"])
    out.to_csv(path, index=False)
    print(f"{path.relative_to(ROOT)}: {len(out)} rows, {out['month'].min()} to {out['month'].max()}; "
          f"{len(changed)} held values changed, {len(kept)} kept that the report no longer gives "
          f"{dict(Counter(kept['category']))}")


def main():
    new = fetch()
    aliases = load_codes()
    merge(new[new["category"].isin(OPERATIONS_CATEGORIES)], OPERATIONS, aliases)
    merge(new[new["category"] != GRIEVANCES], PROGRAMS, aliases)


if __name__ == "__main__":
    main()
