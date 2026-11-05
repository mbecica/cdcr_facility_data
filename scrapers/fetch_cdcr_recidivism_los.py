#!/usr/bin/env python3
"""
Three-year return-to-prison rate by release cohort and length of stay from the CDCR Adult
Recidivism dashboard, read through its query endpoint as the aggregate measure and with the
filters of the dashboard's Returns crosstab. The rate is never computed here.

Output, one row per fiscal year and length of stay:
  data/population/cdcr_recidivism_los.csv

Usage:
  python3 scrapers/fetch_cdcr_recidivism_los.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from powerbi_query import Report, column

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "population" / "cdcr_recidivism_los.csv"
REPORT_R = "eyJrIjoiNmRjOTkwMWEtYmVkMy00MTA1LWIxZDYtYzg4OTIzYjkxNTRlIiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9"
SOURCES = {"f": "Fiscal Year", "k": "Key Measures", "r": "Recidivism"}
RATE = {"Measure": {"Expression": {"SourceRef": {"Source": "k"}}, "Property": "3 Year Return Rate"},
        "Name": "Key Measures.3 Year Return Rate"}


def crosstab_filters(report):
    """The Returns crosstab's filter conditions and the extra sources they need. Each filter
    names its own sources, and two use the same name, so those get new names here."""
    section = next(s for s in report.exploration["sections"] if s["displayName"] == "Return")
    sources, where = dict(SOURCES), []
    for visual in section["visualContainers"]:
        if json.loads(visual["config"]).get("singleVisual", {}).get("visualType") != "pivotTable":
            continue
        filters = visual.get("filters", "[]")
        for i, f in enumerate(json.loads(filters) if isinstance(filters, str) else filters):
            if not f.get("filter"):
                continue
            text = json.dumps(f["filter"]["Where"])
            for source in f["filter"]["From"]:
                name, entity = source["Name"], source["Entity"]
                if sources.get(name) != entity:
                    text = text.replace(f'"Source": "{name}"', f'"Source": "{name}{i}"')
                    sources[f"{name}{i}"] = entity
            where += json.loads(text)
    return sources, where


def main():
    report = Report(REPORT_R)
    select = [column("f", "Fiscal_Year"), column("r", "Length_of_Stay"), RATE]
    sources, where = crosstab_filters(report)
    rows = report.query(sources, select, where)
    df = pd.DataFrame(rows, columns=["fiscal_year", "length_of_stay", "rate"]).dropna(subset=["fiscal_year", "length_of_stay"])
    # The measure returns a fraction, published to one decimal place as a percent
    df["three_year_return_rate_pct"] = (pd.to_numeric(df["rate"].astype(str).str.rstrip("D")) * 100).round(1)
    order = {los: i for i, (los, _) in enumerate(report.query({"d": "dimLength_of_Stay"}, [column("d", "Length_of_Stay"), column("d", "sort")]))}
    df["sort"] = df["length_of_stay"].map(order)
    df = df.sort_values(["fiscal_year", "sort"])[["fiscal_year", "length_of_stay", "three_year_return_rate_pct"]]
    df.to_csv(OUT, index=False)
    print(f"Saved {len(df)} rows, {df['fiscal_year'].min()} to {df['fiscal_year'].max()}")


if __name__ == "__main__":
    main()
